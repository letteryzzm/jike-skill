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

---

## Web App (`web/`)

Cloudflare Worker，部署地址：`https://jike-radar.jike-analyse.workers.dev`

```bash
# 本地开发
cd web && npx wrangler dev

# 部署
cd web && npx wrangler deploy
```

### 功能需求

**Tab 1 — 人才搜索**
- 输入关键词（逗号分隔）+ 自然语言筛选条件
- Worker 搜索 Jike → 去重 → 批量拉 profile → 调 Gemini 按条件评分筛选
- 结果以大表展示：显示名、主页链接、Bio 摘要、推荐理由、联系方式（有则显示）、年龄（有则显示）、来源关键词
- 支持导出 CSV

**Tab 2 — 用户分析**
- 输入即刻用户链接（`https://web.okjike.com/u/xxx`）或用户名
- 抓取该用户全部（或指定数量）帖子，调 Gemini 做多维度分析
- 分析维度可自定义，留空则默认：兴趣领域、内容风格、技术/产品深度、代表性观点、整体画像
- 结果流式输出，Markdown 渲染

**通用设置**
- Jike Access Token、Refresh Token、Gemini API Key 存 localStorage，刷新后自动恢复
- Token 仅在客户端存储，每次请求随 body 发给 Worker，Worker 不持久化
- 支持扫码登录：点击「扫码登录获取 Token」按钮，用即刻 App 扫描 QR 码，自动获取并填入 Token

**AI 供应商**
- 使用 Google Gemini API（模型：`gemini-3-flash-preview`）
- 非流式调用（人才搜索评分）：`generateContent` 端点
- 流式调用（用户分析）：`streamGenerateContent?alt=sse` 端点
- API Key 以 query 参数传递：`?key=API_KEY`

### 已知坑

**HTML 内嵌 JS 的正则限制**：`web/src/worker.js` 把整个 HTML 作为模板字符串嵌入。HTML `<script>` 块里**禁止使用正则字面量**（`/pattern/`），因为 `<`、`>` 在 HTML 解��阶段会引发误判，导致 `SyntaxError`。一律改用 `.split().join()` 或 DOM API（`div.textContent = s; return div.innerHTML`）替代。

**onclick 属性失效**：HTML 属性里的 `onclick="fn()"` 在部分上下文中找不到函数作用域，一律改用 `addEventListener` 在脚本底部注册。

