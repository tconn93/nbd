# nbd — Node Big Deal: Hermes Fleet Orchestration

Manage a fleet of Hermes agents. One master orchestrator, many worker nodes.

## Quick Start

### Master (one command)

```bash
git clone git@github.com:tconn93/nbd.git ~/nbd
cd ~/nbd && ./nbd setup master
```

Follow the interview prompts — choose a database backend (SQLite, Postgres, or Docker Postgres), and the installer handles the rest.

Open `http://<your-ip>:9119` → **Fleet** tab.

### Node (one command)

```bash
~/nbd/nbd setup node --master http://<master-ip>:9119
```

Nodes register with the master, run `hermes proxy` on port 8080, and are immediately available for chat.

### With a registration token (recommended for production)

On the master:
```bash
~/nbd/nbd generate-token --hours 48 --desc "prod-node-01"
```

On the node:
```bash
~/nbd/nbd setup node --master http://<master-ip>:9119 --token <token>
```

## CLI Commands

| Command | Description |
|---|---|
| `nbd setup master` | Interview-style master setup (plugin, DB, auth, service) |
| `nbd setup node --master <url>` | Configure as a worker node |
| `nbd generate-token` | Create time-limited registration tokens (`nbt_*`) |
| `nbd serve` | Start standalone Fleet API server (MCP + HTTP on :9005) |
| `nbd status` | Show fleet config and current status |
| `nbd service install` | Install dashboard as systemd user service |
| `nbd service uninstall` | Remove systemd service |

## Architecture

nbd provides **two ways** to run the fleet backend — use whichever fits your setup:

### Mode A: Dashboard Plugin (default)

```
Master                       Nodes
┌───────────────────┐        ┌──────────────┐
│ hermes dashboard  │  HTTP  │ hermes proxy │
│ port :9119        │◄──────►│ port :8080   │
│ Fleet tab (React) │        └──────────────┘
│ SQLite / Postgres │
│ Plugin API        │
│ /api/plugins/nbd/ │
└───────────────────┘
```

Set up with `nbd setup master`. The Fleet API lives inside `hermes dashboard` as a plugin.

### Mode B: Standalone API Server

```
Master                       Nodes
┌───────────────────┐        ┌──────────────┐
│ nbd serve         │  HTTP  │ hermes proxy │
│ port :9005        │◄──────►│ port :8080   │
│ MCP (SSE) + HTTP  │        └──────────────┘
│ Fleet DB          │
│ /api/plugins/nbd/ │
└───────────────────┘
```

Start with `nbd serve`. Exposes the same HTTP API plus MCP tools over SSE for agent-to-agent orchestration.

### How Nodes Connect

1. The node runs `hermes proxy --port 8080` (OpenAI-compatible API)
2. It POSTs its URL to the master's `/api/plugins/nbd/nodes/register`
3. The master stores the node in the fleet database
4. Nodes send heartbeats every 60s; stale (>3min) nodes are marked offline

## Database Backends

During `nbd setup master`, you choose one of:

| Backend | Description |
|---|---|
| **SQLite** (default) | Zero setup, stores at `~/.hermes/fleet.db` |
| **Postgres** | Connection URL to an existing Postgres instance |
| **Docker Postgres** | Auto-deploys a `postgres:16-alpine` container with persisted volume |

Set `NBD_DATABASE_URL` env var to override at runtime.

## API Endpoints

### Dashboard Plugin Mode — `/api/plugins/nbd/`

| Method | Path | Description |
|---|---|---|
| `GET` | `/nodes` | List all registered nodes |
| `GET` | `/nodes/{id}` | Node details |
| `POST` | `/nodes/register` | Register/update a node (token-optional) |
| `POST` | `/nodes/heartbeat` | Heartbeat (marks stale after 3min) |
| `GET` | `/sessions` | List sessions (`?node_id=` to filter) |
| `GET` | `/sessions/{id}` | Session with full message history |
| `POST` | `/sessions` | Create a new session |
| `POST` | `/sessions/{id}/messages` | Add message to session |
| `POST` | `/chat` | Send prompt to node, auto-stores session |
| `GET` | `/setup-command` | Get master URL + connect command |
| `POST` | `/tokens/generate` | Create registration token |
| `GET` | `/tokens` | List tokens (with expired/used status) |

