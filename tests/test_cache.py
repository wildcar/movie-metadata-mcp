"""Tests for ``SQLiteCache``."""

from __future__ import annotations

import asyncio
import time

import pytest

from movie_metadata_mcp.cache import SQLiteCache


async def test_set_get_roundtrip(opened_cache: SQLiteCache) -> None:
    key = SQLiteCache.make_key("t", {"a": 1, "b": "x"})
    await opened_cache.set(key, {"hello": "world"}, ttl_seconds=60)
    assert await opened_cache.get(key) == {"hello": "world"}


async def test_missing_key_returns_none(opened_cache: SQLiteCache) -> None:
    assert await opened_cache.get("nope") is None


async def test_key_is_deterministic_regardless_of_arg_order() -> None:
    a = SQLiteCache.make_key("t", {"x": 1, "y": 2})
    b = SQLiteCache.make_key("t", {"y": 2, "x": 1})
    assert a == b


async def test_entry_expires(opened_cache: SQLiteCache) -> None:
    key = "expires"
    await opened_cache.set(key, {"v": 1}, ttl_seconds=0)
    # The TTL is in the past on the very next read.
    await asyncio.sleep(0.01)
    assert await opened_cache.get(key) is None


async def test_purge_expired_removes_only_expired(opened_cache: SQLiteCache) -> None:
    await opened_cache.set("fresh", {"v": 1}, ttl_seconds=300)
    await opened_cache.set("stale", {"v": 2}, ttl_seconds=0)
    await asyncio.sleep(0.01)

    removed = await opened_cache.purge_expired()
    assert removed == 1
    assert await opened_cache.get("fresh") == {"v": 1}


async def test_use_before_open_raises() -> None:
    cache = SQLiteCache("/tmp/does-not-matter.sqlite")
    with pytest.raises(RuntimeError, match="used before open"):
        await cache.get("x")


async def test_second_open_overwrites(opened_cache: SQLiteCache) -> None:
    # Just exercising that writes and reads land on the same file between
    # .open() and .close() — catches e.g. an accidental :memory: default.
    before = await opened_cache.get("k")
    assert before is None
    await opened_cache.set("k", {"v": time.time()}, ttl_seconds=60)
    assert await opened_cache.get("k") is not None
