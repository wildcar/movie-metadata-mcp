"""Server-level smoke tests."""

from __future__ import annotations

from movie_metadata_mcp.context import AppContext
from movie_metadata_mcp.server import build_server


def test_build_server_registers_both_tools(app_ctx: AppContext) -> None:
    server = build_server(app_ctx)
    assert server.name == "movie-metadata-mcp"
    names = {t.name for t in server._tool_manager._tools.values()}
    assert names == {"search_movie", "get_movie_details"}
