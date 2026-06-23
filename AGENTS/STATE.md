# State

Repo-local snapshot. Overwrite each iteration. Cross-repo view: `../AGENTS/STATE.md`.

## Goal

Aggregate movie metadata (TMDB + OMDb + poiskkino.dev) into a unified, Pydantic-typed
MCP surface, resolving free-text titles to IMDb IDs for downstream servers.

## Now

- Both tools (`search_movie`, `get_movie_details`) implemented and verified via MCP
  Inspector; SQLite TTL cache (1 h / 24 h) live.
- `cartoon` overlay and `number_of_seasons` on series shipped.
- Harness migrated to the `agent-template` layout (AGENTS.md + AGENTS/ + docs/adr/).
- Deployed on the bot host at port 8765.

## Next

- None active. Maintenance only; respond to upstream API changes if they break tests.

## Open questions

- —

## Deferred

- —
