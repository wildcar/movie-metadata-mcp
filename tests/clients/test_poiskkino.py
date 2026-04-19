"""Tests for ``PoiskkinoClient`` — HTTP mocked via respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from movie_metadata_mcp.clients.poiskkino import (
    POISKKINO_BASE_URL,
    PoiskkinoClient,
    PoiskkinoError,
)


async def test_returns_first_doc(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{POISKKINO_BASE_URL}/v1.4/movie").mock(
        return_value=httpx.Response(
            200,
            json={
                "docs": [{"id": 123, "name": "Дюна", "description": "Пустынная планета..."}],
                "total": 1,
                "limit": 1,
                "page": 1,
                "pages": 1,
            },
        )
    )
    client = PoiskkinoClient("tok")
    try:
        data = await client.get_by_imdb("tt1160419")
    finally:
        await client.aclose()

    assert data is not None
    assert data["name"] == "Дюна"
    request = respx_mock.calls.last.request
    assert request.headers["X-API-KEY"] == "tok"
    assert request.url.params["externalId.imdb"] == "tt1160419"
    assert request.url.params["limit"] == "1"


async def test_empty_docs_returns_none(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{POISKKINO_BASE_URL}/v1.4/movie").mock(
        return_value=httpx.Response(200, json={"docs": []})
    )
    client = PoiskkinoClient("tok")
    try:
        assert await client.get_by_imdb("tt0") is None
    finally:
        await client.aclose()


async def test_find_by_title_picks_year_match(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{POISKKINO_BASE_URL}/v1.4/movie/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "docs": [
                    {"id": 2882, "name": "Дюна", "year": 1984},
                    {"id": 409424, "name": "Дюна", "year": 2021},
                ]
            },
        )
    )
    client = PoiskkinoClient("tok")
    try:
        data = await client.find_by_title("Dune", year=2021)
    finally:
        await client.aclose()
    assert data is not None
    assert data["year"] == 2021
    assert data["id"] == 409424


async def test_find_by_title_falls_back_to_first_when_no_year_match(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"{POISKKINO_BASE_URL}/v1.4/movie/search").mock(
        return_value=httpx.Response(
            200,
            json={"docs": [{"id": 1, "name": "X", "year": 2001}]},
        )
    )
    client = PoiskkinoClient("tok")
    try:
        data = await client.find_by_title("X", year=2050)
    finally:
        await client.aclose()
    assert data is not None and data["id"] == 1


async def test_error_raises(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{POISKKINO_BASE_URL}/v1.4/movie").mock(
        return_value=httpx.Response(403, text="forbidden")
    )
    client = PoiskkinoClient("tok")
    try:
        with pytest.raises(PoiskkinoError, match="403"):
            await client.get_by_imdb("tt1160419")
    finally:
        await client.aclose()
