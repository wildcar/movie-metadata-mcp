# history — movie-metadata-mcp

Per-repo task log. Each code-change task adds a short entry **before** work
starts. Cross-repo context lives in the workspace root's `history.md`.

---

## 2026-04-18

### Initial scaffold (Step A)
- Bootstrapped with `uv init --package --lib --python 3.12`; rewrote
  `pyproject.toml` with the runtime and dev dependency sets agreed in
  `../techspec.md`. Build backend: `uv_build`.
- Declared a `movie-metadata-mcp` console-script entrypoint pointing at
  `movie_metadata_mcp.server:main`.
- Added `src/movie_metadata_mcp/{__init__,models,config,tools,server}.py`:
  - `models.py` defines the Pydantic tool-I/O types (`MovieSearchResult`,
    `MovieDetails`, `Rating`, and the `SearchMovieResponse` /
    `GetMovieDetailsResponse` envelopes, plus `ToolError`).
  - `config.py` wraps env vars via `pydantic-settings`.
  - `tools.py` exposes `search_movie` and `get_movie_details` as async
    functions currently returning a `not_implemented` `ToolError`.
  - `server.py` registers both tools with `FastMCP`, configures structlog
    to stderr (stdout is reserved for stdio transport), and reads
    `MCP_TRANSPORT` from env (default `stdio`).
- `cache.py` and `clients/` are intentionally deferred to Step B (no empty
  files).
- Added `.env.example` with obtain-instructions for TMDB / OMDb / kinopoisk.dev,
  `README.md`, `Dockerfile` (uv-based, non-root, pinned uv 0.11.7), and a
  GitHub Actions CI workflow (`ruff`, `ruff format --check`, `mypy`,
  `pytest` on Python 3.11 & 3.12, excluding the `integration` marker).
- Local verification: `uv sync` OK, `ruff check` OK, `ruff format --check`
  OK, `mypy --strict` OK, `build_server()` constructs and exposes both
  tools.
- Remote `wildcar/movie-metadata-mcp` created and initial commit pushed.
