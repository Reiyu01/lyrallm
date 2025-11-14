import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

logger = logging.getLogger(__name__)

HAS_AIOMYSQL = True
try:
    import aiomysql
except Exception:  # pragma: no cover - optional dependency
    HAS_AIOMYSQL = False
    aiomysql = None  # type: ignore


class MySQLAdapter:
    """Async adapter for writing token usage events into MySQL."""

    def __init__(self, dsn: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        self._dsn = dsn
        self._config = config or {}
        self._pool: Optional[Any] = None
        self._schema_ensured = False

    async def connect(self):
        if not HAS_AIOMYSQL:
            logger.warning("aiomysql not installed; MySQL adapter disabled")
            return
        if self._pool:
            return
        params = self._build_pool_params()
        try:
            self._pool = await aiomysql.create_pool(**params)
            await self._ensure_schema()
        except Exception as exc:
            logger.exception("MySQLAdapter connect failed: %s", exc)
            raise

    async def close(self):
        if not HAS_AIOMYSQL:
            return
        if self._pool:
            self._pool.close()
            try:
                await self._pool.wait_closed()
            except Exception:
                pass
            self._pool = None
            self._schema_ensured = False

    async def write_token_usage(self, event: Dict[str, Any]):
        if not HAS_AIOMYSQL:
            logger.info("[MySQL stub] insert_token_usage called (aiomysql missing). Event: %s", {"request_id": event.get("request_id")})
            return
        if not self._pool:
            await self.connect()
        if not self._pool:
            return
        await self._ensure_schema()

        ts = event.get("timestamp")
        if isinstance(ts, datetime):
            if ts.tzinfo is not None:
                ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
        elif ts:
            try:
                ts = datetime.fromisoformat(str(ts))
            except Exception:
                ts = datetime.utcnow()
        else:
            ts = datetime.utcnow()

        payload = (
            event.get("request_id"),
            ts,
            event.get("model_name"),
            int(event.get("prompt_tokens", 0)),
            int(event.get("completion_tokens", 0)),
            int(event.get("total_tokens", 0)),
            float(event.get("cost_usd", 0.0)),
            event.get("user_id"),
            event.get("endpoint"),
            event.get("status"),
            json.dumps(event, default=str),
        )

        sql = (
            "INSERT INTO token_usage("
            "request_id, timestamp, model_name, prompt_tokens, completion_tokens, "
            "total_tokens, cost_usd, user_id, endpoint, status, raw) "
            "VALUES(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, payload)
            await conn.commit()

    async def query_token_usage(self, limit: int = 10) -> List[Dict[str, Any]]:
        if not HAS_AIOMYSQL:
            return []
        if not self._pool:
            await self.connect()
        if not self._pool:
            return []
        sql = "SELECT * FROM token_usage ORDER BY created_at DESC LIMIT %s"
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:  # type: ignore[attr-defined]
                await cur.execute(sql, (int(limit),))
                rows = await cur.fetchall()
                return [dict(row) for row in rows]

    def _build_pool_params(self) -> Dict[str, Any]:
        params: Dict[str, Any] = {"autocommit": True}

        cfg_host = self._config.get("host")
        if cfg_host:
            params["host"] = cfg_host
        cfg_port = self._config.get("port")
        if cfg_port:
            params["port"] = int(cfg_port)
        cfg_user = self._config.get("user") or self._config.get("username")
        if cfg_user:
            params["user"] = cfg_user
        cfg_password = self._config.get("password")
        if cfg_password is not None:
            params["password"] = cfg_password
        cfg_db = self._config.get("database") or self._config.get("db")
        if cfg_db:
            params["db"] = cfg_db

        if self._dsn:
            parsed = urlparse(self._dsn)
            scheme = (parsed.scheme or "").lower()
            if scheme and not scheme.startswith("mysql"):
                raise ValueError(f"Unsupported MySQL DSN scheme: {parsed.scheme}")
            if parsed.hostname:
                params["host"] = parsed.hostname
            if parsed.port:
                params["port"] = parsed.port
            if parsed.username:
                params["user"] = unquote(parsed.username)
            if parsed.password:
                params["password"] = unquote(parsed.password)
            if parsed.path and parsed.path != "/":
                params["db"] = parsed.path.lstrip("/")
            if parsed.query:
                extras = parse_qs(parsed.query, keep_blank_values=True)
                for key, value in extras.items():
                    if not value:
                        continue
                    params[key] = value[-1]

        params.setdefault("host", "127.0.0.1")
        params.setdefault("port", 3306)
        if "user" not in params or "db" not in params:
            raise ValueError("MySQL connection requires user and database")
        return params

    async def _ensure_schema(self):
        if self._schema_ensured or not self._pool:
            return
        sql = (
            "CREATE TABLE IF NOT EXISTS token_usage ("
            "id BIGINT AUTO_INCREMENT PRIMARY KEY,"
            "request_id VARCHAR(191) NOT NULL,"
            "timestamp DATETIME(6) NOT NULL,"
            "model_name VARCHAR(191) NOT NULL,"
            "prompt_tokens INT NOT NULL,"
            "completion_tokens INT NOT NULL,"
            "total_tokens INT NOT NULL,"
            "cost_usd DECIMAL(18,8) NOT NULL,"
            "user_id VARCHAR(191),"
            "endpoint VARCHAR(191),"
            "status VARCHAR(64),"
            "raw JSON,"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "KEY idx_token_usage_request_id (request_id),"
            "KEY idx_token_usage_timestamp (timestamp)"
            ")"
        )
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql)
            await conn.commit()
        self._schema_ensured = True


__all__ = ["MySQLAdapter"]
