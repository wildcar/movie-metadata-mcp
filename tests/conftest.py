"""Shared fixtures for movie-metadata-mcp tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from movie_metadata_mcp.cache import SQLiteCache
from movie_metadata_mcp.clients import OMDbClient, PoiskkinoClient, TMDBClient
from movie_metadata_mcp.config import Settings
from movie_metadata_mcp.context import AppContext


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """A Settings instance with dummy credentials and a per-test cache path."""

    return Settings(
        tmdb_api_token="test-tmdb-token",
        omdb_api_key="test-omdb-key",
        poiskkino_dev_token="test-poiskkino-token",
        cache_path=str(tmp_path / "cache.sqlite"),
        cache_ttl_search_seconds=3600,
        cache_ttl_details_seconds=86_400,
    )


@pytest_asyncio.fixture
async def opened_cache(settings: Settings) -> AsyncIterator[SQLiteCache]:
    cache = SQLiteCache(settings.cache_path)
    await cache.open()
    try:
        yield cache
    finally:
        await cache.close()


@pytest_asyncio.fixture
async def app_ctx(settings: Settings) -> AsyncIterator[AppContext]:
    """AppContext built with real clients pointed at real base URLs.

    Tests mock the HTTP layer with ``respx``; the clients' own lifecycle is
    exercised as a side benefit.
    """

    cache = SQLiteCache(settings.cache_path)
    await cache.open()
    assert settings.tmdb_api_token is not None
    assert settings.omdb_api_key is not None
    assert settings.poiskkino_dev_token is not None
    ctx = AppContext(
        settings=settings,
        tmdb=TMDBClient(settings.tmdb_api_token),
        omdb=OMDbClient(settings.omdb_api_key),
        poiskkino=PoiskkinoClient(settings.poiskkino_dev_token),
        cache=cache,
    )
    try:
        yield ctx
    finally:
        await ctx.aclose()
