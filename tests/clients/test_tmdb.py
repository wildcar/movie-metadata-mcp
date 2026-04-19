"""Tests for ``TMDBClient`` — HTTP mocked via respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from movie_metadata_mcp.clients.tmdb import TMDB_BASE_URL, TMDBClient, TMDBError


async def test_search_movie_passes_year_and_trims_to_limit(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{TMDB_BASE_URL}/search/movie").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {"id": 1, "title": "Dune", "release_date": "2021-09-15"},
                    {"id": 2, "title": "Dune 2"},
                    {"id": 3, "title": "Dune 3"},
                ]
            },
        )
    )
    client = TMDBClient("tok")
    try:
        results = await client.search_movie("Dune", year=2021, limit=2)
    finally:
        await client.aclose()

    assert len(results) == 2
    assert results[0]["id"] == 1
    # Year filter propagated.
    request = respx_mock.calls.last.request
    assert request.url.params["year"] == "2021"
    assert request.url.params["query"] == "Dune"
    assert request.headers["Authorization"] == "Bearer tok"


async def test_find_by_imdb_returns_first_match(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{TMDB_BASE_URL}/find/tt1160419").mock(
        return_value=httpx.Response(200, json={"movie_results": [{"id": 438631, "title": "Dune"}]})
    )
    client = TMDBClient("tok")
    try:
        found = await client.find_by_imdb("tt1160419")
    finally:
        await client.aclose()
    assert found == {"id": 438631, "title": "Dune"}


async def test_find_by_imdb_returns_none_when_no_match(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{TMDB_BASE_URL}/find/tt0").mock(
        return_value=httpx.Response(200, json={"movie_results": []})
    )
    client = TMDBClient("tok")
    try:
        assert await client.find_by_imdb("tt0") is None
    finally:
        await client.aclose()


async def test_error_response_raises(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{TMDB_BASE_URL}/movie/999/external_ids").mock(
        return_value=httpx.Response(401, text="Invalid API key")
    )
    client = TMDBClient("tok")
    try:
        with pytest.raises(TMDBError, match="401"):
            await client.get_external_ids(999)
    finally:
        await client.aclose()


def test_poster_url_builder() -> None:
    assert TMDBClient.poster_url("/abc.jpg") == "https://image.tmdb.org/t/p/w500/abc.jpg"
    assert TMDBClient.poster_url(None) is None
    assert TMDBClient.poster_url("") is None
