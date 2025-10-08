```python
import asyncio
import logging
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class EventBus:
    """Simple in-process asyncio event bus using a Queue.

    Use EventBus.publish(...) to emit events and EventBus.subscribe(...) to
    register an async handler that will be called for each event.
    """

    _instance = None

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._subscribers = []
        self._task = None

    @classmethod
    def get_instance(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = EventBus()
        return cls._instance

    def publish(self, event: Any):
        """Publish an event to the bus (thread-safe)."""
        try:
            self._queue.put_nowait(event)
        except Exception:
            # fallback to coro
            asyncio.create_task(self._queue.put(event))

    def queue_size(self) -> int:
        """Return approximate queue size."""
        try:
            return self._queue.qsize()
        except Exception:
            return -1

    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def subscribe(self, handler: Callable[[Any], Coroutine]):
        """Register an async handler(event) -> None."""
        self._subscribers.append(handler)
        # start the dispatcher when first subscriber is added
        if not self._task:
            loop = asyncio.get_event_loop()
            self._task = loop.create_task(self._dispatch_loop())

    async def _dispatch_loop(self):
        while True:
            event = await self._queue.get()
            for sub in list(self._subscribers):
                try:
                    # dispatch without waiting for all handlers sequentially
                    asyncio.create_task(sub(event))
                except Exception as e:
                    logger.exception(f"Event handler error: {e}")


event_bus = EventBus.get_instance()

```