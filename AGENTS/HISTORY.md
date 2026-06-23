# History

Newest first. Each entry ≤5 lines using the format defined in `AGENTS.md`. Repo-local
log; cross-repo detail lives in `../AGENTS/HISTORY.md`.

---

## 2026-06-23 · Migrate harness to agent-template layout
- What: Added repo harness (`AGENTS.md`, `CLAUDE.md` pointer, `AGENTS/{SPEC,STATE,HISTORY,MEMORY,ENV}.md`, `docs/adr/TEMPLATE.md`); folded `history.md`→`AGENTS/HISTORY.md`, `env.md`→`AGENTS/ENV.md`.
- Why: Adopt the standard `wildcar/agent-template` harness across all repos.
- Files: `AGENTS.md`, `CLAUDE.md`, `AGENTS/*`, `docs/adr/TEMPLATE.md`; removed `history.md`, `env.md`.
- Next: Maintenance only.

## 2026-04-27 · `get_movie_details` emits `kind="cartoon"` for animated movies
- What: Extended `TitleKind` to `movie|series|cartoon`; added `_looks_like_cartoon` (TMDB Animation genre id 16 + RU/EN filename token fallback). Only `get_movie_details` produces `cartoon`; animated series stay `series`.
- Why: Bot routes animated movies to a separate Cartoon/ dir + 🎨 marker; `kind` is the natural carrier.
- Files: `src/movie_metadata_mcp/models.py`, `tools.py`.
- Next: —

## 2026-04-25 · Expose `number_of_seasons` on series details
- What: Added `number_of_seasons: int | None` to `MovieDetails`, populated from TMDB `tv/{id}` when `kind=="series"`; `None` for movies / un-indexed shows.
- Why: Bot renders a season picker before the rutracker search for series.
- Files: `src/movie_metadata_mcp/models.py`, `tools.py`.
- Next: —

## 2026-04-23 · Expose КиноПоиск id; align README with implemented state
- What: Added `kinopoisk_id` to `MovieDetails` (direct КП hyperlinks) with a merge-path test; rewrote README to reflect the implemented server (tools live, aggregation + cache live, `clients/poiskkino.py`).
- Why: Frontends want a direct КиноПоиск title link; README still described the Step-A scaffold.
- Files: `src/movie_metadata_mcp/models.py`, `tools.py`, tests, `README.md`.
- Next: —

## 2026-04-18 · Step B — real aggregation logic + poiskkino rebrand
- What: Implemented `cache.py` (`SQLiteCache`), `clients/{tmdb,omdb,poiskkino}.py`, `context.py` (`AppContext`); rewrote `tools.py` (parallel fan-out, graceful degradation, poiskkino title-fallback for IMDb-id gaps); async `amain()` closure pattern in `server.py`; unit + integration tests. Rebranded `kinopoisk.dev`→`poiskkino.dev` (env var, field, endpoints) — rating slug stays `"kinopoisk"`.
- Why: Turn the scaffold into a working aggregator; provider rebranded its API.
- Files: `src/movie_metadata_mcp/*`, `tests/*`, `README.md`, `.env.example`, `pyproject.toml`.
- Next: Scaffold the Telegram bot (priority 2).

## 2026-04-18 · Initial scaffold (Step A)
- What: Bootstrapped with `uv init --package --lib` (`uv_build` backend); `movie-metadata-mcp` console script → `server:main`; added `models.py`, `config.py`, stub `tools.py` (returning `not_implemented`), `server.py` (FastMCP, structlog→stderr, `MCP_TRANSPORT`); `.env.example`, `README.md`, `Dockerfile`, CI workflow. Created remote `wildcar/movie-metadata-mcp` and pushed.
- Why: Establish the priority-1 server skeleton with all CI gates green.
- Files: `pyproject.toml`, `src/movie_metadata_mcp/*`, `.github/workflows/ci.yml`, `Dockerfile`, `README.md`.
- Next: Step B — real aggregation logic.
