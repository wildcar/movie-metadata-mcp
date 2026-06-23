# Environment — movie-metadata-mcp

Repo-local environment detail. **Shared host/deploy facts** (dev box, bot host,
media host, `uv`/`gh`/tool versions, GitHub auth, prod deploy commands, credential
file layout) live in `../AGENTS/ENV.md` — read that for anything not below.

## Python / virtualenv

- Managed by `uv`; `.venv/` created by `uv sync`, gitignored.
- Interpreter pin: `.python-version` → `3.12` (matches the dev host).
  `pyproject.toml` declares `requires-python = ">=3.11"` so CI validates on 3.11 too.

## Local `.env`

- Copy `.env.example` → `.env`, fill in real credentials; `.env` is gitignored and
  read automatically by `pydantic-settings`. Never commit it.
- Three tokens required for meaningful output / integration tests:
  `TMDB_API_TOKEN` (v4 Read Access Token), `OMDB_API_KEY`, `POISKKINO_DEV_TOKEN`.
  Obtain-links are in `README.md` and `.env.example`. The server still starts with
  tokens missing — each provider degrades independently.
- Optional: `CACHE_PATH`, `CACHE_TTL_SEARCH_SECONDS` (3600), `CACHE_TTL_DETAILS_SECONDS`
  (86400), `MCP_TRANSPORT` (stdio|sse|streamable-http), `MCP_AUTH_TOKEN`,
  `MCP_HTTP_HOST`/`MCP_HTTP_PORT` (default 127.0.0.1:8765).

## Running / verifying

```bash
uv sync                                  # install
uv run movie-metadata-mcp                # stdio server
uv run pytest && uv run ruff check && uv run mypy src
uv run pytest -m integration             # real APIs; needs .env credentials
npx @modelcontextprotocol/inspector uv run movie-metadata-mcp   # manual verify (needs Node ≥22.7)
```

`uv run pytest` (no marker) runs unit tests only; integration tests are gated by the
`integration` marker and kept out of CI.

## Cache

- `.cache/movie_metadata.sqlite` is created on first real run; the directory is
  gitignored.
