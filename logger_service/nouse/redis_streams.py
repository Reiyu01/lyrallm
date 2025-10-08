"""Redis Streams adapter for event publishing and consumption.

This module provides a minimal publisher (xadd) and a consumer loop
that reads from a consumer group (xreadgroup) and yields messages to a
handler. It uses redis.asyncio when available; otherwise it provides
stubs that log warnings so the project can still run in environments
without redis installed.
"""
import asyncio
import json
import logging
from typing import Any, Callable, Optional
from lyrallm.config.config_manager import config_manager

logger = logging.getLogger(__name__)

HAS_REDIS = True
try:
    import redis.asyncio as redis
except Exception:
    HAS_REDIS = False
    redis = None  # type: ignore


class RedisStreamsPublisher:
    def __init__(self, stream_name: str = "token_usage_stream", url: Optional[str] = None):
        cfg = config_manager.config.get('event_bus', {})
        self.stream = stream_name
        self.url = url or cfg.get('redis_url') or 'redis://localhost:6379/0'
        self._client = None

    async def _ensure_client(self):
        if not HAS_REDIS:
            logger.warning("redis.asyncio not available; RedisStreamsPublisher is a no-op")
            return
        if self._client is None:
            self._client = redis.from_url(self.url)

    async def publish(self, event: Any) -> Optional[str]:
        await self._ensure_client()
        if not HAS_REDIS:
            logger.info("[Redis stub] publish called: %s", event)
            return None
        # flatten into string fields; store raw as JSON field
        try:
            msg_id = await self._client.xadd(self.stream, {"raw": json.dumps(event)}, maxlen=None)
            return msg_id
        except Exception as e:
            logger.exception(f"Redis xadd failed: {e}")
            return None


