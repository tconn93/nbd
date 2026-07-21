---
name: hermes-fleet
description: "Use when managing a fleet of Hermes agents. Lets you list nodes, chat with remote agents, view session history, and run setup."
version: 1.0.0
author: Rork
license: MIT
metadata:
  hermes:
    tags: [fleet, orchestration, multi-agent, proxy]
    related_skills: []
---

# Hermes Fleet Skill

Load this skill to manage a fleet of connected Hermes agents.
Nodes expose their API via `hermes proxy` and register with the master.

## Setup

### On the Master machine:
```bash
~/nbd/hermes-fleet setup master
```
This installs the dashboard plugin, configures auth, and starts the dashboard.

### On each Node machine:
```bash
~/nbd/hermes-fleet setup node --master http://<master-ip>:9119
```
This starts `hermes proxy` and registers with the master.

## Fleet API

All endpoints on the master at `http://localhost:9119/api/plugins/hermes-fleet/`:

### List all nodes
```python
from hermes_tools import terminal
result = terminal("curl -s http://localhost:9119/api/plugins/hermes-fleet/nodes")
```

### Chat with a node (auto-stores session)
```python
from hermes_tools import execute_code
result = execute_code("""
import httpx, json
r = httpx.post('http://localhost:9119/api/plugins/hermes-fleet/chat',
    json={"node_id": "node-abc123", "prompt": "What is your status?"})
print(r.json()['reply'])
""")
```

### View a node's sessions
```bash
curl -s http://localhost:9119/api/plugins/hermes-fleet/sessions?node_id=node-abc123
```

### View full conversation
```bash
curl -s http://localhost:9119/api/plugins/hermes-fleet/sessions/ses-abc123
```

## Dashboard

Open `http://<master-ip>:9119` → **Fleet** tab.

Shows all connected nodes with status indicators. Click a node to expand and see its sessions. Click a session to read the full conversation history.
