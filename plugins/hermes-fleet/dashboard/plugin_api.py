"""
Hermes Fleet — dashboard plugin backend.

Stores connected Hermes agent nodes and their conversation sessions.
Nodes register by running `hermes proxy` and providing their URL.

API mounted at /api/plugins/hermes-fleet/
"""

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("hermes-fleet")

router = APIRouter()

HERMES_HOME = Path.home() / ".hermes"
DB_PATH = HERMES_HOME / "fleet.db"


def _db():
    """Get or create the SQLite database."""
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            api_url TEXT NOT NULL,
            api_key TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'offline',
            last_heartbeat TEXT,
            last_seen TEXT,
            first_seen TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            node_id TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT 'Untitled',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            message_count INTEGER DEFAULT 0,
            FOREIGN KEY (node_id) REFERENCES nodes(id)
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_node ON sessions(node_id);
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
    """)
    db.commit()
    return db


def _now():
    return datetime.now(timezone.utc).isoformat()


# ── Models ────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    node_id: str = ""
    name: str = ""
    api_url: str
    api_key: str = ""
    metadata: dict = {}

class HeartbeatRequest(BaseModel):
    node_id: str
    status: str = "online"

class SessionCreateRequest(BaseModel):
    node_id: str
    title: str = "Untitled"

class MessageRequest(BaseModel):
    session_id: str
    role: str
    content: str


# ── Node Endpoints ───────────────────────────────────────────────────────

@router.post("/nodes/register")
async def register_node(req: RegisterRequest):
    """Register (or update) a Hermes agent node."""
    db = _db()
    now = _now()
    node_id = req.node_id or f"node-{uuid.uuid4().hex[:8]}"

    db.execute(
        """
        INSERT INTO nodes (id, name, api_url, api_key, status, last_heartbeat, last_seen, first_seen, metadata)
        VALUES (?, ?, ?, ?, 'online', ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, api_url=excluded.api_url, api_key=excluded.api_key,
            status='online', last_heartbeat=excluded.last_heartbeat, last_seen=excluded.last_seen,
            metadata=excluded.metadata
        """,
        (node_id, req.name or node_id, req.api_url, req.api_key, now, now, now, json.dumps(req.metadata)),
    )
    db.commit()
    logger.info(f"Node registered: {node_id} @ {req.api_url}")

    return {"success": True, "node_id": node_id}


@router.post("/nodes/heartbeat")
async def node_heartbeat(req: HeartbeatRequest):
    """Receive a heartbeat from a registered node."""
    db = _db()
    now = _now()
    cur = db.execute("UPDATE nodes SET status=?, last_heartbeat=?, last_seen=? WHERE id=?", (req.status, now, now, req.node_id))
    db.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "Node not found — register first")
    return {"success": True}


@router.get("/nodes")
async def list_nodes():
    """List all registered nodes."""
    db = _db()
    # Mark stale nodes offline (no heartbeat > 3 min)
    db.execute("UPDATE nodes SET status='offline' WHERE status='online' AND last_heartbeat < ?", (_now(),))
    # Actually check 3 min ago
    import time
    stale_cutoff = datetime.fromtimestamp(time.time() - 180, tz=timezone.utc).isoformat()
    db.execute("UPDATE nodes SET status='offline' WHERE status='online' AND last_heartbeat < ?", (stale_cutoff,))
    db.commit()

    rows = db.execute("SELECT * FROM nodes ORDER BY last_seen DESC").fetchall()
    return {"nodes": [dict(r) for r in rows], "count": len(rows)}


@router.get("/nodes/{node_id}")
async def get_node(node_id: str):
    """Get a specific node's details."""
    db = _db()
    row = db.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Node not found")
    return {"node": dict(row)}


# ── Session Endpoints ────────────────────────────────────────────────────

@router.post("/sessions")
async def create_session(req: SessionCreateRequest):
    """Start a new conversation session with a node."""
    db = _db()
    now = _now()
    session_id = f"ses-{uuid.uuid4().hex[:10]}"
    db.execute(
        "INSERT INTO sessions (id, node_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, req.node_id, req.title, now, now),
    )
    db.commit()
    return {"success": True, "session_id": session_id}


@router.get("/sessions")
async def list_sessions(node_id: Optional[str] = None, limit: int = 50):
    """List sessions, optionally filtered by node."""
    db = _db()
    if node_id:
        rows = db.execute(
            "SELECT * FROM sessions WHERE node_id=? ORDER BY updated_at DESC LIMIT ?",
            (node_id, limit),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,)).fetchall()
    return {"sessions": [dict(r) for r in rows], "count": len(rows)}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a session with all its messages."""
    db = _db()
    session = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not session:
        raise HTTPException(404, "Session not found")
    messages = db.execute(
        "SELECT * FROM messages WHERE session_id=? ORDER BY id ASC",
        (session_id,),
    ).fetchall()
    return {
        "session": dict(session),
        "messages": [dict(m) for m in messages],
        "message_count": len(messages),
    }


@router.post("/sessions/{session_id}/messages")
async def add_message(session_id: str, req: MessageRequest):
    """Add a message to a session."""
    db = _db()
    now = _now()
    db.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (session_id, req.role, req.content, now),
    )
    db.execute(
        "UPDATE sessions SET updated_at=?, message_count=message_count+1 WHERE id=?",
        (now, session_id),
    )
    db.commit()
    return {"success": True}


# ── Proxy Chat ────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    node_id: str
    prompt: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = None


@router.post("/chat")
async def chat_with_node(req: ChatRequest):
    """
    Send a prompt to a node via its OpenAI-compatible API.
    Creates/updates a session and stores the conversation.
    """
    import httpx

    db = _db()
    node = db.execute("SELECT * FROM nodes WHERE id=?", (req.node_id,)).fetchone()
    if not node:
        raise HTTPException(404, "Node not found")
    if node["status"] == "offline":
        raise HTTPException(503, "Node is offline")

    now = _now()

    # Create or use session
    session_id = req.session_id
    if not session_id:
        session_id = f"ses-{uuid.uuid4().hex[:10]}"
        db.execute(
            "INSERT INTO sessions (id, node_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, req.node_id, req.prompt[:60], now, now),
        )

    # Store user message
    db.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
        (session_id, req.prompt, now),
    )

    # Call the node's OpenAI-compatible API
    headers = {"Content-Type": "application/json"}
    if node["api_key"]:
        headers["Authorization"] = f"Bearer {node['api_key']}"

    api_url = node["api_url"].rstrip("/")
    chat_url = f"{api_url}/v1/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                chat_url,
                json={
                    "model": "default",
                    "messages": [{"role": "user", "content": req.prompt}],
                },
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            reply = data["choices"][0]["message"]["content"]
    except httpx.ConnectError:
        reply = f"[Error] Cannot reach node at {api_url}"
    except Exception as e:
        reply = f"[Error] {e}"

    # Store assistant reply
    db.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, 'assistant', ?, ?)",
        (session_id, reply, now),
    )
    db.execute(
        "UPDATE sessions SET updated_at=?, message_count=message_count+2 WHERE id=?",
        (now, session_id),
    )
    db.commit()

    return {
        "success": True,
        "session_id": session_id,
        "reply": reply,
    }
