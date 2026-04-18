"""Smoke tests for MCP server wiring.

These tests exercise tool registration and the Step-A ``not_implemented``
stubs. Real behaviour tests land alongside the client/cache/tool logic in
Step B.
"""

from __future__ import annotations

import pytest

from movie_metadata_mcp.server import build_server
from movie_metadata_mcp.tools import get_movie_details, search_movie


def test_build_server_registers_both_tools() -> None:
    server = build_server()
    assert server.name == "movie-metadata-mcp"

    tool_names = {tool.name for tool in server._tool_manager._tools.values()}
    assert tool_names == {"search_movie", "get_movie_details"}


@pytest.mark.asyncio
async def test_search_movie_stub_returns_not_implemented() -> None:
    response = await search_movie(title="Dune", year=2021)
    assert response.results == []
    assert response.error is not None
    assert response.error.code == "not_implemented"


@pytest.mark.asyncio
async def test_get_movie_details_stub_returns_not_implemented() -> None:
    response = await get_movie_details(imdb_id="tt1160419")
    assert response.details is None
    assert response.error is not None
    assert response.error.code == "not_implemented"
