# NBD — Node Big Deal: Hermes Fleet Plugin

A Hermes dashboard plugin for managing a fleet of connected Hermes agents.
Nodes expose their API via `hermes proxy` and register with the fleet orchestrator.

## Quick Start

```bash
# 1. Install the plugin
cp -r dashboard-plugin ~/.hermes/dashboard-plugins/hermes-fleet

# 2. Install the skill
cp skill/SKILL.md ~/.hermes/skills/hermes-fleet/SKILL.md

# 3. Restart the dashboard
hermes dashboard --host 0.0.0.0 --port 9119
```

Open `http://<your-ip>:9119` → **Fleet** tab.

## How Nodes Connect

Each remote Hermes agent:

```bash
# Expose the agent as an OpenAI-compatible API
hermes proxy --port 8080

# Register with the fleet
curl -X POST http://<ORCH_IP>:9119/api/plugins/hermes-fleet/nodes/register \
  -H "Content-Type: application/json" \
  -d '{"api_url": "http://<NODE_IP>:8080", "name": "my-node"}'
```

The node appears in the Fleet dashboard automatically.

## Structure

```
nbd/
├── dashboard-plugin/       # Hermes dashboard plugin
│   ├── manifest.json       # Plugin manifest
│   ├── plugin_api.py       # Backend API (registration, chat, sessions)
│   └── dist/
│       └── index.js        # React UI (Fleet tab)
├── skill/
│   └── SKILL.md            # Hermes skill for the orchestrator agent
└── README.md
```

## API Endpoints

All at `/api/plugins/hermes-fleet/`:

| Method | Path | Description |
|---|---|---|
| GET | `/nodes` | List nodes |
| POST | `/nodes/register` | Register a node |
| POST | `/nodes/heartbeat` | Heartbeat |
| GET | `/sessions` | List sessions |
| GET | `/sessions/{id}` | Session with messages |
| POST | `/chat` | Chat with a node (auto-stores session) |
