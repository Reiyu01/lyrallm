import asyncio
import logging
from lyrallm.config.config_manager import config_manager
from .handlers import get_handlers

logger = logging.getLogger(__name__)

# 全局緩存 handlers，避免每次事件都重新創建
_handlers_cache = None

def _get_cached_handlers():
    """獲取緩存的 handlers，首次調用時創建"""
    global _handlers_cache
    if _handlers_cache is None:
        _handlers_cache = get_handlers()
        logger.info(f"[EventConsumer] Initialized {len(_handlers_cache)} handlers")
    return _handlers_cache


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

        logger.info(f"[EventConsumer] Received event: {event.get('request_id') or event.get('id')}")
        handlers = _get_cached_handlers()

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
            from .redis_streams import RedisStreamsConsumer
            consumer = RedisStreamsConsumer()

            async def _start_loop():
                await consumer.start(_handle_event)

            loop = asyncio.get_event_loop()
            loop.create_task(_start_loop())
            logger.info("Redis Streams consumer started")
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
    except Exception as e:
        logger.exception(f"Failed to start in-process event consumer: {e}")


