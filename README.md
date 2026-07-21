# NBD — Node Big Deal: Hermes Fleet Plugin

Manage a fleet of Hermes agents. One master orchestrator, many worker nodes.

## Quick Start

### Master (one command)

```bash
git clone git@github.com:tconn93/nbd.git ~/nbd
cd ~/nbd && ./nbd setup master
```

Open `http://<your-ip>:9119` → **Fleet** tab.

### Node (one command)

```bash
~/nbd/nbd setup node --master http://<master-ip>:9119
```

## How Nodes Connect

The master auto-detects its own IP and displays the exact command to run.
Open the Fleet tab on a master with no nodes to see:

```bash
git clone git@github.com:tconn93/nbd.git && cd nbd && ./nbd setup node --master http://10.0.171.31:9119
```

## What Each Mode Does

**Master** — Installs the Fleet dashboard plugin, configures auth, starts `hermes dashboard --host 0.0.0.0`, exposes API at `/api/plugins/nbd/`.

**Node** — Starts `hermes proxy --port 8080` (OpenAI-compatible API), registers with the master.

## Repo Structure

```
nbd/
├── nbd                      # CLI setup command (chmod +x, zero deps)
├── plugins/nbd/dashboard/   # Hermes dashboard plugin
│   ├── manifest.json
│   ├── plugin_api.py
│   └── dist/index.js
└── skill/SKILL.md           # Hermes agent skill
```

## API Endpoints

All at `/api/plugins/nbd/`:

| Method | Path | Description |
|---|---|---|
| GET | `/setup-command` | Get master URL + connect command |
| GET | `/nodes` | List nodes |
| POST | `/nodes/register` | Register a node |
| POST | `/nodes/heartbeat` | Heartbeat |
| GET | `/sessions` | List sessions |
| GET | `/sessions/{id}` | Session with messages |
| POST | `/chat` | Chat with a node (auto-stores session) |
