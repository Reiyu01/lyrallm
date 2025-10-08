import asyncio
import logging
from lyrallm.config.config_manager import config_manager
from logger_service.handlers import get_handlers

logger = logging.getLogger(__name__)


async def _handle_event(event: dict):
    """Core event handler that dispatches to configured handlers.

    Database handlers are awaited synchronously (in order). Background handlers
    (e.g. HTTP/UDP forwarders) are scheduled with create_task so they don't block.
    """
    try:
        # Normalize timestamp if necessary
        if isinstance(event.get('timestamp'), str):
            from datetime import datetime
            try:
                event['timestamp'] = datetime.fromisoformat(event['timestamp'])
            except Exception:
                pass

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


def start_event_consumer():
    backend = config_manager.config.get('event_bus', {}).get('backend')
    if backend == 'redis_stream':
        # start redis streams consumer loop
        try:
            from logger_service.redis_streams import RedisStreamsConsumer
            consumer = RedisStreamsConsumer()

            async def _start_loop():
                await consumer.start(_handle_event)

            loop = asyncio.get_event_loop()
            loop.create_task(_start_loop())
            logger.info("Redis Streams consumer started")
            return
        except Exception as e:
            logger.exception(f"Failed to start Redis Streams consumer: {e}")

    # fallback to in-process EventBus
    try:
        from logger_service.event_bus import event_bus
        event_bus.subscribe(_handle_event)
        logger.info("In-process EventBus consumer subscribed")
    except Exception as e:
        logger.exception(f"Failed to start in-process event consumer: {e}")


# Start consumer on import so package usage triggers it
try:
    start_event_consumer()
except Exception:
    logger.exception("Failed to start event consumer")
