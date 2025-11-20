import asyncio
import logging
from datetime import datetime
from lyrallm.config.config_manager import config_manager
from .handlers import get_handlers, get_db_handlers

logger = logging.getLogger(__name__)

_FLUSH_INTERVAL_SECONDS = 60
_flush_task_started = False


async def _handle_event(event: dict):
    """Core event handler that dispatches to configured handlers.

    Database handlers are awaited synchronously (in order). Background handlers
    (e.g. HTTP/UDP forwarders) are scheduled with create_task so they don't block.
    """
    try:
        # Normalize timestamp if necessary
        if isinstance(event.get('timestamp'), str):
            try:
                event['timestamp'] = datetime.fromisoformat(event['timestamp'])
            except Exception:
                pass

        logger.info(f"[EventConsumer] Received event: {event.get('request_id') or event.get('id')}")
        handlers = get_handlers()

        for h in handlers:
            try:
                if getattr(h, 'background', False):
                    # schedule background handler and don't await
                    asyncio.create_task(h.handle(event))
                else:
                    # await DB or other critical handlers
                    await h.handle(event)
            except Exception as e:
                logger.exception(f"Handler {h.__class__.__name__} failed: {e}")

    except Exception as e:
        logger.exception(f"Failed to handle event: {e}")


async def _flush_loop():
    while True:
        try:
            await asyncio.sleep(_FLUSH_INTERVAL_SECONDS)
            handlers = get_db_handlers()
            if not handlers:
                continue

            now = datetime.utcnow()
            for handler in handlers:
                try:
                    flushed = await handler.flush(now=now)
                    if flushed:
                        logger.info(
                            "Periodic flush wrote %s aggregate windows via %s",
                            flushed,
                            handler.__class__.__name__,
                        )
                except Exception as exc:
                    logger.exception(
                        "Periodic flush failed for %s: %s",
                        handler.__class__.__name__,
                        exc,
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(f"Periodic flush loop error: {exc}")


def _ensure_flush_loop():
    global _flush_task_started
    if _flush_task_started:
        return

    loop = asyncio.get_event_loop()
    loop.create_task(_flush_loop())
    _flush_task_started = True
    logger.info("Analytics flush loop started")


def start_event_consumer():
    backend = config_manager.config.get('event_bus', {}).get('backend')
    if backend == 'redis_stream':
        # start redis streams consumer loop
        try:
            from .redis_streams import RedisStreamsConsumer
            consumer = RedisStreamsConsumer()

            async def _start_loop():
                await consumer.start(_handle_event)

            loop = asyncio.get_event_loop()
            loop.create_task(_start_loop())
            logger.info("Redis Streams consumer started")
            _ensure_flush_loop()
            return
        except ModuleNotFoundError:
            logger.info('Redis Streams module not available; falling back to in-process queue.')
        except Exception as e:
            logger.exception(f"Failed to start Redis Streams consumer: {e}")

    # fallback to in-process EventBus
    try:
        from .event_bus import event_bus
        if event_bus.subscriber_count() == 0:
            event_bus.subscribe(_handle_event)
            logger.info("In-process EventBus consumer subscribed")
        else:
            logger.info("In-process EventBus consumer already subscribed")
        _ensure_flush_loop()
    except Exception as e:
        logger.exception(f"Failed to start in-process event consumer: {e}")


