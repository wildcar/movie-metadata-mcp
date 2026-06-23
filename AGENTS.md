# Agent Instructions — movie-metadata-mcp

Primary entrypoint for any agent (Claude, Codex, DeepSeek, etc.) working in this
repo. Read this first.

## Workspace

This repo is one of seven siblings in the `movie_handler` multi-repo workspace.
For cross-repo architecture, end-to-end flows, hosts, and shared agreements see
`../AGENTS.md` and `../AGENTS/SPEC.md`. **When working inside this repo, THIS file
is authoritative** — it has the repo-local spec, state, and history.

## Project

**movie-metadata-mcp** — priority-1 MCP (Model Context Protocol) server. Aggregates
movie metadata from **TMDB**, **OMDb**, and **poiskkino.dev** (formerly kinopoisk.dev)
into a unified, Pydantic-typed response. It is the only server in the system that
resolves free-text titles to an **IMDb ID**, the cross-server correlation key for
metadata lookups consumed by every downstream server (trailer, torrent, download).

## Document Map

| File | Role |
|------|------|
| `AGENTS.md` | This entrypoint. Repo map, workflow, rules. |
| `CLAUDE.md` | Compatibility pointer to `AGENTS.md`. |
| `AGENTS/SPEC.md` | Repo functional + technical spec: tools, upstreams, cache, structure. |
| `AGENTS/STATE.md` | Current snapshot: goal, now, next, open questions, deferred. |
| `AGENTS/HISTORY.md` | Repo iteration log, newest first. |
| `AGENTS/MEMORY.md` | Durable repo-local facts/agreements not derivable from code/git. |
| `AGENTS/ENV.md` | Repo-local env detail; shared host/deploy facts point to `../AGENTS/ENV.md`. |
| `README.md` | Public-facing readme: tool list, env vars, local run, Claude Desktop. |
| `docs/adr/` | Architecture Decision Records (see `docs/adr/TEMPLATE.md`). |

## Environment

- OS / shell: Ubuntu 24.04 / `bash`, user `keeper` (passwordless sudo). See `../AGENTS/ENV.md`.
- Commit identity: `wildcar <wildcar@mail.ru>`. Remote: `github.com/wildcar/movie-metadata-mcp`.
- Python pinned to 3.12 (`.python-version`); `requires-python >=3.11`. Deps via `uv`.

## Startup Checklist

1. Read `AGENTS.md` (this file).
2. Read `AGENTS/SPEC.md` for the tool surface, upstreams, and structure.
3. Read `AGENTS/STATE.md` for the live snapshot.
4. Read the top 3–5 entries in `AGENTS/HISTORY.md`.
5. Read `AGENTS/MEMORY.md` (repo-local facts + agreements).
6. Check `git status --short` before editing. Open `AGENTS/ENV.md` / `../AGENTS/ENV.md`
   only when you need run / credential / host details.

## Change Workflow

For every iteration that changes code or behavior:

1. If the tool contract changes — update `AGENTS/SPEC.md` first (and `../AGENTS/SPEC.md`
   if the cross-repo contract shifts).
2. Make the changes.
3. Run `uv run pytest && uv run ruff check && uv run mypy src` before committing.
4. Overwrite `AGENTS/STATE.md`; prepend a new `AGENTS/HISTORY.md` entry.
5. Commit + push to `main` after verification — no feature branch, no asking.

### `AGENTS/HISTORY.md` entry format (≤5 lines, newest first)

```
## YYYY-MM-DD · <short iteration title>
- What: <one line — what changed>
- Why: <one line — reason / task>
- Files: <key paths, comma-separated>
- Next: <one line — what was planned right after>
```

Keep each entry tight. Long explanations belong in commit messages or `SPEC.md`.

## Memory

`AGENTS/MEMORY.md` is the **single** store of durable agent memory for this repo.
Read it at session start; append a short bullet when you learn a durable fact or
working agreement and commit it with the related change. Do not duplicate the root
`../AGENTS/MEMORY.md`. Split of concerns: durable facts/agreements → `MEMORY.md`;
current snapshot → `STATE.md`; iteration log → `HISTORY.md`.

## Language Rules

- Source code, technical docs, code comments: **English**.
- Conversation with the user: **Russian**.
- End-user-facing strings (overviews, country names) are returned in **Russian**
  (ru-RU) by design — the bot renders them directly.

## Project Rules

- **Structured error returns, not exceptions** across the MCP boundary. Tools return
  a response carrying a `ToolError`; they never raise. A downed upstream degrades
  gracefully (partial results + `sources_failed`).
- **Pydantic models** for all tool I/O (`models.py`); schemas derived by `FastMCP`.
- **Secrets only via env vars** (`pydantic-settings`, `env_file=".env"`); never tool
  args. Ship `.env.example`; never commit a real `.env`.
- **IMDb ID is metadata only** — it is this server's output key for downstream lookups,
  never a download key (the bot uses the composite `media_id` for that).
- **Transport:** `stdio` for local dev / Inspector / Claude Desktop; HTTP+SSE or
  streamable-HTTP with Bearer `MCP_AUTH_TOKEN` for networked use (port 8765).
- **Every commit passes `ruff` + `mypy --strict` + `pytest` locally before push.**
  Commit + push to `main` directly. Integration tests (`-m integration`) hit real
  APIs and stay out of CI.

## Stack & Commands

Python ≥ 3.11, `asyncio`, `httpx`, official Anthropic `mcp` SDK (`FastMCP`),
`pydantic` v2 + `pydantic-settings`, `structlog` (JSON to stderr), `aiosqlite` TTL
cache, `uv` for deps. Tests: `pytest` + `pytest-asyncio` + `respx`.

```bash
uv sync                                  # install / sync deps
uv run movie-metadata-mcp                # run over stdio
uv run pytest && uv run ruff check && uv run mypy src
uv run pytest -m integration             # hits real TMDB/OMDb/poiskkino (needs .env)
npx @modelcontextprotocol/inspector uv run movie-metadata-mcp   # manual verify
```

## Architecture

```
search_movie / get_movie_details (FastMCP tools, server.py)
        │
   tools.py  ── asyncio.gather across providers, downed ones → sources_failed
        ├─→ clients/tmdb.py       (primary: search, external-id → IMDb, details)
        ├─→ clients/omdb.py       (IMDb / Metacritic ratings, gap-fill)
        └─→ clients/poiskkino.py  (RU description, КП rating; title fallback)
        │
   cache.py  ── SQLite TTL cache (1 h search / 24 h details), keyed by tool+args
```

`context.py` owns the three `httpx.AsyncClient`s + cache for the server's lifetime
(only instantiates a client when its token is present). See `AGENTS/SPEC.md` for the
full tool signatures, merge precedence, and cartoon/series detection.

## Code Style

- Match surrounding conventions: comment density, naming, idiom.
- `ruff` format + lint (line-length 100, double quotes), `mypy --strict`.
- `from __future__ import annotations` at the top of every module.
