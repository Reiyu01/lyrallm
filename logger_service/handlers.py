import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from lyrallm.config.config_manager import config_manager

logger = logging.getLogger(__name__)

_HANDLERS_CACHE: Optional[List["BaseHandler"]] = None


class BaseHandler:
    """Abstract handler for processing token usage events."""
    background = False  # if True, consumer will schedule as fire-and-forget

    async def handle(self, event: Dict[str, Any]):
        raise NotImplementedError()


class DbHandler(BaseHandler):
    """Handler that writes token usage to configured analytics storage."""
    background = False

    def __init__(self, adapter: Any):
        self._adapter = adapter

    async def handle(self, event: Dict[str, Any]):
        try:
            if hasattr(self._adapter, 'connect'):
                await self._adapter.connect()
            await self._adapter.write_token_usage(event)
            logger.info(f"DbHandler wrote request_id={event.get('request_id')} to analytics store")
            return True
        except Exception as e:
            logger.exception(f"DbHandler failed to insert event: {e}")
            return False

    async def flush(self, now: Optional[datetime] = None, batch_size: int = 100) -> int:
        flush_fn = getattr(self._adapter, 'flush_due_windows', None)
        if flush_fn is None:
            return 0

        try:
            if hasattr(self._adapter, 'connect'):
                await self._adapter.connect()

            kwargs = {'batch_size': batch_size}
            if now is not None:
                kwargs['now'] = now

            try:
                return await flush_fn(**kwargs)
            except TypeError:
                kwargs.pop('batch_size', None)
                if kwargs:
                    return await flush_fn(**kwargs)
                return await flush_fn()
        except Exception as exc:
            logger.exception(f"DbHandler flush failed: {exc}")
            return 0


class HttpForwardHandler(BaseHandler):
    """Handler that forwards events via HTTP POST with retries (uses http_forwarder.post_json)."""
    background = True

    def __init__(self, url: str):
        from .http_forwarder import post_json
        self._url = url
        self._post = post_json

    async def handle(self, event: Dict[str, Any]):
        try:
            ok = await self._post(self._url, event)
            logger.debug(f"HttpForwardHandler: forwarded request_id={event.get('request_id')} ok={ok}")
            return ok
        except Exception as e:
            logger.exception(f"HttpForwardHandler failed: {e}")
            return False


class UdpForwardHandler(BaseHandler):
    """Handler that forwards events via UDP (best-effort)."""
    background = True

    def __init__(self, host: str, port: int):
        from .http_forwarder import post_udp
        self._host = host
        self._port = int(port)
        self._post_udp = post_udp

    async def handle(self, event: Dict[str, Any]):
        try:
            ok = await self._post_udp(self._host, self._port, event)
            logger.debug(f"UdpForwardHandler: forwarded request_id={event.get('request_id')} ok={ok}")
            return ok
        except Exception as e:
            logger.exception(f"UdpForwardHandler failed: {e}")
            return False


def get_handlers() -> List[BaseHandler]:
    """Create handler instances based on configuration.

    Returns handlers in order where DB handlers come first (so writes happen before forwarding).
    """
    global _HANDLERS_CACHE
    if _HANDLERS_CACHE is not None:
        return _HANDLERS_CACHE

    cfg = config_manager.config
    handlers: List[BaseHandler] = []

    # Database handlers (may be multiple adapters)
    try:
        from lyrallm.adapters.factory import get_adapters

        analytics_adapters = get_adapters('analytics')
        for adapter in analytics_adapters:
            handlers.append(DbHandler(adapter))
    except Exception as exc:
        logger.exception(f"Failed to initialise analytics handlers: {exc}")

    # ELK / forwarder handlers
    elk = cfg.get('elk', {})
    if elk:
        # explicit UDP flag or udp:// scheme
        elk_url = elk.get('http_endpoint') or elk.get('url') or elk.get('http')
        use_udp = elk.get('use_udp') is True
        if isinstance(elk_url, str) and elk_url.startswith('udp://'):
            use_udp = True

        if use_udp:
            # parse udp target
            if isinstance(elk_url, str) and elk_url.startswith('udp://'):
                target = elk_url[len('udp://'):]
            else:
                target = elk.get('udp_target') or f"{elk.get('host','127.0.0.1')}:{elk.get('port',50000)}"
            try:
                host, port = target.split(':')
                handlers.append(UdpForwardHandler(host, int(port)))
            except Exception:
                logger.warning(f"Invalid UDP target in ELK config: {target}")
        else:
            # HTTP forwarder
            url = elk_url or 'http://elk.54ucl.com:50000'
            handlers.append(HttpForwardHandler(url))

    _HANDLERS_CACHE = handlers
    return handlers


def get_db_handlers() -> List[DbHandler]:
    return [h for h in get_handlers() if isinstance(h, DbHandler)]
