"""Pydantic models for the tool input/output surface.

Kept independent of any upstream provider's wire format; client modules in
``movie_metadata_mcp.clients`` are responsible for mapping provider payloads
into these types.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TitleKind = Literal["movie", "series"]

# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------


class _Base(BaseModel):
    """Shared config for every model in this module."""

    model_config = ConfigDict(extra="forbid", frozen=False)


class ToolError(_Base):
    """Structured error envelope returned by a tool when a call cannot be served.

    Per the project convention, MCP tools never raise through the MCP boundary —
    failures surface as a normal response that happens to carry an error.
    """

    code: str = Field(..., description="Stable machine-readable error code.")
    message: str = Field(..., description="Human-readable explanation in English.")


# ---------------------------------------------------------------------------
# search_movie
# ---------------------------------------------------------------------------


class MovieSearchResult(_Base):
    """A single candidate returned by ``search_movie``.

    Lean on purpose: just enough to let an agent disambiguate before calling
    ``get_movie_details`` with the IMDb ID.
    """

    kind: TitleKind = Field(
        "movie", description="Whether this candidate is a feature film or a TV series."
    )
    imdb_id: str | None = Field(
        None, description="IMDb identifier (e.g. tt1375666). May be None if unknown."
    )
    tmdb_id: int | None = Field(None, description="TMDB numeric identifier, if available.")
    title: str = Field(..., description="Localized title (ru-RU) as reported by TMDB.")
    original_title: str | None = Field(
        None, description="Original-language title; useful for disambiguation in the UI."
    )
    year: int | None = Field(None, description="Release year, if known.")
    poster_url: str | None = Field(None, description="Absolute URL of a poster image.")
    overview: str | None = Field(None, description="Short plot summary (ru-RU when available).")
    rating: float | None = Field(
        None,
        description="TMDB aggregated rating on a 0–10 scale; None when TMDB has no votes yet.",
    )
    country: str | None = Field(
        None,
        description=(
            "Primary production country in Russian (e.g. 'США'). Mapped from TMDB "
            "origin_country for TV, original_language for movies (best-effort)."
        ),
    )


class SearchMovieResponse(_Base):
    """Response envelope for ``search_movie``."""

    results: list[MovieSearchResult] = Field(default_factory=list)
    sources_failed: list[str] = Field(
        default_factory=list,
        description="Provider names that failed during this call; partial results may be returned.",
    )
    error: ToolError | None = Field(
        None, description="Set only when the call could not be served at all."
    )


# ---------------------------------------------------------------------------
# get_movie_details
# ---------------------------------------------------------------------------


class Rating(_Base):
    """A single rating from one source."""

    source: str = Field(..., description="Source identifier, e.g. 'imdb', 'tmdb', 'kinopoisk'.")
    value: float = Field(..., description="Numeric rating on the source's native scale.")
    scale: float = Field(..., description="The source's maximum possible value (e.g. 10.0).")
    votes: int | None = Field(None, description="Number of votes, if the source reports it.")


class MovieDetails(_Base):
    """Full metadata returned by ``get_movie_details``."""

    imdb_id: str = Field(..., description="IMDb identifier — cross-server correlation key.")
    kind: TitleKind = Field("movie", description="Feature film or TV series.")
    tmdb_id: int | None = None
    title: str
    original_title: str | None = None
    year: int | None = None
    runtime_minutes: int | None = None
    genres: list[str] = Field(default_factory=list)
    directors: list[str] = Field(default_factory=list)
    cast: list[str] = Field(default_factory=list, description="Main cast, ordered by billing.")
    overview: str | None = Field(None, description="Plot summary (language depends on source).")
    overview_ru: str | None = Field(
        None, description="Russian plot summary, sourced from poiskkino.dev when available."
    )
    poster_url: str | None = None
    ratings: list[Rating] = Field(default_factory=list)


class GetMovieDetailsResponse(_Base):
    """Response envelope for ``get_movie_details``."""

    details: MovieDetails | None = None
    sources_failed: list[str] = Field(default_factory=list)
    error: ToolError | None = None
