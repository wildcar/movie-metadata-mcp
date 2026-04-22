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
    TitleKind,
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
        movies_raw, series_raw = await asyncio.gather(
            ctx.tmdb.search_movie(title, year=year, limit=_SEARCH_CANDIDATE_LIMIT),
            ctx.tmdb.search_tv(title, year=year, limit=_SEARCH_CANDIDATE_LIMIT),
        )
    except Exception as exc:
        log.warning("tmdb.search_failed", error=str(exc))
        return SearchMovieResponse(
            sources_failed=[_TMDB],
            error=ToolError(code="upstream_error", message=f"TMDB search failed: {exc}"),
        )

    imdb_movie, imdb_tv = await asyncio.gather(
        _resolve_imdb_ids(ctx, [r.get("id") for r in movies_raw], kind="movie"),
        _resolve_imdb_ids(ctx, [r.get("id") for r in series_raw], kind="series"),
    )

    candidates: list[MovieSearchResult] = []
    for raw in movies_raw:
        candidates.append(_to_search_result(ctx, raw, kind="movie", imdb_map=imdb_movie))
    for raw in series_raw:
        candidates.append(_to_search_result(ctx, raw, kind="series", imdb_map=imdb_tv))

    response = SearchMovieResponse(results=candidates)
    await ctx.cache.set(
        cache_key, response.model_dump(mode="json"), ctx.settings.cache_ttl_search_seconds
    )
    return response


async def _resolve_imdb_ids(
    ctx: AppContext, tmdb_ids: list[Any], *, kind: TitleKind
) -> dict[int, str | None]:
    """Fan out the ``external_ids`` endpoint (movie or tv) for each TMDB id.

    Network failures are swallowed and the affected id maps to ``None`` so the
    list rendering can still show the title (it just won't be actionable).
    """

    if ctx.tmdb is None:
        return {}
    valid_ids = [i for i in tmdb_ids if isinstance(i, int)]
    if not valid_ids:
        return {}

    fetch = (
        ctx.tmdb.get_external_ids if kind == "movie" else ctx.tmdb.get_tv_external_ids
    )

    async def _one(tmdb_id: int) -> tuple[int, str | None]:
        try:
            data = await fetch(tmdb_id)
        except Exception as exc:
            log.info(
                "tmdb.external_ids_failed", kind=kind, tmdb_id=tmdb_id, error=str(exc)
            )
            return tmdb_id, None
        imdb = data.get("imdb_id")
        return tmdb_id, imdb if isinstance(imdb, str) and imdb else None

    pairs = await asyncio.gather(*(_one(i) for i in valid_ids))
    return dict(pairs)


def _to_search_result(
    ctx: AppContext,
    raw: dict[str, Any],
    *,
    kind: TitleKind,
    imdb_map: dict[int, str | None],
) -> MovieSearchResult:
    """Normalise a raw TMDB movie-or-tv row into :class:`MovieSearchResult`."""

    tmdb_id = raw.get("id") if isinstance(raw.get("id"), int) else None

    if kind == "movie":
        localized = raw.get("title")
        original = raw.get("original_title")
        year = _parse_year(raw.get("release_date"))
    else:
        localized = raw.get("name")
        original = raw.get("original_name")
        year = _parse_year(raw.get("first_air_date"))

    title = localized or original or ""
    # Suppress ``original_title`` when it duplicates the localized title — no
    # point rendering "Дюна (Дюна)" in the UI.
    original_title = original if original and original != title else None

    # TMDB aggregated rating (0–10). 0.0 is used by TMDB when there are no
    # votes yet — treat it as "unknown" so the UI can skip the rating.
    vote = raw.get("vote_average")
    rating = float(vote) if isinstance(vote, int | float) and vote > 0 else None

    # Country resolution: TV rows carry ``origin_country`` (ISO-3166 codes);
    # movie rows don't, so we fall back to ``original_language`` (ISO 639-1)
    # mapped to the most common producing country. Imperfect but a good
    # enough hint for the list view — full details have the authoritative
    # ``production_countries``.
    country: str | None = None
    if kind == "series":
        origin = raw.get("origin_country")
        if isinstance(origin, list) and origin:
            country = _COUNTRY_RU.get(str(origin[0]).upper())
    else:
        lang = raw.get("original_language")
        if isinstance(lang, str) and lang:
            country = _LANG_TO_COUNTRY.get(lang.lower())

    return MovieSearchResult(
        kind=kind,
        imdb_id=imdb_map.get(tmdb_id) if tmdb_id is not None else None,
        tmdb_id=tmdb_id,
        title=title,
        original_title=original_title,
        year=year,
        poster_url=ctx.tmdb.poster_url(raw.get("poster_path")) if ctx.tmdb else None,
        overview=raw.get("overview") or None,
        rating=rating,
        country=country,
    )