### Standalone Server Mode — same paths at `http://<host>:9005`

| Path | Description |
|---|---|
| `/api/plugins/nbd/...` | Same HTTP API as plugin mode |
| `/mcp` | SSE endpoint for MCP tools |
| `/health` | Health check |

### MCP Tools (standalone server only, SSE transport)

| Tool | Description |
|---|---|
| `nbd_list_nodes` | List all registered nodes with status |
| `nbd_node_status` | Get detailed status for a specific node |
| `nbd_chat_with_node` | Send a prompt to a node, get response |
| `nbd_get_sessions` | List sessions (optionally filtered by node) |
| `nbd_get_session` | Get full conversation history for a session |
| `nbd_generate_token` | Generate a time-limited registration token |

## Token-Based Registration

Tokens prevent unauthorized nodes from joining your fleet. Generate them on the master:

```bash
nbd generate-token --hours 24 --desc "staging-node"
# → Token: nbt_abc123... expires 2026-07-22T12:00:00
```

Tokens are:
- Stored in the fleet database with expiry and usage tracking
- Validated by `/nodes/register` before a node is accepted
- One-time use (marked `used_at` after registration)
- Also generated automatically by the `/setup-command` endpoint

## Repo Structure

```
nbd/
├── nbd                         # CLI entry point (chmod +x, zero deps)
├── server.py                   # Standalone Fleet API (MCP + HTTP, port 9005)
├── plugins/nbd/                # Hermes agent plugin (tools for the agent)
│   ├── __init__.py             # Plugin registration (5 tools)
│   ├── plugin.yaml             # Plugin manifest
│   ├── tools.py                # Tool handlers (agent-side HTTP calls)
│   ├── schemas.py              # Tool schemas (what the LLM sees)
│   └── dashboard/              # Dashboard UI plugin
│       ├── manifest.json       # Tab config (label "Fleet", path /fleet)
│       ├── plugin_api.py       # Full fleet API backend
│       └── dist/index.js       # React frontend bundle
└── skill/SKILL.md              # Hermes agent skill for fleet management
```

## Dashboards Tab

The **Fleet** tab appears in the Hermes dashboard nav bar (after Skills). Shows:
- All connected nodes with green/yellow/red status dots
- Click to expand: node URL, last heartbeat, sessions
- Click a session to read the full conversation history
- Auto-refreshes every 15 seconds

Default login: `admin` / `hermes`

## Chat Endpoint Details

`POST /chat` with body `{"node_id": "...", "prompt": "..."}`:

1. Looks up the node's API URL from the DB
2. Calls `POST <node_url>/v1/chat/completions` with the prompt
3. Stores the user message and assistant reply in a session
4. Returns `{"session_id": "...", "reply": "..."}`

Optional `session_id` field to append to an existing conversation.

## Pitfalls

1. **`plugins.enabled` must be a YAML list.** `hermes config set` stores lists as strings. Always edit `config.yaml` directly or use PyYAML to write `plugins.enabled` as a proper YAML list.

2. **Dashboard auth for network binding.** Using `--host 0.0.0.0` requires basic auth or OAuth. Configured automatically during `setup master`.

3. **API routes require auth when bound to network.** Plugin APIs are unprotected on localhost but require session cookies on public bind. Use localhost or tunnel for automated scripts.

4. **Node proxy URL must be reachable from master.** The master calls the node's OpenAI API directly — nodes need a route back, not just outbound to master.

5. **`hermes proxy` must be running.** If `hermes proxy` isn't running on the node, `/chat` calls return connection errors. Verify with `curl <node-url>/v1/models`.

6. **Stale nodes.** Nodes are marked offline after 3 minutes without a heartbeat. The `nodes` endpoint runs this check on every call.
