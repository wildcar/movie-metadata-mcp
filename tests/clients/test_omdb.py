"""Tests for ``OMDbClient`` — HTTP mocked via respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from movie_metadata_mcp.clients.omdb import OMDB_BASE_URL, OMDbClient, OMDbError


async def test_success_returns_payload(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{OMDB_BASE_URL}/").mock(
        return_value=httpx.Response(
            200,
            json={
                "Title": "Dune",
                "Year": "2021",
                "imdbRating": "8.0",
                "imdbID": "tt1160419",
                "Response": "True",
            },
        )
    )
    client = OMDbClient("key")
    try:
        data = await client.get_by_imdb("tt1160419")
    finally:
        await client.aclose()

    assert data is not None
    assert data["Title"] == "Dune"
    request = respx_mock.calls.last.request
    assert request.url.params["apikey"] == "key"
    assert request.url.params["i"] == "tt1160419"
    assert request.url.params["plot"] == "full"


async def test_not_found_returns_none(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{OMDB_BASE_URL}/").mock(
        return_value=httpx.Response(200, json={"Response": "False", "Error": "Incorrect IMDb ID."})
    )
    client = OMDbClient("key")
    try:
        assert await client.get_by_imdb("tt0") is None
    finally:
        await client.aclose()


async def test_http_error_raises(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{OMDB_BASE_URL}/").mock(return_value=httpx.Response(500, text="boom"))
    client = OMDbClient("key")
    try:
        with pytest.raises(OMDbError, match="500"):
            await client.get_by_imdb("tt1160419")
    finally:
        await client.aclose()
