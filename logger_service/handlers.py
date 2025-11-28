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
    """Handler that persists token usage via the configured analytics adapter."""
    background = True  # 改為 True，避免阻塞主請求響應

    def __init__(self):
        # use adapter factory for pluggable backends (Postgres / Elasticsearch / etc.)
        from lyrallm.adapters.factory import get_adapter
        self._adapter = get_adapter('analytics')
        logger.info(f"DbHandler initialized with adapter: {self._adapter.__class__.__name__}")

    async def handle(self, event: Dict[str, Any]):
        try:
            await self._adapter.connect()
            await self._adapter.write_token_usage(event)
            logger.info(f"DbHandler wrote request_id={event.get('request_id')} to analytics store")
            return True
        except Exception as e:
            logger.exception(f"DbHandler failed to insert event: {e}")
            return False


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
    cfg = config_manager.config
    handlers: List[BaseHandler] = []

    # Database/analytics handler (uses adapter factory, picks Postgres or Elasticsearch)
    db_cfg = cfg.get('database', {}) or {}
    storages_cfg = cfg.get('storages', {}) or {}
    analytics_cfg = storages_cfg.get('analytics', {}) or {}
    analytics_type = (analytics_cfg.get('type') or analytics_cfg.get('adapter') or analytics_cfg.get('backend') or '').lower()
    
    # 性能優化：檢查是否禁用 analytics（用於測試）
    analytics_enabled = analytics_cfg.get('enabled', True) if analytics_cfg else (bool(db_cfg) or bool(analytics_type))
    
    logger.info(f"Logger handlers init - analytics_enabled={analytics_enabled} database_cfg_present={bool(db_cfg)} analytics_cfg={analytics_cfg} analytics_type={analytics_type}")

    if analytics_enabled and (db_cfg or analytics_cfg or analytics_type):
        # Adapter factory will route to Postgres or Elasticsearch depending on config
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
