"""OMDb API client.

OMDb returns ``{"Response": "True", ...}`` on success and
``{"Response": "False", "Error": "..."}`` on failure. We treat the latter as
a normal "not found" result and let the caller decide how to degrade.
"""

from __future__ import annotations

from typing import Any

import httpx

OMDB_BASE_URL = "https://www.omdbapi.com"


class OMDbError(Exception):
    """Raised when OMDb returns an HTTP error (network / 5xx). A logical
    "not found" surfaces as ``None`` from :meth:`OMDbClient.get_by_imdb`."""


class OMDbClient:
    """Thin async wrapper around OMDb.

    OMDb auth is a query-param ``apikey``; there are no headers.
    """

    def __init__(
        self,
        api_key: str,
        *,
        http: httpx.AsyncClient | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._http = http or httpx.AsyncClient(base_url=OMDB_BASE_URL, timeout=timeout)
        self._owns_http = http is None

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def get_by_imdb(self, imdb_id: str) -> dict[str, Any] | None:
        """Fetch a movie by IMDb id. Returns ``None`` if OMDb reports not found."""

        resp = await self._http.get(
            "/",
            params={
                "apikey": self._api_key,
                "i": imdb_id,
                "plot": "full",
                "r": "json",
            },
        )
        if resp.status_code >= 400:
            raise OMDbError(f"OMDb i={imdb_id} → {resp.status_code}: {resp.text}")

        data: dict[str, Any] = resp.json()
        if data.get("Response") != "True":
            return None
        return data