# ISO-3166 alpha-2 → Russian country name. Coverage is limited to the
# countries that actually show up in TMDB results for films/series the bot
# handles; anything else falls back to ``None`` (country hidden in UI).
_COUNTRY_RU: dict[str, str] = {
    "US": "США", "GB": "Великобритания", "RU": "Россия", "UA": "Украина",
    "FR": "Франция", "DE": "Германия", "IT": "Италия", "ES": "Испания",
    "JP": "Япония", "KR": "Корея", "CN": "Китай", "HK": "Гонконг",
    "TW": "Тайвань", "IN": "Индия", "CA": "Канада", "AU": "Австралия",
    "NZ": "Новая Зеландия", "BR": "Бразилия", "MX": "Мексика", "AR": "Аргентина",
    "PL": "Польша", "CZ": "Чехия", "SE": "Швеция", "NO": "Норвегия",
    "DK": "Дания", "FI": "Финляндия", "NL": "Нидерланды", "BE": "Бельгия",
    "IE": "Ирландия", "TR": "Турция", "IL": "Израиль", "IR": "Иран",
    "TH": "Таиланд", "PH": "Филиппины", "ID": "Индонезия", "VN": "Вьетнам",
    "ZA": "ЮАР", "EG": "Египет", "GR": "Греция", "PT": "Португалия",
    "CH": "Швейцария", "AT": "Австрия", "HU": "Венгрия", "RO": "Румыния",
    "BG": "Болгария", "HR": "Хорватия", "RS": "Сербия", "BY": "Беларусь",
    "KZ": "Казахстан", "GE": "Грузия", "AM": "Армения",
}

# ISO 639-1 language → likely producing country (Russian). Best-effort only:
# English → США is a coin-flip vs UK/CA/AU, but 'США' is the most common
# TMDB origin for English-language films and reads naturally in Russian.
_LANG_TO_COUNTRY: dict[str, str] = {
    "en": "США", "ru": "Россия", "uk": "Украина", "be": "Беларусь",
    "fr": "Франция", "de": "Германия", "it": "Италия", "es": "Испания",
    "ja": "Япония", "ko": "Корея", "zh": "Китай", "hi": "Индия",
    "pt": "Бразилия", "pl": "Польша", "cs": "Чехия", "sk": "Словакия",
    "sv": "Швеция", "no": "Норвегия", "da": "Дания", "fi": "Финляндия",
    "nl": "Нидерланды", "tr": "Турция", "he": "Израиль", "fa": "Иран",
    "th": "Таиланд", "vi": "Вьетнам", "id": "Индонезия", "ar": "Египет",
    "el": "Греция", "hu": "Венгрия", "ro": "Румыния", "bg": "Болгария",
    "hr": "Хорватия", "sr": "Сербия", "ka": "Грузия", "hy": "Армения",
    "kk": "Казахстан",
}


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
        is_tv = tmdb.get("_kind") == "series"
        fallback_title = (
            (tmdb.get("name") or tmdb.get("original_name"))
            if is_tv
            else (tmdb.get("title") or tmdb.get("original_title"))
        )
        fallback_year = _parse_year(
            tmdb.get("first_air_date") if is_tv else tmdb.get("release_date")
        )
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
    """Resolve IMDb id through TMDB, dispatching between movie and TV endpoints.

    On success returns the details dict **with an added ``_kind`` key** so the
    merge step knows which field layout to expect (movie vs tv).
    """

    if ctx.tmdb is None:
        return _FAILED
    try:
        found = await ctx.tmdb.find_any_by_imdb(imdb_id)
        if found is None:
            return None
        kind, row = found
        kind_typed: TitleKind = "series" if kind == "series" else "movie"
        tmdb_id = row.get("id")
        if not isinstance(tmdb_id, int):
            return None
        details = (
            await ctx.tmdb.get_details(tmdb_id)
            if kind_typed == "movie"
            else await ctx.tmdb.get_tv_details(tmdb_id)
        )
        details["_kind"] = kind_typed
        return details
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
    kind: TitleKind = "movie"
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
        kind = "series" if tmdb.get("_kind") == "series" else "movie"
        tmdb_id = tmdb.get("id") if isinstance(tmdb.get("id"), int) else None
        if kind == "movie":
            title = tmdb.get("title") or tmdb.get("original_title") or ""
            original_title = tmdb.get("original_title") or None
            year = _parse_year(tmdb.get("release_date"))
            if isinstance(tmdb.get("runtime"), int):
                runtime = tmdb["runtime"]
            credits_data = tmdb.get("credits") or {}
            directors = [
                c.get("name", "")
                for c in credits_data.get("crew") or []
                if c.get("job") == "Director" and c.get("name")
            ]
        else:
            title = tmdb.get("name") or tmdb.get("original_name") or ""
            original_title = tmdb.get("original_name") or None
            year = _parse_year(tmdb.get("first_air_date"))
            runtimes = tmdb.get("episode_run_time") or []
            if isinstance(runtimes, list) and runtimes and isinstance(runtimes[0], int):
                runtime = runtimes[0]
            directors = [
                c.get("name", "")
                for c in tmdb.get("created_by") or []
                if c.get("name")
            ]
            credits_data = tmdb.get("credits") or {}
        if original_title and original_title == title:
            original_title = None
        genres = [g["name"] for g in tmdb.get("genres") or [] if g.get("name")]
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
        kind=kind,
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
