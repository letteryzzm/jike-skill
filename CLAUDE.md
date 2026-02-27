# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install (editable, with test deps)
pip install -e ".[qr]"
pip install pytest

# Run all tests
pytest

# Run a single test file
pytest tests/test_client.py

# Run a single test
pytest tests/test_client.py::TestJikeClientFeed::test_feed_basic

# Build distribution
pip install hatchling && python -m hatchling build
```

## Architecture

This repo serves two purposes simultaneously:

1. **`pip install jike-skill`** — a typed Python package (`src/jike/`)
2. **Claude Code skill** — standalone scripts in `scripts/` that need zero pip install (only `requests`)

### Dual-mode design

- `src/jike/` — the installable package; `JikeClient`, `TokenPair`, `authenticate` are the public API
- `scripts/` — self-contained copies of the same logic for AI agent use; they import nothing from `src/jike/`
- `SKILL.md` — the skill definition Claude reads; kept lean; detailed API in `references/api.md`
- `.claude-plugin/` — plugin marketplace metadata (not code)

### Key files

| File | Role |
|------|------|
| `src/jike/types.py` | `TokenPair` (frozen dataclass), `API_BASE`, `DEFAULT_HEADERS` |
| `src/jike/auth.py` | QR login flow: `create_session` → `poll_confirmation` → `refresh_tokens` |
| `src/jike/client.py` | `JikeClient` with auto-refresh on 401; CLI dispatch table |
| `src/jike/__main__.py` | Routes `jike auth` → auth module, everything else → client module |
| `scripts/auth.py` | Standalone version of auth (no package imports) |
| `scripts/client.py` | Standalone version of client (no package imports) |
| `scripts/export.py` | Paginated full-history export to Markdown |

### Token lifecycle

- `TokenPair` is an immutable frozen dataclass; refresh always returns a **new** instance
- `JikeClient._request` auto-retries once on 401 by calling `_refresh()`, which mutates `self._tokens`
- All API calls require `Origin: https://web.okjike.com` (Jike blocks requests without it)
- API base: `https://api.ruguoapp.com`

### Pagination

Jike uses a cursor pattern: responses include `loadMoreKey`; pass it back as `loadMoreKey` in the next request body. `load_more_key=None` fetches the first page.

### Analyze user posts (skill workflow)

When used as a Claude Code skill and asked to analyze a user's posts:

1. Parse username from input — direct name or `https://okjike.com/u/USERNAME` URL
2. Run `python3 scripts/export.py --username USERNAME --access-token AT --refresh-token RT --output /tmp/jike_USERNAME.md`
3. Read the output file and analyze per the user's request

`export.py` handles full pagination automatically (all pages, rate-limited at 0.5s between calls). Output format is Markdown with timestamp, content, topic tag, repost info, and post ID per entry.

### Tests

Tests use `unittest.mock` to patch `requests.request` / `requests.post` / `requests.get`. No live network calls. All fixtures live in `tests/conftest.py`.
