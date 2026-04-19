"""TMDB API client.

Uses the v4 API Read Access Token (Bearer auth) against the v3 REST
endpoints — this is the officially documented path for public data access.

Surface (intentionally narrow — driven by the two MCP tools):
- ``search_movie`` — free-text search with optional year filter.
- ``get_external_ids`` — fetch the IMDb id for a TMDB movie id.
- ``find_by_imdb`` — reverse lookup: IMDb id → TMDB movie.
- ``get_details`` — full details + credits in a single call.
"""

from __future__ import annotations

from typing import Any

import httpx

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
# The bot serves a Russian UI; ask TMDB for ru-RU metadata upfront. Original
# titles remain available on each response via ``original_title`` /
# ``original_name`` so we can show both to the user.
DEFAULT_LANGUAGE = "ru-RU"


class TMDBError(Exception):
    """Raised when TMDB returns a non-success response."""


class TMDBClient:
    """Thin async wrapper around TMDB.

    The client owns no state beyond an ``httpx.AsyncClient``. Tests inject a
    mocked transport via ``respx``.
    """

    def __init__(
        self,
        token: str,
        *,
        http: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._token = token
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        self._http = http or httpx.AsyncClient(
            base_url=TMDB_BASE_URL, headers=headers, timeout=timeout
        )
        self._owns_http = http is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    # ---------------------------------------------------------------
    # Public methods
    # ---------------------------------------------------------------

    async def search_movie(
        self, title: str, year: int | None = None, *, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Search movies by title. Returns raw TMDB result dicts (trimmed to ``limit``)."""

        params: dict[str, Any] = {
            "query": title,
            "language": DEFAULT_LANGUAGE,
            "include_adult": "false",
            "page": 1,
        }
        if year is not None:
            params["year"] = year

        data = await self._get_json("/search/movie", params=params)
        results = data.get("results", [])
        if not isinstance(results, list):
            raise TMDBError("TMDB search: 'results' missing or malformed")
        return results[:limit]

    async def search_tv(
        self, title: str, year: int | None = None, *, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Search TV series by title. Same shape as ``search_movie`` but hits ``/search/tv``.

        The raw TMDB TV item uses ``name``/``original_name``/``first_air_date``;
        the caller is responsible for normalising to ``title``/``original_title``/``year``.
        """

        params: dict[str, Any] = {
            "query": title,
            "language": DEFAULT_LANGUAGE,
            "include_adult": "false",
            "page": 1,
        }
        if year is not None:
            params["first_air_date_year"] = year

        data = await self._get_json("/search/tv", params=params)
        results = data.get("results", [])
        if not isinstance(results, list):
            raise TMDBError("TMDB TV search: 'results' missing or malformed")
        return results[:limit]

    async def get_external_ids(self, tmdb_id: int) -> dict[str, Any]:
        """Fetch external ids (IMDb, etc.) for a TMDB movie."""

        return await self._get_json(f"/movie/{tmdb_id}/external_ids")

    async def get_tv_external_ids(self, tv_id: int) -> dict[str, Any]:
        """Fetch external ids for a TMDB TV series."""

        return await self._get_json(f"/tv/{tv_id}/external_ids")

    async def find_by_imdb(self, imdb_id: str) -> dict[str, Any] | None:
        """Reverse lookup by IMDb id against movies only.

        Kept for callers that want a movie-specific answer. For a unified
        lookup across movies **and** TV series, use :meth:`find_any_by_imdb`.
        """

        data = await self._find_raw(imdb_id)
        movies = data.get("movie_results", [])
        if isinstance(movies, list) and movies:
            first: dict[str, Any] = movies[0]
            return first
        return None

    async def find_any_by_imdb(
        self, imdb_id: str
    ) -> tuple[str, dict[str, Any]] | None:
        """Reverse lookup across both movie and TV endpoints.

        Returns ``("movie" | "series", tmdb_row)`` for the first match, or
        ``None`` if neither list is populated. One HTTP round-trip — ``/find``
        returns all categories at once.
        """

        data = await self._find_raw(imdb_id)
        movies = data.get("movie_results", [])
        if isinstance(movies, list) and movies:
            return "movie", movies[0]
        tv = data.get("tv_results", [])
        if isinstance(tv, list) and tv:
            return "series", tv[0]
        return None

    async def _find_raw(self, imdb_id: str) -> dict[str, Any]:
        return await self._get_json(
            f"/find/{imdb_id}",
            params={"external_source": "imdb_id", "language": DEFAULT_LANGUAGE},
        )

    async def get_details(self, tmdb_id: int) -> dict[str, Any]:
        """Fetch full movie details + top-billed cast + director in one request."""

        return await self._get_json(
            f"/movie/{tmdb_id}",
            params={"language": DEFAULT_LANGUAGE, "append_to_response": "credits"},
        )

    async def get_tv_details(self, tv_id: int) -> dict[str, Any]:
        """Fetch full TV-series details + credits in one request."""

        return await self._get_json(
            f"/tv/{tv_id}",
            params={"language": DEFAULT_LANGUAGE, "append_to_response": "credits"},
        )

    # ---------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------

    @staticmethod
    def poster_url(poster_path: str | None) -> str | None:
        """Turn a relative TMDB ``poster_path`` into a full image URL."""

        if not poster_path:
            return None
        return f"{TMDB_IMAGE_BASE_URL}{poster_path}"

    async def _get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = await self._http.get(path, params=params)
        if resp.status_code >= 400:
            raise TMDBError(f"TMDB {resp.request.method} {path} → {resp.status_code}: {resp.text}")
        payload: dict[str, Any] = resp.json()
        return payload
