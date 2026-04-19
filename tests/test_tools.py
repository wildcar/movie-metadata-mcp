"""Integration-style tests for tool implementations.

Real client instances are wired into an ``AppContext``; ``respx`` mocks the
HTTP layer so the full code path (tool → client → httpx) is exercised.
"""

from __future__ import annotations

import httpx
import respx

from movie_metadata_mcp.clients.omdb import OMDB_BASE_URL
from movie_metadata_mcp.clients.poiskkino import POISKKINO_BASE_URL
from movie_metadata_mcp.clients.tmdb import TMDB_BASE_URL
from movie_metadata_mcp.context import AppContext
from movie_metadata_mcp.tools import get_movie_details_impl, search_movie_impl

# ---------------------------------------------------------------------------
# search_movie
# ---------------------------------------------------------------------------


async def test_search_movie_populates_imdb_ids(
    app_ctx: AppContext, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{TMDB_BASE_URL}/search/tv").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    respx_mock.get(f"{TMDB_BASE_URL}/search/movie").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 438631,
                        "title": "Dune",
                        "release_date": "2021-09-15",
                        "poster_path": "/abc.jpg",
                        "overview": "Paul Atreides...",
                    },
                    {
                        "id": 693134,
                        "title": "Dune: Part Two",
                        "release_date": "2024-02-27",
                    },
                ]
            },
        )
    )
    respx_mock.get(f"{TMDB_BASE_URL}/movie/438631/external_ids").mock(
        return_value=httpx.Response(200, json={"imdb_id": "tt1160419"})
    )
    respx_mock.get(f"{TMDB_BASE_URL}/movie/693134/external_ids").mock(
        return_value=httpx.Response(200, json={"imdb_id": "tt15239678"})
    )

    resp = await search_movie_impl(app_ctx, "Dune", year=2021)

    assert resp.error is None
    assert [c.imdb_id for c in resp.results] == ["tt1160419", "tt15239678"]
    assert resp.results[0].poster_url == "https://image.tmdb.org/t/p/w500/abc.jpg"
    assert resp.results[0].year == 2021


async def test_search_movie_uses_cache_on_second_call(
    app_ctx: AppContext, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{TMDB_BASE_URL}/search/tv").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    respx_mock.get(f"{TMDB_BASE_URL}/search/movie").mock(
        return_value=httpx.Response(200, json={"results": [{"id": 1, "title": "X"}]})
    )
    respx_mock.get(f"{TMDB_BASE_URL}/movie/1/external_ids").mock(
        return_value=httpx.Response(200, json={"imdb_id": "tt1"})
    )

    await search_movie_impl(app_ctx, "X", year=None)
    await search_movie_impl(app_ctx, "X", year=None)

    # Second call should hit the cache; respx call count stays at 3
    # (/search/movie + /search/tv + /movie/1/external_ids).
    assert len(respx_mock.calls) == 3


async def test_search_movie_rejects_empty_title(app_ctx: AppContext) -> None:
    resp = await search_movie_impl(app_ctx, "   ")
    assert resp.error is not None
    assert resp.error.code == "invalid_argument"


async def test_search_movie_upstream_error_degrades(
    app_ctx: AppContext, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{TMDB_BASE_URL}/search/tv").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    respx_mock.get(f"{TMDB_BASE_URL}/search/movie").mock(
        return_value=httpx.Response(503, text="down")
    )

    resp = await search_movie_impl(app_ctx, "Anything")
    assert resp.error is not None
    assert resp.error.code == "upstream_error"
    assert "tmdb" in resp.sources_failed


# ---------------------------------------------------------------------------
# get_movie_details
# ---------------------------------------------------------------------------


def _stub_tmdb_details(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{TMDB_BASE_URL}/find/tt1160419").mock(
        return_value=httpx.Response(200, json={"movie_results": [{"id": 438631, "title": "Dune"}]})
    )
    respx_mock.get(f"{TMDB_BASE_URL}/movie/438631").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 438631,
                "title": "Dune",
                "original_title": "Dune",
                "release_date": "2021-09-15",
                "runtime": 155,
                "poster_path": "/dune.jpg",
                "overview": "Paul Atreides...",
                "vote_average": 7.8,
                "vote_count": 10000,
                "genres": [{"id": 878, "name": "Science Fiction"}],
                "credits": {
                    "cast": [{"name": "Timothée Chalamet", "order": 0}],
                    "crew": [{"name": "Denis Villeneuve", "job": "Director"}],
                },
            },
        )
    )


def _stub_omdb(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{OMDB_BASE_URL}/").mock(
        return_value=httpx.Response(
            200,
            json={
                "Title": "Dune",
                "Year": "2021",
                "Runtime": "155 min",
                "Genre": "Action, Adventure, Drama",
                "Director": "Denis Villeneuve",
                "Actors": "Timothée Chalamet, Rebecca Ferguson",
                "Plot": "A duke's son leads desert warriors...",
                "imdbRating": "8.0",
                "imdbVotes": "800,000",
                "Metascore": "74",
                "Response": "True",
            },
        )
    )


