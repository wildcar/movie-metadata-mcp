"""MCP server entrypoint.

Registers the two public tools and starts the transport.

Default transport is ``stdio`` (used by MCP Inspector and by Claude Desktop).
Networked transports (``sse``, ``streamable-http``) are available through the
``MCP_TRANSPORT`` environment variable; those require ``MCP_AUTH_TOKEN`` to be
set — see README.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Final

import structlog
from mcp.server.fastmcp import FastMCP

from . import __version__
from .tools import get_movie_details, search_movie

_SUPPORTED_TRANSPORTS: Final[frozenset[str]] = frozenset({"stdio", "sse", "streamable-http"})


def _configure_logging() -> None:
    """Send structlog output to stderr as JSON.

    stdout is reserved for the MCP stdio transport's JSON-RPC framing — logging
    there would corrupt the protocol. stderr is safe.
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


def build_server() -> FastMCP:
    """Construct a ``FastMCP`` instance with all tools registered.

    Split from ``main`` so tests can import the server without starting a
    transport.
    """

    mcp = FastMCP(
        name="movie-metadata-mcp",
        instructions=(
            "Aggregates movie metadata from TMDB, OMDb, and poiskkino.dev. "
            "Use `search_movie` to resolve a free-text query to IMDb IDs, then "
            "`get_movie_details` to fetch full metadata. IMDb IDs returned here "
            "are the cross-server correlation key."
        ),
    )

    mcp.tool(
        name="search_movie",
        description=(
            "Search candidate movies by title (optionally filtered by year). "
            "Returns a merged list across TMDB/OMDb/poiskkino.dev."
        ),
    )(search_movie)

    mcp.tool(
        name="get_movie_details",
        description=(
            "Fetch full metadata for a movie by IMDb ID: poster, plot, ratings "
            "(IMDb/TMDB/Кинопоиск), cast, director, runtime, genres."
        ),
    )(get_movie_details)

    return mcp


def main() -> None:
    """Start the MCP server.

    Transport is picked from the ``MCP_TRANSPORT`` env var (default: ``stdio``).
    """

    _configure_logging()
    log = structlog.get_logger()

    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport not in _SUPPORTED_TRANSPORTS:
        raise SystemExit(
            f"Unsupported MCP_TRANSPORT={transport!r}; "
            f"expected one of {sorted(_SUPPORTED_TRANSPORTS)}."
        )

    log.info("server.start", version=__version__, transport=transport)
    server = build_server()
    server.run(transport=transport)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
