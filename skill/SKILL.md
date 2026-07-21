---
name: nbd
description: "Use when managing a fleet of Hermes agents. Lets you list nodes, chat with remote agents, view session history, and run setup."
version: 1.1.0
author: Rork
license: MIT
metadata:
  hermes:
    tags: [fleet, orchestration, multi-agent, proxy, hermes-proxy]
    related_skills: [hermes-dashboard-plugins]
---

# Hermes Fleet Skill

Manage a fleet of Hermes agents using `hermes proxy` (OpenAI-compatible API) with a central orchestrator dashboard.
One master, many worker nodes. Simpler and more reliable than MCP-based orchestration.

## Architecture

```
Master (dashboard + plugin)              Nodes (hermes proxy)
┌────────────────────────┐               ┌──────────────────┐
│ Dashboard :9119        │    HTTP POST  │ hermes proxy :8080│
│ Fleet tab (React)      │◄────────────►│ OpenAI API       │
│                        │   /v1/chat/   │                  │
│ DB: nodes, sessions    │   completions └──────────────────┘
│ Plugin API             │               ┌──────────────────┐
│  /api/plugins/fleet/*  │◄────────────►│ hermes proxy :8081│
└────────────────────────┘               └──────────────────┘
```

**Master** runs `hermes dashboard` with the fleet plugin. Nodes register their URL, and the master proxies chat requests to them via their OpenAI-compatible API. All conversations are stored in SQLite.

**Nodes** run `hermes proxy --port 8080` which exposes an OpenAI API endpoint. They register once and the master connects to them.

## Setup

### One-command Master Setup

```bash
# From the fleet repo:
./nbd setup master
```

This single command:
1. Copies the dashboard plugin to `~/.hermes/plugins/<name>/dashboard/`
2. Adds `hermes-fleet` to `plugins.enabled` in config.yaml (as a proper YAML list)
3. Configures dashboard basic auth (admin / hermes)
4. Kills any old dashboard and starts fresh on port 9119

### One-command Node Setup

```bash
./nbd setup node --master http://<master-ip>:9119
```

This:
1. Starts `hermes proxy --port 8080` in the background
2. Registers with the master via POST to `/api/plugins/hermes-fleet/nodes/register`

### Manual Setup (for automation / non-interactive)

**Master:**
```bash
cp -r plugins/hermes-fleet ~/.hermes/plugins/
# Edit config.yaml: add 'hermes-fleet' to plugins.enabled (YAML list, not string!)
hermes dashboard --host 0.0.0.0 --port 9119
```

**Node:**
```bash
hermes proxy --port 8080 --host 0.0.0.0 &
curl -X POST http://<master>:9119/api/plugins/hermes-fleet/nodes/register \
  -H "Content-Type: application/json" \
  -d '{"api_url": "http://<node-ip>:8080", "name": "node-name"}'
```

## Fleet API (on master)

All at `http://<master>:9119/api/plugins/hermes-fleet/`

| Method | Path | Description |
|---|---|---|
| `GET` | `/nodes` | List all registered nodes |
| `GET` | `/nodes/{id}` | Node details |
| `POST` | `/nodes/register` | Register/update a node |
| `POST` | `/nodes/heartbeat` | Heartbeat (marks stale after 3min) |
| `GET` | `/sessions` | List sessions (`?node_id=` to filter) |
| `GET` | `/sessions/{id}` | Session with full message history |
| `POST` | `/chat` | Send prompt to node, auto-stores session |

### Chat endpoint details

`POST /chat` with body `{"node_id": "...", "prompt": "..."}`:
1. Looks up the node's API URL from the DB
2. Calls `POST <node_url>/v1/chat/completions` with the prompt
3. Stores the user message and assistant reply in a session
4. Returns `{"session_id": "...", "reply": "..."}`

## Dashboard Tab

The **Fleet** tab appears in the nav bar (after Skills). Shows:
- All connected nodes with green/yellow/red status dots
- Click to expand: see node URL, last heartbeat, sessions
- Click a session to read the full conversation history
- Auto-refreshes every 15 seconds

## Interacting as the Agent

When this skill is loaded, use `execute_code` (Python with httpx) to interact:

```python
from hermes_tools import execute_code

# List all nodes
result = execute_code("""
import httpx
r = httpx.get('http://localhost:9119/api/plugins/hermes-fleet/nodes')
print(r.json())
""")

# Chat with a specific node
result = execute_code("""
import httpx
r = httpx.post('http://localhost:9119/api/plugins/hermes-fleet/chat',
    json={"node_id": "node-abc123", "prompt": "Run diagnostics"})
data = r.json()
print(f"Session: {data['session_id']}")
print(f"Reply: {data['reply']}")
""")

# View a session's conversation
result = execute_code("""
import httpx
r = httpx.get('http://localhost:9119/api/plugins/hermes-fleet/sessions/ses-abc123')
msgs = r.json().get('messages', [])
for m in msgs:
    print(f"[{m['role']}] {m['content'][:100]}")
""")
```

## Common Workflows

### "Check fleet health"
```bash
curl -s http://localhost:9119/api/plugins/hermes-fleet/nodes | jq '.nodes[] | {name: .name, status: .status}'
```

### "Send task to a specific node"
```bash
curl -s -X POST http://localhost:9119/api/plugins/hermes-fleet/chat \
  -H "Content-Type: application/json" \
  -d '{"node_id": "node-xyz", "prompt": "check disk space and report"}'
```

### "What conversations happened with node-01?"
```bash
curl -s "http://localhost:9119/api/plugins/hermes-fleet/sessions?node_id=node-01"
# Then pick a session_id and:
curl -s http://localhost:9119/api/plugins/hermes-fleet/sessions/ses-abc123
```

## Pitfalls

1. **plugins.enabled must be a YAML list.** `hermes config set` stores lists as strings. Always edit config.yaml directly or use PyYAML to write `plugins.enabled` as a proper YAML list.

2. **Dashboard auth for network binding.** Use `--host 0.0.0.0` requires basic auth or OAuth. Configure with `dashboard.basic_auth.username` + `password_hash`.

3. **API routes require auth when bound to network.** Plugin APIs are unprotected on localhost but require session cookies on public bind. For automated scripts, use localhost or tunnel.

4. **Node proxy URL must be reachable from master.** The master calls the node's OpenAI API directly — nodes need a route back, not just outbound to master.

5. **hermes proxy must be running.** If `hermes proxy` isn't running on the node, `/chat` calls return connection errors. Check with `curl <node-url>/v1/models`.

6. **Stale nodes.** Nodes are marked offline after 3 minutes without a heartbeat. The `nodes` endpoint runs this check on every call.

