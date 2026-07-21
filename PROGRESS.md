# nbd — Session Progress Summary
## Date: 2026-07-21

### What was built
- **Hermes dashboard plugin** at `~/.hermes/plugins/nbd/dashboard/`
  - `manifest.json` — plugin manifest, tab at `/fleet`, label "Node Big Deal"
  - `plugin_api.py` — 12 API routes: nodes, sessions, chat, tokens, setup-command
  - `dist/index.js` — React Fleet tab UI via Hermes Plugin SDK
- **Hermes agent plugin** at `~/.hermes/plugins/nbd/`
  - `plugin.yaml` — manifest declaring 5 tools
  - `__init__.py` — registers tools via `ctx.register_tool()`
  - `schemas.py` — tool schemas for the LLM
  - `tools.py` — tool handlers calling the Fleet API
  - Tools: `nbd_list_nodes`, `nbd_node_status`, `nbd_chat_with_node`, `nbd_get_sessions`, `nbd_get_session`
- **CLI** at `~/nbd/nbd`
  - `nbd setup master` — interview-style: plugin install → config → database → auth → service
  - `nbd setup node --master <url>` — starts proxy, registers with master
  - `nbd generate-token` — creates 24h registration tokens
  - `nbd service install/uninstall` — systemd service management
  - `nbd status` — fleet overview
- **GitHub repo**: `github.com/tconn93/nbd`

### Key decisions
1. **Plugin, not skill** — uses Hermes plugin API (`ctx.register_tool()`) for native tools
2. **Database** — SQLite default, Postgres via `NBD_DATABASE_URL`, Docker Postgres auto-deploy
3. **Tokens** — time-limited (24h default), one-time use, stored in fleet.db's `tokens` table
4. **Service** — systemd user service with linger for persistence

### Known issues
- **Dashboard auth gate** — When bound to `0.0.0.0`, plugin JS and API are behind auth. User must log in first via browser. API calls from curl without session cookie return 401.
- **Plugin JS endpoint** (`/dashboard-plugins/nbd/dist/index.js`) returns 302 when not authenticated — expected behavior, browser sends cookie after login.
- **Tab name** changed from "Fleet" to "Node Big Deal"

### Fleet dashboard URL
- `http://10.0.171.31:9119` — login: admin / hermes

### Skill
- `~/.hermes/skills/nbd/SKILL.md` — agent instructions for fleet management
