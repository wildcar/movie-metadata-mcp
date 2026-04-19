"""poiskkino.dev API client (formerly kinopoisk.dev).

Uses ``X-API-KEY`` header auth against the v1.4 REST API.
See https://poiskkino.dev/documentation — the OpenAPI spec is exposed at
``https://api.poiskkino.dev/documentation-json``.

Surface:
- ``get_by_imdb`` — lookup by IMDb id via ``/v1.4/movie?externalId.imdb=...``.
- ``find_by_title`` — text-search fallback for titles whose record in the
  poiskkino dataset lacks an IMDb externalId mapping (a real data gap —
  confirmed e.g. for "Dune" 2021, which exists in the DB but without its
  IMDb id populated). Used by ``tools.get_movie_details_impl`` when the
  primary IMDb lookup returns no match.
"""

from __future__ import annotations

from typing import Any

import httpx

POISKKINO_BASE_URL = "https://api.poiskkino.dev"


class PoiskkinoError(Exception):
    """Raised when the upstream returns an HTTP error."""


class PoiskkinoClient:
    def __init__(
        self,
        api_key: str,
        *,
        http: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        headers = {"X-API-KEY": api_key, "Accept": "application/json"}
        self._http = http or httpx.AsyncClient(
            base_url=POISKKINO_BASE_URL, headers=headers, timeout=timeout
        )
        self._owns_http = http is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def get_by_imdb(self, imdb_id: str) -> dict[str, Any] | None:
        """Fetch the first movie matching ``externalId.imdb == imdb_id``.

        Returns the raw doc dict or ``None`` if no match.
        """

        resp = await self._http.get(
            "/v1.4/movie",
            params={"externalId.imdb": imdb_id, "limit": 1},
        )
        if resp.status_code >= 400:
            raise PoiskkinoError(f"poiskkino.dev imdb={imdb_id} → {resp.status_code}: {resp.text}")
        payload = resp.json()
        docs = payload.get("docs", [])
        if isinstance(docs, list) and docs:
            first: dict[str, Any] = docs[0]
            return first
        return None

    async def find_by_title(
        self, title: str, year: int | None = None, *, limit: int = 5
    ) -> dict[str, Any] | None:
        """Text-search fallback via ``/v1.4/movie/search?query=...``.

        Picks the best candidate by year match when a ``year`` is supplied;
        otherwise returns the first hit. Returns ``None`` if no results.

        Note: the ``search`` endpoint returns a trimmed payload compared to
        ``/v1.4/movie`` (e.g. some fields may be absent). Merging code in
        ``tools.py`` handles missing fields gracefully.
        """

        resp = await self._http.get(
            "/v1.4/movie/search",
            params={"query": title, "limit": limit},
        )
        if resp.status_code >= 400:
            raise PoiskkinoError(
                f"poiskkino.dev search={title!r} → {resp.status_code}: {resp.text}"
            )
        payload = resp.json()
        docs = payload.get("docs", [])
        if not isinstance(docs, list) or not docs:
            return None
        if year is not None:
            for doc in docs:
                if isinstance(doc.get("year"), int) and doc["year"] == year:
                    match: dict[str, Any] = doc
                    return match
        first: dict[str, Any] = docs[0]
        return first
