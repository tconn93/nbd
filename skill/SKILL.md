---
name: hermes-fleet
description: "Use when managing connected Hermes agent nodes. Lets you list nodes, chat with remote agents, and view session history."
version: 1.0.0
author: Rork
license: MIT
metadata:
  hermes:
    tags: [fleet, orchestration, multi-agent, proxy]
    related_skills: []
---

# Hermes Fleet Skill

Load this skill to manage a fleet of connected Hermes agent nodes.
Nodes expose their OpenAI-compatible API via `hermes proxy` and register with the fleet.

## How Nodes Connect

Each remote Hermes agent runs:

```bash
hermes proxy --port 8080
```

Then registers with the fleet orchestrator:

```bash
curl -X POST http://<ORCHESTRATOR_IP>:9119/api/plugins/hermes-fleet/nodes/register \
  -H "Content-Type: application/json" \
  -d '{"api_url": "http://<NODE_IP>:8080", "name": "my-node-1"}'
```

Once registered, the node appears in the Fleet dashboard tab and I can interact with it.

## Fleet API Endpoints

All endpoints at `http://localhost:9119/api/plugins/hermes-fleet/`

### Nodes
| Method | Path | Description |
|---|---|---|
| GET | `/nodes` | List all registered nodes and their status |
| GET | `/nodes/{id}` | Get node details |
| POST | `/nodes/register` | Register/update a node |
| POST | `/nodes/heartbeat` | Send a heartbeat |

### Sessions
| Method | Path | Description |
|---|---|---|
| GET | `/sessions` | List all sessions (filter by `?node_id=`) |
| GET | `/sessions/{id}` | Get session with all messages |
| POST | `/sessions` | Create a new session |
| POST | `/sessions/{id}/messages` | Add a message to a session |

### Chat
| Method | Path | Description |
|---|---|---|
| POST | `/chat` | Send prompt to a node, get reply, auto-saves session |
| | | Body: `{"node_id": "...", "prompt": "..."}` |

## Agent Tools (How I Use This)

When this skill is loaded, I can interact with the fleet using `execute_code` (Python with httpx) or `terminal` (curl):

### List all nodes
```python
from hermes_tools import terminal
result = terminal("curl -s http://localhost:9119/api/plugins/hermes-fleet/nodes")
```

### Chat with a node
```python
from hermes_tools import terminal
result = terminal('''curl -s -X POST http://localhost:9119/api/plugins/hermes-fleet/chat \\
  -H "Content-Type: application/json" \\
  -d '{"node_id": "node-abc123", "prompt": "What is the status of your system?"}' ''')
```

### View a node's sessions
```python
from hermes_tools import terminal
result = terminal("curl -s http://localhost:9119/api/plugins/hermes-fleet/sessions?node_id=node-abc123")
```

### View session conversation
```python
from hermes_tools import terminal
result = terminal("curl -s http://localhost:9119/api/plugins/hermes-fleet/sessions/ses-abc123")
```

## Dashboard

Open the Hermes Dashboard at `http://<orch-ip>:9119` and click the **Fleet** tab.
- See all connected nodes and their online/offline status
- Click a node to expand and see its sessions
- Click a session to read the full conversation

## Common Workflows

### "Check fleet health"
```bash
curl -s http://localhost:9119/api/plugins/hermes-fleet/nodes | jq '.nodes[] | {name: .name, status: .status, url: .api_url}'
```

### "Send a task to a specific node"
```bash
curl -s -X POST http://localhost:9119/api/plugins/hermes-fleet/chat \
  -H "Content-Type: application/json" \
  -d '{"node_id": "node-xyz", "prompt": "Run diagnostics and report back"}'
```

### "What did we talk about with node-xyz?"
```bash
curl -s http://localhost:9119/api/plugins/hermes-fleet/sessions?node_id=node-xyz
# Then pick a session_id and:
curl -s http://localhost:9119/api/plugins/hermes-fleet/sessions/ses-abc123
```
