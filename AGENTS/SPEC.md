# movie-metadata-mcp — functional & technical specification

Repo-local source of truth for *what this server does* and *how it is built*. The
cross-repo contract lives in `../AGENTS/SPEC.md`; this document is the detail for
this server only.

## Purpose

Priority-1 MCP server. Given a free-text title (optionally a year) it returns a
unified candidate list with IMDb IDs; given an IMDb ID it returns merged full
metadata (poster, EN + RU plot, ratings, genres, director, cast, runtime, season
count, kind). It is the **only** server doing fuzzy text movie lookup and the only
producer of the IMDb ID that downstream metadata consumers key on.

## Stack

- Python ≥ 3.11 (3.12 in dev), `asyncio`, `httpx`.
- MCP: official Anthropic `mcp` SDK, `FastMCP`; tools typed with Pydantic v2.
- Config/secrets: `pydantic-settings` (`env_file=".env"`).
- Logging: `structlog`, JSON to **stderr** (stdout reserved for stdio JSON-RPC).
- Cache: SQLite via `aiosqlite`. Deps: `uv` (`uv.lock`). Build backend: `uv_build`.
- Lint/types/tests: `ruff`, `mypy --strict`, `pytest` + `pytest-asyncio` + `respx`.
- CI: GitHub Actions (`ruff` → `ruff format --check` → `mypy` → `pytest`, Py 3.11 & 3.12,
  excludes the `integration` marker). Container: `Dockerfile` (uv-based, non-root).

## Tools

Both tools return a response envelope carrying an optional `ToolError` and a
`sources_failed: list[str]` — they never raise through the MCP boundary.

| Tool | Signature | Returns |
|------|-----------|---------|
| `search_movie` | `(title: str, year: int \| None = None)` | `SearchMovieResponse` — list of `MovieSearchResult` (kind, imdb_id, tmdb_id, title, original_title, year, poster_url, overview, rating, country). |
| `get_movie_details` | `(imdb_id: str)` | `GetMovieDetailsResponse` — `MovieDetails` (imdb_id, kind, tmdb_id, kinopoisk_id, title, original_title, year, runtime_minutes, genres, directors, cast, overview, overview_ru, poster_url, number_of_seasons, ratings[]). |

- `TitleKind = "movie" | "series" | "cartoon"`. `search_movie` only ever emits
  `movie`/`series` (no genre data at search time); `cartoon` is produced solely by
  `get_movie_details` as an animation overlay on a movie-shaped title (animated TV
  stays `series` so the bot's per-season picker keeps working).
- `Rating(source, value, scale, votes?)`. Sources: `tmdb`, `imdb`, `metacritic`,
  `kinopoisk`. The `kinopoisk` slug tracks the rating source (Кинопоиск website),
  not the transport — it stays after the kinopoisk.dev → poiskkino.dev rebrand.
- Validation: empty `title` → `invalid_argument`; `imdb_id` not starting with `tt`
  → `invalid_argument`; TMDB unconfigured for search → `no_primary_source`; all
  providers empty → `not_found`.

## Upstreams & resolution flow

- **TMDB** (primary) — `clients/tmdb.py`. v3 API with v4 Bearer auth. `search_movie`
  + `search_tv` (fanned in parallel); top-5 candidates resolve IMDb IDs via
  `external_ids`. `get_movie_details` resolves IMDb → movie or TV via `find_any_by_imdb`,
  then fetches full details. Carries an injected `_kind` key through the merge.
- **OMDb** — `clients/omdb.py`. `?i={imdb_id}` lookup; IMDb rating + Metacritic;
  gap-fills title/year/runtime/genres/directors/cast/plot the primary left empty.
- **poiskkino.dev** — `clients/poiskkino.py`. `externalId.imdb` filter for RU
  description + КП rating + `kinopoisk_id`. Title-fallback (`find_by_title`) when the
  IMDb-keyed query is empty (their DB has genuine IMDb-mapping gaps) and TMDB supplied
  a title + year — picks the year-matching candidate.
- `get_movie_details` fans the three out with `asyncio.gather`; a failing provider is
  logged and appended to `sources_failed`. A provider returning "no match" (`None`) is
  usable info, not a failure (distinguished from the `_FAILED` sentinel by identity).
- **Merge precedence:** TMDB > poiskkino > OMDb for EN fields; poiskkino for RU fields;
  ratings appended from every source reporting a number.

## Cache

`cache.py` — `SQLiteCache` (`aiosqlite`), single `cache` table keyed by canonical
`tool:args` string, per-entry TTL, lazy expiration on read. TTLs: search **3600 s
(1 h)**, details **86400 s (24 h)**. Default path `.cache/movie_metadata.sqlite`.

## Project structure

```
movie-metadata-mcp/
├── pyproject.toml            # deps, ruff/mypy/pytest config, console script
├── uv.lock                   # locked deps
├── .env.example              # env vars + obtain-instructions
├── Dockerfile                # uv-based, non-root, stdio by default
├── README.md                 # public readme (tools, env, run, Claude Desktop)
├── AGENTS.md / CLAUDE.md / AGENTS/   # repo harness
├── docs/adr/                 # Architecture Decision Records
├── .github/workflows/ci.yml  # ruff → format → mypy → pytest (3.11 & 3.12)
├── src/movie_metadata_mcp/
│   ├── server.py             # FastMCP entrypoint; transport select; structlog→stderr
│   ├── tools.py              # search_movie / get_movie_details impls + merge logic
│   ├── models.py             # Pydantic tool I/O types
│   ├── config.py             # pydantic-settings env config
│   ├── context.py            # AppContext: clients + cache lifecycle
│   ├── cache.py              # SQLite TTL cache
│   └── clients/              # tmdb.py, omdb.py, poiskkino.py upstream clients
└── tests/                    # test_{tools,cache,server}.py, clients/, integration/
```

## Transport & config

`MCP_TRANSPORT` ∈ {`stdio` (default), `sse`, `streamable-http`}. HTTP transports bind
`MCP_HTTP_HOST`/`MCP_HTTP_PORT` (default `127.0.0.1:8765`) and require Bearer
`MCP_AUTH_TOKEN`. Env: `TMDB_API_TOKEN`, `OMDB_API_KEY`, `POISKKINO_DEV_TOKEN`
(required for full output), `CACHE_PATH`, `CACHE_TTL_SEARCH_SECONDS`,
`CACHE_TTL_DETAILS_SECONDS`. The server starts even with no tokens; each provider
degrades independently when its key is missing.

## Current state

- ✅ Both tools implemented, provider aggregation + SQLite TTL cache live, verified
  via MCP Inspector. `cartoon` overlay and `number_of_seasons` shipped.
- Deployed on the bot host (`homesrv`) at port 8765. See `../AGENTS/SPEC.md` for how
  it fits the wider system and `AGENTS/STATE.md` for the live snapshot.

## Data sources & dependencies

Upstream APIs: TMDB (primary), OMDb, poiskkino.dev. No outbound dependency on sibling
repos — coordination is one-way (this server emits IMDb IDs others consume).