def _stub_poiskkino(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{POISKKINO_BASE_URL}/v1.4/movie").mock(
        return_value=httpx.Response(
            200,
            json={
                "docs": [
                    {
                        "id": 1318972,
                        "name": "Дюна",
                        "description": "Пол Атрейдес...",
                        "year": 2021,
                        "movieLength": 155,
                        "rating": {"kp": 7.9, "imdb": 8.0},
                        "votes": {"kp": 500000, "imdb": 800000},
                        "poster": {"url": "https://example/kp.jpg"},
                        "genres": [{"name": "фантастика"}],
                    }
                ],
                "total": 1,
                "limit": 1,
            },
        )
    )


async def test_get_movie_details_merges_all_three_sources(
    app_ctx: AppContext, respx_mock: respx.MockRouter
) -> None:
    _stub_tmdb_details(respx_mock)
    _stub_omdb(respx_mock)
    _stub_poiskkino(respx_mock)

    resp = await get_movie_details_impl(app_ctx, "tt1160419")

    assert resp.error is None
    assert resp.sources_failed == []
    d = resp.details
    assert d is not None
    assert d.imdb_id == "tt1160419"
    assert d.tmdb_id == 438631
    assert d.title == "Dune"
    assert d.year == 2021
    assert d.runtime_minutes == 155
    assert d.overview is not None and "Paul Atreides" in d.overview
    assert d.overview_ru == "Пол Атрейдес..."
    assert "Denis Villeneuve" in d.directors
    assert d.cast and d.cast[0] == "Timothée Chalamet"
    rating_sources = {r.source for r in d.ratings}
    assert rating_sources == {"tmdb", "imdb", "metacritic", "kinopoisk"}


async def test_get_movie_details_survives_one_provider_failure(
    app_ctx: AppContext, respx_mock: respx.MockRouter
) -> None:
    _stub_tmdb_details(respx_mock)
    # OMDb fails with a 5xx.
    respx_mock.get(f"{OMDB_BASE_URL}/").mock(return_value=httpx.Response(500, text="boom"))
    _stub_poiskkino(respx_mock)

    resp = await get_movie_details_impl(app_ctx, "tt1160419")

    assert resp.details is not None
    assert resp.details.title == "Dune"
    assert "omdb" in resp.sources_failed
    # No metacritic rating, because OMDb died.
    assert "metacritic" not in {r.source for r in resp.details.ratings}


async def test_get_movie_details_falls_back_to_title_when_poiskkino_imdb_empty(
    app_ctx: AppContext, respx_mock: respx.MockRouter
) -> None:
    _stub_tmdb_details(respx_mock)
    _stub_omdb(respx_mock)
    # Primary poiskkino-by-imdb returns no docs.
    respx_mock.get(f"{POISKKINO_BASE_URL}/v1.4/movie").mock(
        return_value=httpx.Response(200, json={"docs": [], "total": 0})
    )
    # Fallback via /search returns the 2021 match.
    respx_mock.get(f"{POISKKINO_BASE_URL}/v1.4/movie/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "docs": [
                    {
                        "id": 409424,
                        "name": "Дюна",
                        "year": 2021,
                        "description": "Пол Атрейдес на Арракисе...",
                        "rating": {"kp": 7.9},
                    }
                ]
            },
        )
    )

    resp = await get_movie_details_impl(app_ctx, "tt1160419")

    assert resp.details is not None
    assert resp.details.overview_ru == "Пол Атрейдес на Арракисе..."
    rating_sources = {r.source for r in resp.details.ratings}
    assert "kinopoisk" in rating_sources
    # Fallback ran, so an extra request hit /v1.4/movie/search.
    search_calls = [c for c in respx_mock.calls if "/v1.4/movie/search" in str(c.request.url)]
    assert len(search_calls) == 1


async def test_get_movie_details_rejects_bad_imdb(app_ctx: AppContext) -> None:
    resp = await get_movie_details_impl(app_ctx, "not-an-imdb-id")
    assert resp.error is not None
    assert resp.error.code == "invalid_argument"


async def test_get_movie_details_not_found_when_all_sources_return_nothing(
    app_ctx: AppContext, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{TMDB_BASE_URL}/find/tt9999999").mock(
        return_value=httpx.Response(200, json={"movie_results": []})
    )
    respx_mock.get(f"{OMDB_BASE_URL}/").mock(
        return_value=httpx.Response(200, json={"Response": "False", "Error": "not found"})
    )
    respx_mock.get(f"{POISKKINO_BASE_URL}/v1.4/movie").mock(
        return_value=httpx.Response(200, json={"docs": []})
    )

    resp = await get_movie_details_impl(app_ctx, "tt9999999")
    assert resp.details is None
    assert resp.error is not None
    assert resp.error.code == "not_found"


async def test_get_movie_details_uses_cache(
    app_ctx: AppContext, respx_mock: respx.MockRouter
) -> None:
    _stub_tmdb_details(respx_mock)
    _stub_omdb(respx_mock)
    _stub_poiskkino(respx_mock)

    await get_movie_details_impl(app_ctx, "tt1160419")
    calls_after_first = len(respx_mock.calls)
    await get_movie_details_impl(app_ctx, "tt1160419")
    assert len(respx_mock.calls) == calls_after_first
