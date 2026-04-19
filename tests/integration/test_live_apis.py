"""End-to-end tests that hit the real TMDB / OMDb / poiskkino.dev.

Opt-in: marked with ``@pytest.mark.integration``. Skipped automatically when
any credential is missing, so CI (which runs ``-m "not integration"``)
never reaches them.

Run locally with:
    uv run pytest -m integration
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from movie_metadata_mcp.cache import SQLiteCache
from movie_metadata_mcp.clients import OMDbClient, PoiskkinoClient, TMDBClient
from movie_metadata_mcp.config import get_settings
from movie_metadata_mcp.context import AppContext
from movie_metadata_mcp.tools import get_movie_details_impl, search_movie_impl

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def live_ctx(tmp_path: Path) -> AsyncIterator[AppContext]:
    settings = get_settings()
    missing = [
        name
        for name, val in (
            ("TMDB_API_TOKEN", settings.tmdb_api_token),
            ("OMDB_API_KEY", settings.omdb_api_key),
            ("POISKKINO_DEV_TOKEN", settings.poiskkino_dev_token),
        )
        if not val
    ]
    if missing:
        pytest.skip(f"Missing credentials: {', '.join(missing)}")

    assert settings.tmdb_api_token and settings.omdb_api_key and settings.poiskkino_dev_token

    cache = SQLiteCache(str(tmp_path / "integration-cache.sqlite"))
    await cache.open()

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


async def test_search_movie_live(live_ctx: AppContext) -> None:
    resp = await search_movie_impl(live_ctx, "Dune", year=2021)
    assert resp.error is None, resp.error
    assert len(resp.results) > 0
    top = resp.results[0]
    assert top.imdb_id == "tt1160419"
    assert top.tmdb_id == 438631
    assert top.year == 2021
    assert top.poster_url and top.poster_url.startswith("https://image.tmdb.org/")


async def test_get_movie_details_live(live_ctx: AppContext) -> None:
    resp = await get_movie_details_impl(live_ctx, "tt1160419")
    assert resp.error is None, resp.error
    assert resp.details is not None
    d = resp.details
    assert d.imdb_id == "tt1160419"
    assert d.title.lower().startswith("dune")
    assert d.year == 2021
    assert d.runtime_minutes and d.runtime_minutes > 100
    assert "Denis Villeneuve" in d.directors
    assert d.overview
    # At least one provider returned the Russian plot.
    assert d.overview_ru
    # All three rating sources expected for a well-known title.
    rating_sources = {r.source for r in d.ratings}
    assert {"tmdb", "imdb", "kinopoisk"}.issubset(rating_sources)
