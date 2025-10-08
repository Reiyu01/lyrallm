from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class PostgresAdapter:
    def __init__(self, dsn: Optional[str] = None):
        from logger_service.db_client import get_postgres_client
        self._pg = get_postgres_client()
        self._dsn = dsn

    async def connect(self):
        try:
            await self._pg.connect()
        except Exception as e:
            logger.exception(f"PostgresAdapter connect failed: {e}")

    async def close(self):
        try:
            await self._pg.close()
        except Exception:
            pass

    async def write_token_usage(self, event: Dict[str, Any]):
        return await self._pg.insert_token_usage(event)

    async def query_token_usage(self, limit: int = 10):
        # simple helper; not optimized
        if not getattr(self._pg, '_pool', None):
            await self.connect()
        async with self._pg._pool.acquire() as conn:
            rows = await conn.fetch(f"SELECT * FROM token_usage ORDER BY created_at DESC LIMIT {int(limit)}")
            return [dict(r) for r in rows]
