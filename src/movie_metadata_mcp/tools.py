"""MCP tool implementations.

These functions are the public tool surface of the server. At this stage
(Step A — scaffolding) they return a structured ``not_implemented`` error so
that the wiring — registration, schema derivation, transport — can be
exercised end-to-end via MCP Inspector before real logic lands in Step B.
"""

from __future__ import annotations

from .models import (
    GetMovieDetailsResponse,
    SearchMovieResponse,
    ToolError,
)

_NOT_IMPLEMENTED = ToolError(
    code="not_implemented",
    message="Tool logic not implemented yet (Step A scaffolding only).",
)


async def search_movie(title: str, year: int | None = None) -> SearchMovieResponse:
    """Search candidate movies across TMDB, OMDb, and kinopoisk.dev.

    Args:
        title: Free-text title to search for.
        year: Optional release year to disambiguate.

    Returns:
        ``SearchMovieResponse`` with merged candidates. In the current
        scaffolding this always returns a ``not_implemented`` error.
    """

    _ = (title, year)  # unused until Step B
    return SearchMovieResponse(error=_NOT_IMPLEMENTED)


async def get_movie_details(imdb_id: str) -> GetMovieDetailsResponse:
    """Fetch full metadata for a movie by IMDb ID.

    Args:
        imdb_id: IMDb identifier (``tt\\d{7,8}``). Correlation key across the
            cross-server system, returned by ``search_movie``.

    Returns:
        ``GetMovieDetailsResponse``. In the current scaffolding this always
        returns a ``not_implemented`` error.
    """

    _ = imdb_id
    return GetMovieDetailsResponse(error=_NOT_IMPLEMENTED)
