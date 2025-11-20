import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse

logger = logging.getLogger(__name__)

HAS_AIOMYSQL = True
try:
    import aiomysql
except Exception:  # pragma: no cover - optional dependency
    HAS_AIOMYSQL = False
    aiomysql = None  # type: ignore


WINDOW_INTERVAL_SECONDS = 300


class MySQLAdapter:
    """Async adapter for aggregated token usage accounting in MySQL."""

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

        user_id = event.get("user_id")
        if not user_id:
            logger.debug("MySQLAdapter.write_token_usage skipped: missing user_id")
            return

        prompt_tokens = self._as_int(event.get("prompt_tokens"))
        completion_tokens = self._as_int(event.get("completion_tokens"))
        total_tokens = self._as_int(event.get("total_tokens"))
        if total_tokens == 0:
            # fall back to sum in case caller omitted total but provided parts
            total_tokens = prompt_tokens + completion_tokens

        if total_tokens <= 0:
            logger.debug(
                "MySQLAdapter.write_token_usage skipped: zero tokens (user_id=%s)",
                user_id,
            )
            return

        now = self._normalize_timestamp(event.get("timestamp"))

        await self._ensure_schema()

        async with self._pool.acquire() as conn:
            await conn.begin()
            try:
                async with conn.cursor(aiomysql.DictCursor) as cur:  # type: ignore[attr-defined]
                    row = await self._fetch_window_for_update(cur, user_id)
                    row, _ = await self._roll_window_if_needed(cur, user_id, row, now)

                    if row is None:
                        await self._insert_new_window(
                            cur,
                            user_id,
                            now,
                            prompt_tokens,
                            completion_tokens,
                            total_tokens,
                        )
                    else:
                        await self._increment_window(
                            cur,
                            user_id,
                            prompt_tokens,
                            completion_tokens,
                            total_tokens,
                        )
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

    async def query_token_usage(self, limit: int = 10) -> List[Dict[str, Any]]:
        if not HAS_AIOMYSQL:
            return []
        if not self._pool:
            await self.connect()
        if not self._pool:
            return []
        sql = (
            "SELECT user_id, interval_start, interval_end, "
            "prompt_tokens, completion_tokens, total_tokens, created_at "
            "FROM token_usage_aggregate ORDER BY interval_end DESC LIMIT %s"
        )
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

        stmts = [
            (
                "CREATE TABLE IF NOT EXISTS token_usage_window ("
                "user_id VARCHAR(191) PRIMARY KEY,"
                "interval_start DATETIME(6) NOT NULL,"
                "next_cutoff DATETIME(6) NOT NULL,"
                "accum_prompt_tokens INT NOT NULL DEFAULT 0,"
                "accum_completion_tokens INT NOT NULL DEFAULT 0,"
                "accum_total_tokens INT NOT NULL DEFAULT 0,"
                "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
                "KEY idx_token_usage_window_cutoff (next_cutoff)"
                ") ENGINE=InnoDB"
            ),
            (
                "CREATE TABLE IF NOT EXISTS token_usage_aggregate ("
                "id BIGINT AUTO_INCREMENT PRIMARY KEY,"
                "user_id VARCHAR(191) NOT NULL,"
                "interval_start DATETIME(6) NOT NULL,"
                "interval_end DATETIME(6) NOT NULL,"
                "prompt_tokens INT NOT NULL,"
                "completion_tokens INT NOT NULL,"
                "total_tokens INT NOT NULL,"
                "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
                "KEY idx_token_usage_aggregate_user (user_id, interval_start),"
                "KEY idx_token_usage_aggregate_end (interval_end)"
                ") ENGINE=InnoDB"
            ),
            (
                "CREATE TABLE IF NOT EXISTS user_quota ("
                "user_id VARCHAR(191) PRIMARY KEY,"
                "allocated_tokens BIGINT NOT NULL DEFAULT 0,"
                "remaining_tokens BIGINT NOT NULL DEFAULT 0,"
                "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
                ") ENGINE=InnoDB"
            ),
        ]

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                for sql in stmts:
                    await cur.execute(sql)
            await conn.commit()
        self._schema_ensured = True

    @staticmethod
    def _as_int(value: Any) -> int:
        try:
            return int(value)
        except Exception:
            return 0

    @staticmethod
    def _normalize_timestamp(value: Any) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                value = value.astimezone(timezone.utc)
            return value.replace(tzinfo=None)
        if value:
            try:
                parsed = datetime.fromisoformat(str(value))
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                return parsed
            except Exception:
                pass
        return datetime.utcnow()

    async def flush_due_windows(self, now: Optional[datetime] = None, batch_size: int = 100) -> int:
        """Flush all windows whose cutoff has passed.

        Returns the number of aggregate rows written.
        """

        if not HAS_AIOMYSQL:
            return 0
        if not self._pool:
            await self.connect()
        if not self._pool:
            return 0
        await self._ensure_schema()

        current = self._normalize_timestamp(now)
        written = 0

        async with self._pool.acquire() as conn:
            await conn.begin()
            try:
                async with conn.cursor(aiomysql.DictCursor) as cur:  # type: ignore[attr-defined]
                    await cur.execute(
                        "SELECT user_id, interval_start, next_cutoff, "
                        "accum_prompt_tokens, accum_completion_tokens, accum_total_tokens "
                        "FROM token_usage_window "
                        "WHERE next_cutoff <= %s "
                        "ORDER BY next_cutoff ASC LIMIT %s FOR UPDATE",
                        (current, int(batch_size)),
                    )
                    rows = await cur.fetchall()
                    for row in rows:
                        _, flushed = await self._roll_window_if_needed(
                            cur, row["user_id"], row, current
                        )
                        written += flushed
                await conn.commit()
            except Exception:
                await conn.rollback()
                raise

        return written

    async def _fetch_window_for_update(self, cur: Any, user_id: str) -> Optional[Dict[str, Any]]:
        await cur.execute(
            "SELECT user_id, interval_start, next_cutoff, accum_prompt_tokens, "
            "accum_completion_tokens, accum_total_tokens "
            "FROM token_usage_window WHERE user_id = %s FOR UPDATE",
            (user_id,),
        )
        return await cur.fetchone()

    async def _roll_window_if_needed(
        self,
        cur: Any,
        user_id: str,
        row: Optional[Dict[str, Any]],
        current_time: datetime,
    ) -> Tuple[Optional[Dict[str, Any]], int]:
        if row is None:
            return None, 0

        interval = timedelta(seconds=WINDOW_INTERVAL_SECONDS)
        interval_start = self._normalize_timestamp(row["interval_start"])
        next_cutoff = self._normalize_timestamp(row["next_cutoff"])
        prompt = self._as_int(row.get("accum_prompt_tokens"))
        completion = self._as_int(row.get("accum_completion_tokens"))
        total = self._as_int(row.get("accum_total_tokens"))
        flushed = 0
        dirty = False

        while current_time >= next_cutoff:
            if total > 0:
                await cur.execute(
                    "INSERT INTO token_usage_aggregate "
                    "(user_id, interval_start, interval_end, prompt_tokens, completion_tokens, total_tokens) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (user_id, interval_start, next_cutoff, prompt, completion, total),
                )
                flushed += 1
                interval_start = next_cutoff
                next_cutoff = interval_start + interval
                prompt = 0
                completion = 0
                total = 0
                dirty = True
            else:
                await cur.execute(
                    "DELETE FROM token_usage_window WHERE user_id = %s",
                    (user_id,),
                )
                return None, flushed

        if dirty:
            await cur.execute(
                "UPDATE token_usage_window SET interval_start = %s, next_cutoff = %s, "
                "accum_prompt_tokens = %s, accum_completion_tokens = %s, accum_total_tokens = %s "
                "WHERE user_id = %s",
                (interval_start, next_cutoff, prompt, completion, total, user_id),
            )

        return (
            {
                "user_id": user_id,
                "interval_start": interval_start,
                "next_cutoff": next_cutoff,
                "accum_prompt_tokens": prompt,
                "accum_completion_tokens": completion,
                "accum_total_tokens": total,
            },
            flushed,
        )

    async def _insert_new_window(
        self,
        cur: Any,
        user_id: str,
        start_time: datetime,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ) -> None:
        cutoff = start_time + timedelta(seconds=WINDOW_INTERVAL_SECONDS)
        await cur.execute(
            "INSERT INTO token_usage_window (user_id, interval_start, next_cutoff, "
            "accum_prompt_tokens, accum_completion_tokens, accum_total_tokens) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, start_time, cutoff, prompt_tokens, completion_tokens, total_tokens),
        )

    async def _increment_window(
        self,
        cur: Any,
        user_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ) -> None:
        await cur.execute(
            "UPDATE token_usage_window SET "
            "accum_prompt_tokens = accum_prompt_tokens + %s, "
            "accum_completion_tokens = accum_completion_tokens + %s, "
            "accum_total_tokens = accum_total_tokens + %s "
            "WHERE user_id = %s",
            (prompt_tokens, completion_tokens, total_tokens, user_id),
        )


__all__ = ["MySQLAdapter"]