class RedisStreamsConsumer:
    def __init__(self, stream_name: str = "token_usage_stream", group: str = "token_usage_group", consumer: str = "consumer-1", url: Optional[str] = None):
        cfg = config_manager.config.get('event_bus', {})
        self.stream = stream_name
        self.group = group
        self.consumer = consumer
        self.url = url or cfg.get('redis_url') or 'redis://localhost:6379/0'
        self._client = None
        self._running = False
        # claim/dlq settings
        self.dlq_stream = cfg.get('dlq_stream') or cfg.get('dlq') or 'token_usage_dlq'
        # milliseconds
        self.idle_threshold_ms = int(cfg.get('idle_threshold_ms', 60_000))
        self.max_delivery_count = int(cfg.get('max_delivery_count', 5))
        self.claim_interval_sec = int(cfg.get('claim_interval_sec', 30))
        self._claim_task = None

    async def _ensure_client(self):
        if not HAS_REDIS:
            logger.warning("redis.asyncio not available; RedisStreamsConsumer is a no-op")
            return
        if self._client is None:
            self._client = redis.from_url(self.url)
            # ensure group exists
            try:
                await self._client.xgroup_create(self.stream, self.group, id='$', mkstream=True)
            except Exception:
                # group may already exist
                pass

    async def start(self, handler: Callable[[dict], asyncio.Future], block_ms: int = 1000, count: int = 10):
        await self._ensure_client()
        if not HAS_REDIS:
            logger.info("[Redis stub] start called; no loop will run")
            return
        self._running = True
        # start claim background task
        loop = asyncio.get_event_loop()
        self._claim_task = loop.create_task(self._claim_loop())

        while self._running:
            try:
                res = await self._client.xreadgroup(self.group, self.consumer, {self.stream: '>'}, count=count, block=block_ms)
                if not res:
                    continue
                for stream, messages in res:
                    for msg_id, fields in messages:
                        raw = fields.get(b'raw') or fields.get('raw')
                        if isinstance(raw, bytes):
                            raw = raw.decode()
                        try:
                            event = json.loads(raw)
                        except Exception:
                            event = {"raw": raw}
                        try:
                            await handler(event)
                            # ack on success
                            await self._client.xack(self.stream, self.group, msg_id)
                        except Exception as e:
                            logger.exception(f"Handler failed for message {msg_id}: {e}")
                            # do not ack so it remains pending for claim/retry
            except Exception as e:
                logger.exception(f"RedisStreams consumer loop error: {e}")
                await asyncio.sleep(1.0)

    def stop(self):
        self._running = False
        if self._claim_task and not self._claim_task.done():
            self._claim_task.cancel()

    async def _claim_loop(self):
        """Periodically inspect PEL and claim or move messages to DLQ."""
        if not HAS_REDIS:
            return
        while self._running:
            try:
                # Use XAUTOCLAIM if available (Redis >= 6.2). It returns (next_id, messages)
                try:
                    res = await self._client.xautoclaim(self.stream, self.group, self.consumer, self.idle_threshold_ms, '-', count=100)
                    # res: (next_id, [(id, {field: value}), ...])
                    _, messages = res
                except AttributeError:
                    # Fallback: use XPENDING to get summary then XCLAIM
                    try:
                        pend = await self._client.xpending(self.stream, self.group)
                        # pend may be a dict in some clients; we will use XPENDING RANGE instead
                        messages = []
                        rng = await self._client.xpending_range(self.stream, self.group, '-', '+', 100)
                        for item in rng:
                            msg_id = item['message_id'] if isinstance(item, dict) else item[0]
                            # XCLAIM the message to self.consumer
                            try:
                                claimed = await self._client.xclaim(self.stream, self.group, self.consumer, self.idle_threshold_ms, msg_id, idle=None, retrycount=None)
                                # claimed similar to [(id, {field: value})]
                                for mid, fields in claimed:
                                    messages.append((mid, fields))
                            except Exception:
                                continue
                    except Exception:
                        messages = []

                for msg_id, fields in messages:
                    # extract delivery count if present
                    # some clients include 'delivery_count' metadata; otherwise use XPENDING info
                    delivery_count = None
                    try:
                        # fields may be dict with bytes keys
                        raw = fields.get(b'raw') if isinstance(fields, dict) else fields.get('raw')
                        if isinstance(raw, bytes):
                            raw = raw.decode()
                        try:
                            event = json.loads(raw)
                        except Exception:
                            event = {"raw": raw}
                    except Exception:
                        event = {"raw": None}

                    # get delivery count via XPENDING RANGE for this id
                    try:
                        pend_info = await self._client.xpending_range(self.stream, self.group, msg_id, msg_id, 1)
                        if pend_info:
                            info = pend_info[0]
                            # info format may vary; try common positions
                            if isinstance(info, dict):
                                delivery_count = int(info.get('times_delivered') or info.get('delivery_count') or 0)
                            else:
                                # tuple: [message_id, consumer, idle_time, deliveries]
                                delivery_count = int(info[-1])
                    except Exception:
                        delivery_count = None

                    if delivery_count is not None and delivery_count >= self.max_delivery_count:
                        # move to DLQ (XADD) and ACK original
                        try:
                            raw_field = fields.get(b'raw') if isinstance(fields, dict) else fields.get('raw')
                            if isinstance(raw_field, bytes):
                                raw_field = raw_field.decode()
                            await self._client.xadd(self.dlq_stream, {"raw": raw_field})
                            await self._client.xack(self.stream, self.group, msg_id)
                            logger.warning(f"Moved message {msg_id} to DLQ {self.dlq_stream} after {delivery_count} deliveries")
                        except Exception as e:
                            logger.exception(f"Failed to move message {msg_id} to DLQ: {e}")
                    else:
                        # try to claim and re-dispatch to same consumer (we can call handler directly if desired)
                        try:
                            claimed = None
                            try:
                                claimed = await self._client.xautoclaim(self.stream, self.group, self.consumer, self.idle_threshold_ms, msg_id, count=1)
                                # claimed structure: (next_id, [(id, fields), ...])
                            except Exception:
                                # fallback to XCLAIM
                                claimed = await self._client.xclaim(self.stream, self.group, self.consumer, self.idle_threshold_ms, msg_id)

                            # process claimed messages: we will fetch raw and attempt handler processing by publishing to the in-process queue
                            # For simplicity, just leave claimed messages for the main consumer loop which reads from '>'
                        except Exception as e:
                            logger.exception(f"Failed to claim message {msg_id}: {e}")

                await asyncio.sleep(self.claim_interval_sec)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Claim loop error: {e}")
                await asyncio.sleep(self.claim_interval_sec)
