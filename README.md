# movie-metadata-mcp

MCP (Model Context Protocol) server that aggregates movie metadata from
**TMDB**, **OMDb**, and **poiskkino.dev** (formerly kinopoisk.dev) into a
unified response. It is the
first of five servers in the [`movie_handler`](../) system and the only one
that resolves free-text titles to an **IMDb ID** — the cross-server
correlation key used by every downstream server (trailer, torrent search,
download manager).

> Status: **Step A — scaffolding.** The server starts, registers its tools,
> and validates schemas, but the tool bodies return a `not_implemented`
> error. Real aggregation logic lands in Step B.

---

## Tools

| Tool | Input | Returns |
|---|---|---|
| `search_movie` | `title: str`, `year: int \| None` | `SearchMovieResponse` — list of candidates (IMDb ID, TMDB ID, title, year, poster, short overview) merged across the three providers. |
| `get_movie_details` | `imdb_id: str` | `GetMovieDetailsResponse` — poster, plot (EN + RU), ratings (IMDb / TMDB / Кинопоиск), genres, director, cast, runtime. |

Both tools return structured responses with a `sources_failed` list when a
provider is down, and never raise through the MCP boundary.

Full schemas: see [`src/movie_metadata_mcp/models.py`](src/movie_metadata_mcp/models.py).

## Environment variables

All configuration is read from env vars / `.env`. Copy `.env.example` →
`.env` and fill in values. The most important ones:

| Variable | Required | Purpose |
|---|---|---|
| `TMDB_API_TOKEN` | yes | TMDB API Read Access Token (v4). Posters, descriptions, IMDb IDs, trailers metadata. |
| `OMDB_API_KEY` | yes | OMDb — IMDb rating, Metacritic. |
| `POISKKINO_DEV_TOKEN` | yes | poiskkino.dev — КП rating, Russian description. |
| `CACHE_PATH` | no | SQLite path. Default `.cache/movie_metadata.sqlite`. |
| `CACHE_TTL_SEARCH_SECONDS` | no | Default `3600` (1 h). |
| `CACHE_TTL_DETAILS_SECONDS` | no | Default `86400` (24 h). |
| `MCP_TRANSPORT` | no | `stdio` \| `sse` \| `streamable-http`. Default `stdio`. |
| `MCP_AUTH_TOKEN` | only for networked transports | Bearer token checked on every HTTP request. |

### How to obtain API keys

- **TMDB** → <https://www.themoviedb.org/settings/api>. Create an account,
  request a Developer key (free, a one-line justification is accepted), then
  copy the long **"API Read Access Token"** (JWT-like string). That is the
  v4 token this server expects; do **not** use the short v3 API key.
- **OMDb** → <https://www.omdbapi.com/apikey.aspx>. Pick the FREE tier
  (1000 req/day), confirm via email — the key arrives in that email.
- **poiskkino.dev** → Telegram bot [@poiskkinodev_bot](https://t.me/poiskkinodev_bot)
  (the service rebranded from `kinopoisk.dev` — the old bot is discontinued).
  Send `/api` to request a token; the free tier (200 req/day) is plenty for
  development. Site <https://poiskkino.dev>, API `https://api.poiskkino.dev`,
  docs <https://poiskkino.dev/documentation>.

## Local development

Prerequisites: Python ≥ 3.11 and [`uv`](https://docs.astral.sh/uv/).

```bash
# Install deps (creates .venv, generates uv.lock if missing)
uv sync

# Run the server over stdio
uv run movie-metadata-mcp

# Tests / lint / types
uv run pytest
uv run ruff check
uv run mypy src

# Run integration tests that hit real upstream APIs (requires .env with keys)
uv run pytest -m integration
```

### Inspecting tools with MCP Inspector

The Inspector is the quickest way to exercise the tool surface without a
Claude client. It requires Node.js on your machine.

```bash
npx @modelcontextprotocol/inspector uv run movie-metadata-mcp
```

Then open the printed URL, pick either tool, and send a sample payload.

### Connecting to Claude Desktop

Add this block to Claude Desktop's `claude_desktop_config.json`
(`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS,
`%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "movie-metadata": {
      "command": "uv",
      "args": ["--directory", "/ABS/PATH/TO/movie-metadata-mcp", "run", "movie-metadata-mcp"],
      "env": {
        "TMDB_API_TOKEN": "...",
        "OMDB_API_KEY": "...",
        "POISKKINO_DEV_TOKEN": "..."
      }
    }
  }
}
```

Restart Claude Desktop; the two tools will appear under the 🔨 menu.

## Docker

```bash
docker build -t movie-metadata-mcp .
docker run --rm --env-file .env movie-metadata-mcp
```

By default the container runs over stdio. For networked use:

```bash
docker run --rm --env-file .env -e MCP_TRANSPORT=sse -p 8000:8000 movie-metadata-mcp
```

## Architecture

See the cross-repo [`../techspec.md`](../techspec.md). Specific to this
server:

- Three upstream clients (`clients/tmdb.py`, `omdb.py`, `kinopoisk.py`) share
  no state; each owns its `httpx.AsyncClient` lifecycle.
- `tools.py` fans out provider calls via `asyncio.gather(..., return_exceptions=True)`,
  logs failing sources, and merges what came back.
- `cache.py` is a thin SQLite-backed TTL cache keyed by `(tool, args)`.
- MCP schemas are derived from the Pydantic models in `models.py` by `FastMCP`.

## Project layout

```
movie-metadata-mcp/
├── pyproject.toml
├── uv.lock
├── .env.example
├── Dockerfile
├── history.md
├── env.md
├── .github/workflows/ci.yml
├── src/movie_metadata_mcp/
│   ├── server.py        # MCP entrypoint
│   ├── tools.py         # tool implementations
│   ├── models.py        # pydantic I/O models
│   ├── config.py        # env-var-driven settings
│   ├── cache.py         # SQLite TTL cache          (Step B)
│   └── clients/         # upstream API clients      (Step B)
└── tests/
```

## License

MIT.
