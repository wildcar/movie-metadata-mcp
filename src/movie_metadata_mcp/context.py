"""Application-wide runtime context.

Holds the three upstream clients and the SQLite cache. Constructed once at
server startup via :func:`build_app_context` and torn down at shutdown.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from .cache import SQLiteCache
from .clients import OMDbClient, PoiskkinoClient, TMDBClient
from .config import Settings


@dataclass
class AppContext:
    """Bundle of long-lived resources shared by the two tools."""

    settings: Settings
    tmdb: TMDBClient | None
    omdb: OMDbClient | None
    poiskkino: PoiskkinoClient | None
    cache: SQLiteCache

    async def aclose(self) -> None:
        for client in (self.tmdb, self.omdb, self.poiskkino):
            if client is not None:
                await client.aclose()
        await self.cache.close()


@asynccontextmanager
async def build_app_context(settings: Settings) -> AsyncIterator[AppContext]:
    """Create an :class:`AppContext` whose lifetime is bounded by the ``async with``.

    Upstream clients are only instantiated when their token is present; tools
    check for ``None`` and record the missing provider under ``sources_failed``.
    """

    cache = SQLiteCache(settings.cache_path)
    await cache.open()

    tmdb = TMDBClient(settings.tmdb_api_token) if settings.tmdb_api_token else None
    omdb = OMDbClient(settings.omdb_api_key) if settings.omdb_api_key else None
    poiskkino = (
        PoiskkinoClient(settings.poiskkino_dev_token) if settings.poiskkino_dev_token else None
    )

    ctx = AppContext(
        settings=settings,
        tmdb=tmdb,
        omdb=omdb,
        poiskkino=poiskkino,
        cache=cache,
    )
    try:
        yield ctx
    finally:
        await ctx.aclose()
