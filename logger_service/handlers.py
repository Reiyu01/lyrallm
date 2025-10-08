import asyncio
import logging
from typing import List, Dict, Any
from lyrallm.config.config_manager import config_manager

logger = logging.getLogger(__name__)


class BaseHandler:
    """Abstract handler for processing token usage events."""
    background = False  # if True, consumer will schedule as fire-and-forget

    async def handle(self, event: Dict[str, Any]):
        raise NotImplementedError()


class DbHandler(BaseHandler):
    """Handler that writes token usage to Postgres using existing db_client."""
    background = False

    def __init__(self):
        # use adapter factory for pluggable backends
    from lyrallm.adapters.factory import get_adapter
        self._adapter = get_adapter('analytics')

    async def handle(self, event: Dict[str, Any]):
        try:
            await self._adapter.connect()
            await self._adapter.write_token_usage(event)
            logger.debug(f"DbHandler: inserted request_id={event.get('request_id')}")
            return True
        except Exception as e:
            logger.exception(f"DbHandler failed to insert event: {e}")
            return False


class HttpForwardHandler(BaseHandler):
    """Handler that forwards events via HTTP POST with retries (uses http_forwarder.post_json)."""
    background = True

    def __init__(self, url: str):
        from logger_service.http_forwarder import post_json
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
        from logger_service.http_forwarder import post_udp
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
    cfg = config_manager.config
    handlers: List[BaseHandler] = []

    # Database handler (if database configured)
    db_cfg = cfg.get('database', {})
    if db_cfg:
        # For now we only have a Postgres handler; if type key is added later we can branch
        handlers.append(DbHandler())

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

    return handlers
