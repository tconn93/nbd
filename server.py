"""
nbd Fleet API — MCP + HTTP server on port 9005.

MCP:   Hermes connects via mcp_servers config → tools in my toolset
HTTP:  Dashboard browser UI calls these endpoints for the Fleet tab
Both share the same fleet.db database.
"""

import json
import logging
import os
import secrets
import socket
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("nbd-server")

HERMES_HOME = Path.home() / ".hermes"
DB_PATH = HERMES_HOME / "fleet.db"

# ── Database ──────────────────────────────────────────────────────────────

def _db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    _migrate(db)
    return db

def _migrate(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '',
            api_url TEXT NOT NULL, api_key TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'offline',
            last_heartbeat TEXT, last_seen TEXT, first_seen TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, node_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT 'Untitled',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            message_count INTEGER DEFAULT 0,
            FOREIGN KEY (node_id) REFERENCES nodes(id)
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL, role TEXT NOT NULL,
            content TEXT NOT NULL, created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        CREATE TABLE IF NOT EXISTS tokens (
            id TEXT PRIMARY KEY, description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
            used_at TEXT DEFAULT NULL, used_by TEXT DEFAULT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_node ON sessions(node_id);
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_tokens_expires ON tokens(expires_at);
    """)
    db.commit()

def _now():
    return datetime.now(timezone.utc).isoformat()

def _local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ── Create MCP Server (tools for agents) ──────────────────────────────────

mcp = FastMCP(
    "nbd",
    instructions="nbd Hermes Fleet Orchestration — tools to manage nodes, send prompts, and view sessions.",
    port=9005,
)


@mcp.tool()
def nbd_list_nodes() -> str:
    """List all registered Hermes agent nodes with their status."""
    db = _db()
    stale = datetime.fromtimestamp(__import__("time").time() - 180, tz=timezone.utc).isoformat()
    db.execute("UPDATE nodes SET status='offline' WHERE status='online' AND last_heartbeat < ?", (stale,))
    db.commit()
    rows = db.execute("SELECT * FROM nodes ORDER BY last_seen DESC").fetchall()
    nodes = [dict(r) for r in rows]
    db.close()
    if not nodes:
        return json.dumps({"success": True, "nodes": [], "message": "No nodes registered."})
    summary = [{"id": n["id"], "name": n["name"], "status": n["status"],
                 "api_url": n["api_url"], "last_heartbeat": n["last_heartbeat"]} for n in nodes]
    return json.dumps({"success": True, "nodes": summary, "count": len(summary)})


@mcp.tool()
def nbd_node_status(node_id: str) -> str:
    """Get detailed status for a specific node by its ID."""
    db = _db()
    row = db.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
    db.close()
    if not row:
        return json.dumps({"success": False, "error": "Node not found"})
    n = dict(row)
    return json.dumps({"success": True, "node": {
        "id": n["id"], "name": n["name"], "status": n["status"],
        "api_url": n["api_url"], "last_heartbeat": n["last_heartbeat"],
        "first_seen": n["first_seen"], "current_task": n.get("current_task_id"),
    }})


@mcp.tool()
def nbd_chat_with_node(node_id: str, prompt: str) -> str:
    """Send a natural language prompt to a Hermes node and get its response. The conversation is auto-stored in the database."""
    import httpx
    db = _db()
    node = db.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
    if not node:
        db.close()
        return json.dumps({"success": False, "error": "Node not found"})

    now = _now()
    session_id = f"ses-{uuid.uuid4().hex[:10]}"
    db.execute("INSERT INTO sessions (id, node_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
               (session_id, node_id, prompt[:60], now, now))
    db.execute("INSERT INTO messages (session_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
               (session_id, prompt, now))
    db.commit()

    headers = {"Content-Type": "application/json"}
    if node["api_key"]:
        headers["Authorization"] = f"Bearer {node['api_key']}"
    api_url = node["api_url"].rstrip("/")

    try:
        resp = httpx.post(f"{api_url}/v1/chat/completions",
                          json={"model": "default", "messages": [{"role": "user", "content": prompt}]},
                          headers=headers, timeout=120)
        resp.raise_for_status()
        reply = resp.json()["choices"][0]["message"]["content"]
    except httpx.ConnectError:
        reply = f"[Error] Cannot reach node at {api_url}"
    except Exception as e:
        reply = f"[Error] {e}"

    db.execute("INSERT INTO messages (session_id, role, content, created_at) VALUES (?, 'assistant', ?, ?)",
               (session_id, reply, now))
    db.execute("UPDATE sessions SET updated_at=?, message_count=message_count+2 WHERE id=?", (now, session_id))
    db.commit()
    db.close()

    return json.dumps({"success": True, "session_id": session_id, "reply": reply})


@mcp.tool()
def nbd_get_sessions(node_id: str = "", limit: int = 20) -> str:
    """List conversation sessions. Optionally filter by node_id."""
    db = _db()
    limit = min(limit, 100)
    if node_id:
        rows = db.execute("SELECT * FROM sessions WHERE node_id=? ORDER BY updated_at DESC LIMIT ?",
                          (node_id, limit)).fetchall()
    else:
        rows = db.execute("SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    db.close()
    sessions = [dict(r) for r in rows]
    return json.dumps({"success": True, "sessions": sessions, "count": len(sessions)})


@mcp.tool()
def nbd_get_session(session_id: str) -> str:
    """Get full conversation history for a session."""
    db = _db()
    session = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not session:
        db.close()
        return json.dumps({"success": False, "error": "Session not found"})
    messages = db.execute("SELECT * FROM messages WHERE session_id=? ORDER BY id ASC", (session_id,)).fetchall()
    db.close()
    return json.dumps({
        "success": True,
        "session": dict(session),
        "messages": [{"role": m["role"], "content": m["content"], "time": m["created_at"][:19]} for m in messages],
    })


@mcp.tool()
def nbd_generate_token(hours: int = 24, description: str = "") -> str:
    """Generate a time-limited registration token for a new node. Default 24 hours."""
    db = _db()
    token = f"nbt_{secrets.token_urlsafe(32)}"
    expires = datetime.now(timezone.utc) + timedelta(hours=max(1, min(hours, 720)))
    db.execute("INSERT INTO tokens (id, description, created_at, expires_at) VALUES (?, ?, ?, ?)",
               (token, description[:200], _now(), expires.isoformat()))
    db.commit()
    db.close()
    return json.dumps({
        "success": True, "token": token, "expires_at": expires.isoformat(),
        "command": f"nbd setup node --master http://{_local_ip()}:9005 --token {token}",
    })


# ── Create FastAPI app (HTTP routes for dashboard UI) ────────────────────

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

http_app = FastAPI(title="nbd Fleet API", version="1.0.0")
http_app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                        allow_methods=["*"], allow_headers=["*"])


class RegisterRequest(BaseModel):
    node_id: str = ""; name: str = ""; api_url: str
    api_key: str = ""; token: str = ""; metadata: dict = {}

class HeartbeatRequest(BaseModel):
    node_id: str; status: str = "online"

class ChatRequest(BaseModel):
    node_id: str; prompt: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = None

class TokenGenerateRequest(BaseModel):
    description: str = ""; hours: int = 24


@http_app.post("/api/plugins/nbd/nodes/register")
async def register_node(req: RegisterRequest):
    db = _db()
    now = _now()
    node_id = req.node_id or f"node-{uuid.uuid4().hex[:8]}"
    if req.token:
        token = db.execute("SELECT * FROM tokens WHERE id=? AND used_at IS NULL AND expires_at > ?",
                           (req.token, now)).fetchone()
        if not token:
            db.close(); raise HTTPException(401, "Invalid or expired token")
        db.execute("UPDATE tokens SET used_at=?, used_by=? WHERE id=?", (now, node_id, req.token))
    db.execute("""INSERT INTO nodes (id, name, api_url, api_key, status, last_heartbeat, last_seen, first_seen, metadata)
                  VALUES (?, ?, ?, ?, 'online', ?, ?, ?, ?)
                  ON CONFLICT(id) DO UPDATE SET name=excluded.name, api_url=excluded.api_url,
                      api_key=excluded.api_key, status='online', last_heartbeat=excluded.last_heartbeat,
                      last_seen=excluded.last_seen, metadata=excluded.metadata""",
               (node_id, req.name or node_id, req.api_url, req.api_key, now, now, now, json.dumps(req.metadata)))
    db.commit()
    db.close()
    return {"success": True, "node_id": node_id}

@http_app.post("/api/plugins/nbd/nodes/heartbeat")
async def node_heartbeat(req: HeartbeatRequest):
    db = _db()
    now = _now()
    cur = db.execute("UPDATE nodes SET status=?, last_heartbeat=?, last_seen=? WHERE id=?", (req.status, now, now, req.node_id))
    db.commit()
    db.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Node not found")
    return {"success": True}

@http_app.get("/api/plugins/nbd/nodes")
async def list_nodes():
    db = _db()
    stale = datetime.fromtimestamp(__import__("time").time() - 180, tz=timezone.utc).isoformat()
    db.execute("UPDATE nodes SET status='offline' WHERE status='online' AND last_heartbeat < ?", (stale,))
    db.commit()
    rows = db.execute("SELECT * FROM nodes ORDER BY last_seen DESC").fetchall()
    db.close()
    return {"nodes": [dict(r) for r in rows], "count": len(rows)}

@http_app.get("/api/plugins/nbd/nodes/{node_id}")
async def get_node(node_id: str):
    db = _db()
    row = db.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "Node not found")
    return {"node": dict(row)}

@http_app.post("/api/plugins/nbd/tokens/generate")
async def generate_token_http(req: TokenGenerateRequest):
    result = json.loads(nbd_generate_token(hours=req.hours, description=req.description))
    return result

@http_app.get("/api/plugins/nbd/tokens")
async def list_tokens():
    db = _db()
    rows = db.execute("SELECT * FROM tokens ORDER BY created_at DESC LIMIT 50").fetchall()
    db.close()
    return {"tokens": [dict(r) for r in rows], "count": len(rows)}

@http_app.post("/api/plugins/nbd/chat")
async def chat_http(req: ChatRequest):
    result = json.loads(nbd_chat_with_node(node_id=req.node_id, prompt=req.prompt))
    return result

@http_app.get("/api/plugins/nbd/setup-command")
async def setup_command():
    api_url = f"http://{_local_ip()}:9005"
    return {"master_url": api_url, "command": f"nbd setup node --master {api_url}"}

@http_app.get("/api/plugins/nbd/sessions")
async def list_sessions_http(node_id: str = "", limit: int = 50):
    result = json.loads(nbd_get_sessions(node_id=node_id, limit=limit))
    return result

@http_app.get("/api/plugins/nbd/sessions/{session_id}")
async def get_session_http(session_id: str):
    result = json.loads(nbd_get_session(session_id=session_id))
    return result

@http_app.get("/health")
async def health():
    return {"status": "healthy", "mode": "fleet-api"}


# ── Run ───────────────────────────────────────────────────────────────────

def run(port: int = 9005, host: str = "0.0.0.0"):
    """Start the server — both MCP and HTTP on the same port."""
    import uvicorn
    from starlette.routing import Mount
    from starlette.applications import Starlette

    sse_app = mcp.sse_app()

    print(f"\n  🌐 nbd Fleet")
    print(f"  ─────────────────────────────")
    print(f"  🔌 MCP:     http://{host}:{port}/mcp")
    print(f"  🌍 HTTP:    http://{host}:{port}/api/plugins/nbd/")
    print(f"  📋 Nodes:   http://{host}:{port}/api/plugins/nbd/nodes")
    print(f"  🔗 Setup:   http://{host}:{port}/api/plugins/nbd/setup-command")
    print(f"  💬 Chat:    http://{host}:{port}/api/plugins/nbd/chat")
    print(f"  🎫 Tokens:  http://{host}:{port}/api/plugins/nbd/tokens")
    print()

    combined = Starlette(routes=[
        Mount("/mcp", app=sse_app),
        Mount("/", app=http_app),
    ])

    uvicorn.run(combined, host=host, port=port, log_level="info")
