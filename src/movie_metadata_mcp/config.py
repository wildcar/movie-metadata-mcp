"""Runtime configuration loaded from environment / .env file.

All secrets (API keys) live here. Tool argument surfaces never carry them.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven configuration.

    Variable names map 1-to-1 to env vars. Defaults are intentionally safe:
    the server can start without credentials, and individual provider calls
    degrade gracefully when their key is missing.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Upstream providers -------------------------------------------------

    tmdb_api_token: str | None = Field(
        default=None,
        description="TMDB API Read Access Token (v4 auth). Obtain at https://www.themoviedb.org/settings/api",
    )
    omdb_api_key: str | None = Field(
        default=None,
        description="OMDb API key. Obtain at https://www.omdbapi.com/apikey.aspx",
    )
    poiskkino_dev_token: str | None = Field(
        default=None,
        description="poiskkino.dev API token. Obtain at https://poiskkino.dev (Telegram bot @poiskkinodev_bot). Formerly kinopoisk.dev.",
    )

    # Cache --------------------------------------------------------------

    cache_path: str = Field(
        default=".cache/movie_metadata.sqlite",
        description="Filesystem path to the SQLite cache database.",
    )
    cache_ttl_search_seconds: int = Field(default=3600)
    cache_ttl_details_seconds: int = Field(default=86_400)

    # MCP transport ------------------------------------------------------

    mcp_auth_token: str | None = Field(
        default=None,
        description="Bearer token required when the server is exposed over HTTP+SSE.",
    )


def get_settings() -> Settings:
    """Construct a Settings instance.

    Defined as a function (rather than a module-level singleton) so tests can
    build isolated instances with patched env vars.
    """

    return Settings()
