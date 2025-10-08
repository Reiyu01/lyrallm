"""Postgres client for token usage persistence.

This module uses asyncpg when available. If asyncpg is not installed
we provide a lightweight stub client so the rest of the application
can run without hard failure (consumer will log write attempts).
"""
import asyncio
import logging
from typing import Optional
from datetime import datetime
from lyrallm.config.config_manager import config_manager

logger = logging.getLogger(__name__)

HAS_ASYNCPG = True
try:
    import asyncpg
except Exception:
    HAS_ASYNCPG = False
    asyncpg = None  # type: ignore


class PostgresClient:
    def __init__(self, dsn: Optional[str] = None):
        cfg = config_manager.config.get('database', {})
        self._dsn = dsn or cfg.get('dsn') or cfg.get('url')
        self._pool = None

    async def connect(self):
        if not HAS_ASYNCPG:
            logger.warning("asyncpg not installed; Postgres client is a no-op")
            return
        if self._pool:
            return
        if not self._dsn:
            raise RuntimeError("Postgres DSN not configured in config.yaml under 'database' or passed directly")
        self._pool = await asyncpg.create_pool(dsn=self._dsn)
        await self._ensure_table()

    async def close(self):
        if not HAS_ASYNCPG:
            return
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def _ensure_table(self):
        if not HAS_ASYNCPG:
            return
        sql = """
        CREATE TABLE IF NOT EXISTS token_usage (
            id SERIAL PRIMARY KEY,
            request_id TEXT NOT NULL,
            timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
            model_name TEXT NOT NULL,
            prompt_tokens INTEGER NOT NULL,
            completion_tokens INTEGER NOT NULL,
            total_tokens INTEGER NOT NULL,
            cost_usd NUMERIC(18,8) NOT NULL,
            user_id TEXT,
            endpoint TEXT,
            status TEXT,
            raw JSONB,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        );
        """
        async with self._pool.acquire() as conn:
            await conn.execute(sql)

    async def insert_token_usage(self, token_usage: dict):
        """Insert a token usage dict into the token_usage table.

        If asyncpg is not installed this becomes a logged no-op so the
        producer (SK) doesn't fail.
        """
        if not HAS_ASYNCPG:
            logger.info("[Postgres stub] insert_token_usage called (asyncpg missing). Event: %s", {"request_id": token_usage.get('request_id')})
            return

        if not self._pool:
            await self.connect()

        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO token_usage(request_id, timestamp, model_name, prompt_tokens,
                    completion_tokens, total_tokens, cost_usd, user_id, endpoint, status, raw)
                VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """,
                token_usage.get('request_id'),
                token_usage.get('timestamp'),
                token_usage.get('model_name'),
                int(token_usage.get('prompt_tokens', 0)),
                int(token_usage.get('completion_tokens', 0)),
                int(token_usage.get('total_tokens', 0)),
                float(token_usage.get('cost_usd', 0.0)),
                token_usage.get('user_id'),
                token_usage.get('endpoint'),
                token_usage.get('status'),
                token_usage,
            )


# Singleton instance
_pg_client: Optional[PostgresClient] = None


def get_postgres_client() -> PostgresClient:
    global _pg_client
    if _pg_client is None:
        _pg_client = PostgresClient()
    return _pg_client


async def postgres_health() -> dict:
    """Return a small health summary for Postgres client. Non-blocking if pool exists."""
    pg = get_postgres_client()
    try:
        # if asyncpg not installed, report disconnected
        if not HAS_ASYNCPG:
            return {"connected": False, "reason": "asyncpg_missing"}
        # if pool exists, try a simple query
        if getattr(pg, '_pool', None):
            async with pg._pool.acquire() as conn:
                await conn.fetchrow('SELECT 1')
            return {"connected": True}
        else:
            # Not connected yet
            return {"connected": False, "reason": "not_initialized"}
    except Exception as e:
        return {"connected": False, "reason": str(e)}
