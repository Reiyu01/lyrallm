```python
import asyncio
import logging
from logger_service.event_bus import event_bus
from logger_service.db_client import get_postgres_client

logger = logging.getLogger(__name__)


async def _handle_event(event: dict):
    try:
        # Ensure timestamp is a datetime if it's ISO string
        if isinstance(event.get('timestamp'), str):
            from datetime import datetime
            try:
                event['timestamp'] = datetime.fromisoformat(event['timestamp'])
            except Exception:
                # leave as-is; asyncpg can accept text for timestamp with time zone in many configs
                pass

        pg = get_postgres_client()
        # insert (connect inside)
        await pg.insert_token_usage(event)
        logger.debug(f"Inserted token usage for request_id={event.get('request_id')}")
    except Exception as e:
        logger.exception(f"Failed to handle event: {e}")


def start_event_consumer():
    # subscribe the handler. event_bus will create the dispatcher task
    event_bus.subscribe(_handle_event)


# Start consumer on import so package usage triggers it
try:
    start_event_consumer()
except Exception:
    logger.exception("Failed to start event consumer")

```