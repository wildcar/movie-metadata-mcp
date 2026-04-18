# env — movie-metadata-mcp

Repo-local environment notes. Workspace-level facts (host OS, `uv`/`gh`
install paths, GitHub auth) live in `../env.md`.

---

## Python / virtualenv

- Managed by `uv`; `.venv/` is created by `uv sync` and is gitignored.
- Interpreter pin: `.python-version` → `3.12` (matches the dev host).
  `pyproject.toml` declares `requires-python = ">=3.11"` so CI can still
  validate on 3.11.

## Local `.env`

- Copy `.env.example` to `.env` and fill in real credentials; `.env` is
  gitignored. `pydantic-settings` reads it automatically.
- Three credentials are required for meaningful integration tests:
  `TMDB_API_TOKEN`, `OMDB_API_KEY`, `KINOPOISK_DEV_TOKEN`. See README for
  obtain-links.

## Running

```bash
uv sync                     # install
uv run movie-metadata-mcp   # stdio server

# MCP Inspector — requires Node.js on the host (not currently installed).
npx @modelcontextprotocol/inspector uv run movie-metadata-mcp
```

## Tests

- `uv run pytest` runs unit tests only (integration tests are gated by the
  `integration` pytest marker).
- `uv run pytest -m integration` hits real TMDB / OMDb / kinopoisk.dev and
  requires credentials in `.env`. Keep this out of CI.

## Cache

- `.cache/movie_metadata.sqlite` is created on first real run (Step B).
  The directory is gitignored.
