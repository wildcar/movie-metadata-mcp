"""SQLite-backed TTL cache.

A single ``cache`` table stores JSON-encoded values keyed by a canonical
``tool:args`` string. Expiration is lazy: expired rows are only removed when
they are looked up (and occasionally during ``set``). This keeps the cache
cheap — we never run a scheduled sweeper.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key        TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    expires_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cache_expires_at ON cache(expires_at);
"""


class SQLiteCache:
    """Async SQLite cache with per-entry TTL.

    Instances are constructed synchronously but must be opened via ``open()``
    before use (to create the parent directory and run schema migration).
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path)
        await self._conn.executescript(_SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ---------------------------------------------------------------

    @staticmethod
    def make_key(tool: str, args: dict[str, Any]) -> str:
        """Build a stable cache key from a tool name and its arguments.

        ``args`` is serialized with sorted keys so the key is deterministic
        regardless of the dict ordering at the call site.
        """

        return f"{tool}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}"

    async def get(self, key: str) -> dict[str, Any] | None:
        """Return a cached value or ``None`` if missing / expired.

        Expired entries are removed opportunistically on read.
        """

        conn = self._require_conn()
        now = time.time()
        async with conn.execute(
            "SELECT value_json, expires_at FROM cache WHERE key = ?", (key,)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        value_json, expires_at = row
        if expires_at <= now:
            await conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            await conn.commit()
            return None
        loaded: dict[str, Any] = json.loads(value_json)
        return loaded

    async def set(self, key: str, value: dict[str, Any], ttl_seconds: int) -> None:
        """Upsert ``value`` into the cache with a TTL in seconds."""

        conn = self._require_conn()
        expires_at = time.time() + ttl_seconds
        await conn.execute(
            "INSERT OR REPLACE INTO cache (key, value_json, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(value, ensure_ascii=False), expires_at),
        )
        await conn.commit()

    async def purge_expired(self) -> int:
        """Remove all expired rows. Returns the count removed."""

        conn = self._require_conn()
        now = time.time()
        cur = await conn.execute("DELETE FROM cache WHERE expires_at <= ?", (now,))
        await conn.commit()
        return cur.rowcount or 0

    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("SQLiteCache used before open() or after close()")
        return self._conn
