"""MCP tool implementations.

Two tools:

- :func:`search_movie_impl` — free-text → list of candidates. TMDB is the
  primary source. To make results useful to downstream MCP servers we
  resolve the IMDb id for the top candidates via a fan-out call.
- :func:`get_movie_details_impl` — IMDb id → merged metadata from TMDB,
  OMDb, and poiskkino.dev. Providers are queried in parallel; one failing
  provider degrades the response but never the tool.

Both tools go through :class:`~movie_metadata_mcp.cache.SQLiteCache`.
Responses are cached as their Pydantic JSON dumps, keyed by the canonical
tool-name + args string.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import structlog

from .context import AppContext
from .models import (
    GetMovieDetailsResponse,
    MovieDetails,
    MovieSearchResult,
    Rating,
    SearchMovieResponse,
    ToolError,
)

log = structlog.get_logger()

_TMDB = "tmdb"
_OMDB = "omdb"
_POISKKINO = "poiskkino"

_SEARCH_CANDIDATE_LIMIT = 5


# ---------------------------------------------------------------------------
# search_movie
# ---------------------------------------------------------------------------


async def search_movie_impl(
    ctx: AppContext, title: str, year: int | None = None
) -> SearchMovieResponse:
    """Implementation of the ``search_movie`` tool."""

    if not title or not title.strip():
        return SearchMovieResponse(
            error=ToolError(code="invalid_argument", message="`title` must not be empty."),
        )

    args = {"title": title, "year": year}
    cache_key = ctx.cache.make_key("search_movie", args)

    cached = await ctx.cache.get(cache_key)
    if cached is not None:
        return SearchMovieResponse.model_validate(cached)

    if ctx.tmdb is None:
        return SearchMovieResponse(
            sources_failed=[_TMDB],
            error=ToolError(
                code="no_primary_source",
                message="TMDB is the primary source for search; TMDB_API_TOKEN is not configured.",
            ),
        )

    try:
        raw_results = await ctx.tmdb.search_movie(title, year=year, limit=_SEARCH_CANDIDATE_LIMIT)
    except Exception as exc:
        log.warning("tmdb.search_failed", error=str(exc))
        return SearchMovieResponse(
            sources_failed=[_TMDB],
            error=ToolError(code="upstream_error", message=f"TMDB search failed: {exc}"),
        )

    imdb_ids = await _resolve_imdb_ids(ctx, [r.get("id") for r in raw_results])

    candidates: list[MovieSearchResult] = []
    for raw in raw_results:
        tmdb_id = raw.get("id")
        candidates.append(
            MovieSearchResult(
                imdb_id=imdb_ids.get(tmdb_id) if isinstance(tmdb_id, int) else None,
                tmdb_id=tmdb_id if isinstance(tmdb_id, int) else None,
                title=raw.get("title") or raw.get("original_title") or "",
                year=_parse_year(raw.get("release_date")),
                poster_url=ctx.tmdb.poster_url(raw.get("poster_path"))
                if ctx.tmdb is not None
                else None,
                overview=raw.get("overview") or None,
            )
        )

    response = SearchMovieResponse(results=candidates)
    await ctx.cache.set(
        cache_key, response.model_dump(mode="json"), ctx.settings.cache_ttl_search_seconds
    )
    return response


async def _resolve_imdb_ids(ctx: AppContext, tmdb_ids: list[Any]) -> dict[int, str | None]:
    """Fan out ``/movie/{id}/external_ids`` for each TMDB id; swallow failures."""

    if ctx.tmdb is None:
        return {}
    valid_ids = [i for i in tmdb_ids if isinstance(i, int)]
    if not valid_ids:
        return {}

    async def _one(tmdb_id: int) -> tuple[int, str | None]:
        try:
            data = await ctx.tmdb.get_external_ids(tmdb_id) if ctx.tmdb else {}
        except Exception as exc:
            log.info("tmdb.external_ids_failed", tmdb_id=tmdb_id, error=str(exc))
            return tmdb_id, None
        imdb = data.get("imdb_id")
        return tmdb_id, imdb if isinstance(imdb, str) and imdb else None

    pairs = await asyncio.gather(*(_one(i) for i in valid_ids))
    return dict(pairs)


# ---------------------------------------------------------------------------
# get_movie_details
# ---------------------------------------------------------------------------


async def get_movie_details_impl(ctx: AppContext, imdb_id: str) -> GetMovieDetailsResponse:
    """Implementation of the ``get_movie_details`` tool."""

    if not imdb_id or not imdb_id.startswith("tt"):
        return GetMovieDetailsResponse(
            error=ToolError(
                code="invalid_argument",
                message="`imdb_id` must start with 'tt' (e.g. tt1375666).",
            )
        )

    cache_key = ctx.cache.make_key("get_movie_details", {"imdb_id": imdb_id})
    cached = await ctx.cache.get(cache_key)
    if cached is not None:
        return GetMovieDetailsResponse.model_validate(cached)

    tmdb_payload, omdb_payload, poiskkino_payload = await asyncio.gather(
        _fetch_tmdb(ctx, imdb_id),
        _fetch_omdb(ctx, imdb_id),
        _fetch_poiskkino(ctx, imdb_id),
    )

    failed = [
        name
        for name, payload in (
            (_TMDB, tmdb_payload),
            (_OMDB, omdb_payload),
            (_POISKKINO, poiskkino_payload),
        )
        if payload is _FAILED
    ]

    # Treat ``None`` (successful "not found") as usable info, not a failure.
    tmdb = tmdb_payload if tmdb_payload is not _FAILED else None
    omdb = omdb_payload if omdb_payload is not _FAILED else None
    pk = poiskkino_payload if poiskkino_payload is not _FAILED else None

    # poiskkino fallback: some records in their DB have no IMDb externalId,
    # so ``externalId.imdb=...`` returns empty. When TMDB gave us a title +
    # year we try a text search before giving up on Russian content.
    if pk is None and ctx.poiskkino is not None and tmdb is not None:
        fallback_title = tmdb.get("title") or tmdb.get("original_title")
        fallback_year = _parse_year(tmdb.get("release_date"))
        if isinstance(fallback_title, str) and fallback_title:
            try:
                pk = await ctx.poiskkino.find_by_title(fallback_title, fallback_year)
            except Exception as exc:
                log.info(
                    "poiskkino.title_fallback_failed",
                    imdb_id=imdb_id,
                    title=fallback_title,
                    error=str(exc),
                )

    if tmdb is None and omdb is None and pk is None:
        return GetMovieDetailsResponse(
            sources_failed=failed,
            error=ToolError(
                code="not_found",
                message=f"No provider returned data for IMDb id {imdb_id}.",
            ),
        )

    details = _merge_details(imdb_id, ctx, tmdb, omdb, pk)
    response = GetMovieDetailsResponse(details=details, sources_failed=failed)
    await ctx.cache.set(
        cache_key, response.model_dump(mode="json"), ctx.settings.cache_ttl_details_seconds
    )
    return response


# Sentinel distinguishing "provider raised an exception" (failed) from
# "provider returned no match" (None). ``Any`` cast keeps mypy quiet —
# callers compare identity, not shape.
_FAILED: Any = object()


async def _fetch_tmdb(ctx: AppContext, imdb_id: str) -> dict[str, Any] | None | Any:
    if ctx.tmdb is None:
        return _FAILED
    try:
        found = await ctx.tmdb.find_by_imdb(imdb_id)
        if found is None:
            return None
        tmdb_id = found.get("id")
        if not isinstance(tmdb_id, int):
            return None
        return await ctx.tmdb.get_details(tmdb_id)
    except Exception as exc:
        log.warning("tmdb.details_failed", imdb_id=imdb_id, error=str(exc))
        return _FAILED


async def _fetch_omdb(ctx: AppContext, imdb_id: str) -> dict[str, Any] | None | Any:
    if ctx.omdb is None:
        return _FAILED
    try:
        return await ctx.omdb.get_by_imdb(imdb_id)
    except Exception as exc:
        log.warning("omdb.details_failed", imdb_id=imdb_id, error=str(exc))
        return _FAILED


async def _fetch_poiskkino(ctx: AppContext, imdb_id: str) -> dict[str, Any] | None | Any:
    if ctx.poiskkino is None:
        return _FAILED
    try:
        return await ctx.poiskkino.get_by_imdb(imdb_id)
    except Exception as exc:
        log.warning("poiskkino.details_failed", imdb_id=imdb_id, error=str(exc))
        return _FAILED


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------


def _merge_details(
    imdb_id: str,
    ctx: AppContext,
    tmdb: dict[str, Any] | None,
    omdb: dict[str, Any] | None,
    pk: dict[str, Any] | None,
) -> MovieDetails:
    """Combine provider payloads into a single :class:`MovieDetails`.

    Precedence: TMDB > poiskkino > OMDb for EN fields; poiskkino for RU fields.
    Ratings are appended from every source that reports a number.
    """

    tmdb_id: int | None = None
    title = ""
    original_title: str | None = None
    year: int | None = None
    runtime: int | None = None
    genres: list[str] = []
    directors: list[str] = []
    cast: list[str] = []
    overview: str | None = None
    poster_url: str | None = None

    if tmdb is not None:
        tmdb_id = tmdb.get("id") if isinstance(tmdb.get("id"), int) else None
        title = tmdb.get("title") or tmdb.get("original_title") or ""
        original_title = tmdb.get("original_title") or None
        year = _parse_year(tmdb.get("release_date"))
        if isinstance(tmdb.get("runtime"), int):
            runtime = tmdb["runtime"]
        genres = [g["name"] for g in tmdb.get("genres") or [] if g.get("name")]
        credits_data = tmdb.get("credits") or {}
        directors = [
            c.get("name", "")
            for c in credits_data.get("crew") or []
            if c.get("job") == "Director" and c.get("name")
        ]
        cast = [c.get("name", "") for c in (credits_data.get("cast") or [])[:10] if c.get("name")]
        overview = tmdb.get("overview") or None
        poster_url = ctx.tmdb.poster_url(tmdb.get("poster_path")) if ctx.tmdb else None

    # OMDb fills gaps the primary source left empty.
    if omdb is not None:
        if not title:
            title = omdb.get("Title") or title
        if year is None:
            try:
                year = int(str(omdb.get("Year"))[:4]) if omdb.get("Year") else None
            except ValueError:
                year = None
        if runtime is None:
            runtime_str = str(omdb.get("Runtime") or "").removesuffix(" min")
            if runtime_str.isdigit():
                runtime = int(runtime_str)
        if not genres:
            genres_str = omdb.get("Genre") or ""
            genres = [g.strip() for g in genres_str.split(",") if g.strip()]
        if not directors:
            directors_str = omdb.get("Director") or ""
            directors = [d.strip() for d in directors_str.split(",") if d.strip()]
        if not cast:
            cast_str = omdb.get("Actors") or ""
            cast = [c.strip() for c in cast_str.split(",") if c.strip()]
        if not overview:
            overview = omdb.get("Plot") or None

    overview_ru: str | None = None
    if pk is not None:
        overview_ru = pk.get("description") or pk.get("shortDescription") or None
        if not title:
            title = pk.get("name") or pk.get("alternativeName") or title
        if year is None and isinstance(pk.get("year"), int):
            year = pk["year"]
        if runtime is None and isinstance(pk.get("movieLength"), int):
            runtime = pk["movieLength"]
        if not genres:
            genres = [g["name"] for g in pk.get("genres") or [] if g.get("name")]
        if not poster_url:
            poster = pk.get("poster")
            if isinstance(poster, dict):
                poster_url = poster.get("url") or poster.get("previewUrl")

    ratings = _collect_ratings(tmdb, omdb, pk)

    return MovieDetails(
        imdb_id=imdb_id,
        tmdb_id=tmdb_id,
        title=title,
        original_title=original_title,
        year=year,
        runtime_minutes=runtime,
        genres=genres,
        directors=directors,
        cast=cast,
        overview=overview,
        overview_ru=overview_ru,
        poster_url=poster_url,
        ratings=ratings,
    )


def _collect_ratings(
    tmdb: dict[str, Any] | None,
    omdb: dict[str, Any] | None,
    pk: dict[str, Any] | None,
) -> list[Rating]:
    ratings: list[Rating] = []

    if tmdb is not None and isinstance(tmdb.get("vote_average"), int | float):
        votes = tmdb.get("vote_count")
        ratings.append(
            Rating(
                source=_TMDB,
                value=float(tmdb["vote_average"]),
                scale=10.0,
                votes=votes if isinstance(votes, int) else None,
            )
        )

    if omdb is not None:
        imdb_rating = omdb.get("imdbRating")
        if imdb_rating and imdb_rating != "N/A":
            try:
                value = float(imdb_rating)
            except ValueError:
                value = None
            if value is not None:
                votes_str = (omdb.get("imdbVotes") or "").replace(",", "")
                votes_i = int(votes_str) if votes_str.isdigit() else None
                ratings.append(Rating(source="imdb", value=value, scale=10.0, votes=votes_i))
        metascore = omdb.get("Metascore")
        if metascore and metascore != "N/A":
            try:
                ratings.append(
                    Rating(source="metacritic", value=float(metascore), scale=100.0, votes=None)
                )
            except ValueError:
                pass

    if pk is not None:
        rating_block = pk.get("rating") or {}
        votes_block = pk.get("votes") or {}
        kp_val = rating_block.get("kp") if isinstance(rating_block, dict) else None
        if isinstance(kp_val, int | float) and kp_val:
            kp_votes = votes_block.get("kp") if isinstance(votes_block, dict) else None
            ratings.append(
                Rating(
                    source="kinopoisk",
                    value=float(kp_val),
                    scale=10.0,
                    votes=kp_votes if isinstance(kp_votes, int) else None,
                )
            )

    return ratings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_year(date_str: Any) -> int | None:
    if not isinstance(date_str, str) or len(date_str) < 4:
        return None
    prefix = date_str[:4]
    return int(prefix) if prefix.isdigit() else None


# silence unused-logging-import when log level is disabled by library
logging.getLogger(__name__)
