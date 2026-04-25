# history — movie-metadata-mcp

Per-repo task log. Each code-change task adds a short entry **before** work
starts. Cross-repo context lives in the workspace root's `history.md`.

---

## 2026-04-25

### Expose `number_of_seasons` on series details

- The bot needs the season count to render a season picker before
  the rutracker search (`dl:` for series should let the user pick
  «Сезон 1…N» rather than search the whole show blindly).
- Add `number_of_seasons: int | None` to the `MovieDetails` model;
  populate it from TMDB's `tv/{id}` response (`number_of_seasons`
  field) when `kind == "series"`. Movies and series without a
  TMDB-known season count keep `None`.

---

## 2026-04-23

### Expose КиноПоиск title id to downstream clients
- Extend `MovieDetails` with `kinopoisk_id` so frontends can build direct
  hyperlinks to the official КиноПоиск title page when rendering the ratings
  line in the details card.
- Cover the merged-details path with a test assertion that the poiskkino id
  is preserved in the MCP response.

### Align README with implemented server state
- Update `README.md` to reflect that `movie-metadata-mcp` is no longer a
  Step A scaffold: the tools are implemented, provider aggregation and the
  SQLite TTL cache are live, and the architecture section should reference
  `clients/poiskkino.py` instead of the old `kinopoisk.py` name.

## 2026-04-18

### Step B — real aggregation logic
- Implement `cache.py`: `SQLiteCache` backed by `aiosqlite`, a single table
  keyed by the tool name + canonical-JSON args, with per-entry TTL and lazy
  expiration on read.
- Implement upstream clients under `clients/`:
  - `tmdb.py` — TMDB v3 API with v4 Bearer auth; `search_movie` +
    `get_external_ids` + `find_by_imdb` + `get_details`.
  - `omdb.py` — OMDb `?i={imdb_id}` lookup; parses `Response` / `Error`
    gracefully.
  - `poiskkino.py` — `https://api.poiskkino.dev/v1.4/movie?externalId.imdb=...&limit=1`
    with `X-API-KEY` header; returns the first `docs[]` entry.
- Add `context.py` with an `AppContext` dataclass and
  `build_app_context()` async context manager that owns the three
  `httpx.AsyncClient`s and the cache.
- Rewrite `tools.py`:
  - `search_movie`: TMDB text search → for the top 5 candidates fetch
    external ids in parallel to populate `imdb_id`; cache keyed by
    `(title, year)` with the search TTL.
  - `get_movie_details`: `asyncio.gather(TMDB find+details, OMDb, Poiskkino)`
    with `return_exceptions=True`. Merge fields; downed providers are
    logged and appended to `sources_failed` rather than failing the call.
- Switch `server.py` to an async `amain()` using the closure pattern:
  `build_context()` is awaited before `run_stdio_async()`, and tool
  handlers are thin wrappers that close over the context.
- Unit tests via `respx` per client, plus a tools test with in-memory
  fake clients; cache tests cover set / get / expiration / eviction.
- Integration tests (`@pytest.mark.integration`) hit the real APIs using
  credentials from `.env`; they are skipped when any of the three tokens
  is missing so CI stays offline-safe.
- **poiskkino title-fallback**: integration testing against real data
  surfaced that poiskkino.dev has genuine gaps in IMDb-id mapping — e.g.
  "Dune" (2021) exists in their DB (KP id 409424) but its record has no
  `externalId.imdb` populated, so the primary filter query returns empty
  for a non-trivial share of titles. Added ``PoiskkinoClient.find_by_title``
  (``/v1.4/movie/search?query=``) and, in ``get_movie_details_impl``, a
  second-chance lookup: if the IMDb-based call returns nothing but TMDB
  supplied a title + year, we do one additional search request and pick
  the year-matching candidate. Confirmed no tier-level endpoint
  restrictions on the 200-req/day free plan — this is a data coverage
  issue, not an auth one.

### Rebrand `kinopoisk.dev` → `poiskkino.dev`
- Provider changed its brand. New endpoints: site `https://poiskkino.dev`, API `https://api.poiskkino.dev`, Telegram bot `@poiskkinodev_bot`, docs `poiskkino.dev/documentation`.
- Renamed env var `KINOPOISK_DEV_TOKEN` → `POISKKINO_DEV_TOKEN`; Pydantic field `Settings.kinopoisk_dev_token` → `poiskkino_dev_token`.
- Updated `README.md`, `.env.example`, `pyproject.toml` description, server/tool descriptions, `models.py` docstring, per-repo `env.md`.
- Rating source slug in the `Rating` model stays `"kinopoisk"` — the rating is from the Кинопоиск website, not the API aggregator; the slug tracks the rating source, not the transport.
- Re-verified CI gates locally (`ruff`, `ruff format`, `mypy --strict`, `pytest`). Commit + push.

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
