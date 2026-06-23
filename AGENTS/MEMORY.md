# Memory

Durable repo-local facts and working agreements for `movie-metadata-mcp` that are NOT
derivable from code, git history, or SPEC/STATE/HISTORY. The ONLY agent memory store
for this repo — read at session start; append a short bullet when you learn something
durable and commit it with the related change. Do not duplicate the root
`../AGENTS/MEMORY.md` (commit identity, host map, push-to-main agreement live there).

## Project facts

- The `kinopoisk` **rating slug** in the `Rating` model stays `"kinopoisk"` even after
  the kinopoisk.dev → poiskkino.dev rebrand — the slug tracks the rating source
  (Кинопоиск website), not the API transport. Don't rename it.
- poiskkino.dev has genuine gaps in IMDb-id mapping (e.g. "Dune" 2021, КП id 409424,
  has no `externalId.imdb`). The IMDb-keyed query alone misses a non-trivial share of
  titles — the `find_by_title` year-matching fallback exists for this, not for auth.
  The 200 req/day free tier has no endpoint-level restrictions confirmed by testing.
- TMDB **v4 Read Access Token** (long `eyJ…` JWT), NOT the short v3 API key. The
  client uses v3 endpoints with v4 Bearer auth.
- structlog logs go to **stderr** — stdout is reserved for the stdio JSON-RPC frames.
  Never log to stdout.
- The `_kind` key TMDB payloads carry through the merge is internal plumbing (movie vs
  tv field layout), not part of any wire contract.

## Working agreements

- Integration tests (`-m integration`) hit real TMDB/OMDb/poiskkino and stay out of CI;
  they skip when any of the three tokens is missing so CI is offline-safe.
