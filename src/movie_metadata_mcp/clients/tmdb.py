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
DEFAULT_LANGUAGE = "en-US"


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

    async def get_external_ids(self, tmdb_id: int) -> dict[str, Any]:
        """Fetch external ids (IMDb, etc.) for a TMDB movie."""

        return await self._get_json(f"/movie/{tmdb_id}/external_ids")

    async def find_by_imdb(self, imdb_id: str) -> dict[str, Any] | None:
        """Reverse lookup by IMDb id. Returns the first matching TMDB movie or ``None``."""

        data = await self._get_json(
            f"/find/{imdb_id}",
            params={"external_source": "imdb_id", "language": DEFAULT_LANGUAGE},
        )
        movies = data.get("movie_results", [])
        if isinstance(movies, list) and movies:
            first: dict[str, Any] = movies[0]
            return first
        return None

    async def get_details(self, tmdb_id: int) -> dict[str, Any]:
        """Fetch full details + top-billed cast + director in one request."""

        return await self._get_json(
            f"/movie/{tmdb_id}",
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
