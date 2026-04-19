"""MCP server entrypoint.

Registers the two tools and starts the chosen transport. Context (upstream
clients + cache) is built inside an async ``AppContext`` contextmanager
whose lifetime wraps the server run. Tool handlers are thin closures that
forward to the real implementations in :mod:`movie_metadata_mcp.tools`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Final

import structlog
from mcp.server.fastmcp import FastMCP

from . import __version__
from .config import Settings, get_settings
from .context import AppContext, build_app_context
from .models import GetMovieDetailsResponse, SearchMovieResponse
from .tools import get_movie_details_impl, search_movie_impl

_SUPPORTED_TRANSPORTS: Final[frozenset[str]] = frozenset({"stdio", "sse", "streamable-http"})


def _configure_logging() -> None:
    """Route log output to stderr.

    Stdout is reserved for the stdio transport's JSON-RPC frames — logging
    there would corrupt the wire protocol.
    """

    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def build_server(ctx: AppContext) -> FastMCP:
    """Construct a ``FastMCP`` with both tools bound to the supplied context."""

    mcp = FastMCP(
        name="movie-metadata-mcp",
        instructions=(
            "Aggregates movie metadata from TMDB, OMDb, and poiskkino.dev. "
            "Use `search_movie` to resolve a free-text query to IMDb IDs, then "
            "`get_movie_details` to fetch full metadata. IMDb IDs returned here "
            "are the cross-server correlation key."
        ),
    )

    async def search_movie(title: str, year: int | None = None) -> SearchMovieResponse:
        """Search candidate movies by title (optionally filtered by year).

        Returns a merged list across TMDB/OMDb/poiskkino.dev.
        """

        return await search_movie_impl(ctx, title, year)

    async def get_movie_details(imdb_id: str) -> GetMovieDetailsResponse:
        """Fetch full metadata for a movie by IMDb ID.

        Returns poster, plot (EN + RU), ratings (IMDb / TMDB / Кинопоиск),
        genres, director, cast, runtime.
        """

        return await get_movie_details_impl(ctx, imdb_id)

    mcp.tool(name="search_movie")(search_movie)
    mcp.tool(name="get_movie_details")(get_movie_details)

    return mcp


async def _run(settings: Settings, transport: str) -> None:
    log = structlog.get_logger()
    async with build_app_context(settings) as ctx:
        server = build_server(ctx)
        log.info(
            "server.start",
            version=__version__,
            transport=transport,
            tmdb_configured=ctx.tmdb is not None,
            omdb_configured=ctx.omdb is not None,
            poiskkino_configured=ctx.poiskkino is not None,
        )
        if transport == "stdio":
            await server.run_stdio_async()
        elif transport == "sse":
            await server.run_sse_async()
        else:  # "streamable-http"
            await server.run_streamable_http_async()


def main() -> None:
    """Entrypoint called by the console script ``movie-metadata-mcp``."""

    _configure_logging()
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport not in _SUPPORTED_TRANSPORTS:
        raise SystemExit(
            f"Unsupported MCP_TRANSPORT={transport!r}; "
            f"expected one of {sorted(_SUPPORTED_TRANSPORTS)}."
        )
    asyncio.run(_run(get_settings(), transport))


if __name__ == "__main__":
    main()
