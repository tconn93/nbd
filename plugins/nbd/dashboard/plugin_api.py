"""
nbd Fleet — dashboard plugin backend.

Stores connected Hermes agent nodes, registration tokens, and sessions.
SQLite by default; Postgres when NBD_DATABASE_URL env var is set.

API mounted at /api/plugins/nbd/
"""

import json
import logging
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

logger = logging.getLogger("nbd")

router = APIRouter()

HERMES_HOME = Path.home() / ".hermes"
DB_PATH = HERMES_HOME / "fleet.db"
_DATABASE_URL = os.environ.get("NBD_DATABASE_URL", "")

# ── Database ──────────────────────────────────────────────────────────────

def _db():
    if _DATABASE_URL:
        return _pg_db()
    return _sqlite_db()

def _sqlite_db():
    db = sqlite3.connect(str(DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    _run_sqlite_migrations(db)
    db.commit()
    return db

def _run_sqlite_migrations(db):
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
        CREATE TABLE IF NOT EXISTS tokens (
            id TEXT PRIMARY KEY,
            description TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            used_at TEXT DEFAULT NULL,
            used_by TEXT DEFAULT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_sessions_node ON sessions(node_id);
        CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_tokens_expires ON tokens(expires_at);
    """)
    db.commit()

def _pg_db():
    try:
        import asyncpg
    except ImportError:
        raise RuntimeError("NBD_DATABASE_URL set but asyncpg not installed. Run: pip install asyncpg")
    async def _connect():
        return await asyncpg.connect(_DATABASE_URL)
    if not hasattr(_pg_db, "_conn"):
        import asyncio
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        _pg_db._conn = loop.run_until_complete(_connect())
        loop.run_until_complete(_run_pg_migrations(_pg_db._conn))
    return _pg_db._conn

async def _run_pg_migrations(conn):
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '',
            api_url TEXT NOT NULL, api_key TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'offline',
            last_heartbeat TEXT, last_seen TEXT, first_seen TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY, node_id TEXT NOT NULL REFERENCES nodes(id),
            title TEXT NOT NULL DEFAULT 'Untitled',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            message_count INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
            role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
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

def _now():
    return datetime.now(timezone.utc).isoformat()


# ── Models ────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    node_id: str = ""
    name: str = ""
    api_url: str
    api_key: str = ""
    token: str = ""
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

class TokenGenerateRequest(BaseModel):
    description: str = ""
    hours: int = 24


# ── Token Endpoints ───────────────────────────────────────────────────────

@router.post("/tokens/generate")
async def generate_token(req: TokenGenerateRequest):
    """Generate a time-limited registration token."""
    db = _db()
    now = _now()
    expires = datetime.now(timezone.utc) + timedelta(hours=max(1, min(req.hours, 720)))
    token_id = f"nbt_{secrets.token_urlsafe(32)}"

    db.execute(
        "INSERT INTO tokens (id, description, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token_id, req.description[:200], now, expires.isoformat()),
    )
    db.commit()

    logger.info(f"Token generated: {token_id[:16]}... expires {expires.isoformat()}")

    # Also return the full command the node should run
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "127.0.0.1"
    master_url = f"http://{ip}:9119"

    return {
        "success": True,
        "token": token_id,
        "expires_at": expires.isoformat(),
        "description": req.description,
        "command": f"nbd setup node --master {master_url} --token {token_id}",
    }

@router.get("/tokens")
async def list_tokens():
    """List all tokens with their status."""
    import time
    db = _db()
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = db.execute(
        "SELECT * FROM tokens ORDER BY created_at DESC LIMIT 50"
    ).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        d["expired"] = d["expires_at"] < now_iso
        d["used"] = d["used_at"] is not None
        result.append(d)
    return {"tokens": result, "count": len(result)}


# ── Node Endpoints ────────────────────────────────────────────────────────

@router.post("/nodes/register")
async def register_node(req: RegisterRequest):
    """Register (or update) a node. Validates registration token if provided."""
    db = _db()
    now = _now()
    node_id = req.node_id or f"node-{uuid.uuid4().hex[:8]}"

    # Validate token if provided
    if req.token:
        token_row = db.execute(
            "SELECT * FROM tokens WHERE id=? AND used_at IS NULL AND expires_at > ?",
            (req.token, now),
        ).fetchone()
        if not token_row:
            # Check if expired
            expired = db.execute(
                "SELECT * FROM tokens WHERE id=?", (req.token,)
            ).fetchone()
            if expired:
                if expired["expires_at"] < now:
                    raise HTTPException(401, "Token expired")
                if expired["used_at"]:
                    raise HTTPException(401, "Token already used")
            raise HTTPException(401, "Invalid registration token")
        # Mark token as used
        db.execute(
            "UPDATE tokens SET used_at=?, used_by=? WHERE id=?",
            (now, node_id, req.token),
        )

    db.execute(
        """INSERT INTO nodes (id, name, api_url, api_key, status, last_heartbeat, last_seen, first_seen, metadata)
           VALUES (?, ?, ?, ?, 'online', ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
               name=excluded.name, api_url=excluded.api_url, api_key=excluded.api_key,
               status='online', last_heartbeat=excluded.last_heartbeat,
               last_seen=excluded.last_seen, metadata=excluded.metadata""",
        (node_id, req.name or node_id, req.api_url, req.api_key,
         now, now, now, json.dumps(req.metadata)),
    )
    db.commit()
    logger.info(f"Node registered: {node_id} @ {req.api_url}")
    return {"success": True, "node_id": node_id}


@router.post("/nodes/heartbeat")
async def node_heartbeat(req: HeartbeatRequest):
    db = _db()
    now = _now()
    cur = db.execute(
        "UPDATE nodes SET status=?, last_heartbeat=?, last_seen=? WHERE id=?",
        (req.status, now, now, req.node_id),
    )
    db.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "Node not found — register first")
    return {"success": True}


@router.get("/nodes")
async def list_nodes():
    db = _db()
    import time
    stale_cutoff = datetime.fromtimestamp(time.time() - 180, tz=timezone.utc).isoformat()
    db.execute("UPDATE nodes SET status='offline' WHERE status='online' AND last_heartbeat < ?", (stale_cutoff,))
    db.commit()
    rows = db.execute("SELECT * FROM nodes ORDER BY last_seen DESC").fetchall()
    return {"nodes": [dict(r) for r in rows], "count": len(rows)}


@router.get("/nodes/{node_id}")
async def get_node(node_id: str):
    db = _db()
    row = db.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Node not found")
    return {"node": dict(row)}


# ── Setup Command ─────────────────────────────────────────────────────────

@router.get("/setup-command")
async def get_setup_command():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "127.0.0.1"
    master_url = f"http://{ip}:9119"

    # Generate a fresh token for this command
    token_req = TokenGenerateRequest(description="auto-generated setup token")
    token_resp = await generate_token(token_req)

    return {
        "master_url": master_url,
        "command": token_resp["command"],
        "token": token_resp["token"],
        "expires_at": token_resp["expires_at"],
    }


# ── Session Endpoints ─────────────────────────────────────────────────────

@router.post("/sessions")
async def create_session(req: SessionCreateRequest):
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
    db = _db()
    session = db.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if not session:
        raise HTTPException(404, "Session not found")
    messages = db.execute(
        "SELECT * FROM messages WHERE session_id=? ORDER BY id ASC", (session_id,)
    ).fetchall()
    return {"session": dict(session), "messages": [dict(m) for m in messages], "message_count": len(messages)}


@router.post("/sessions/{session_id}/messages")
async def add_message(session_id: str, req: MessageRequest):
    db = _db()
    now = _now()
    db.execute(
        "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (session_id, req.role, req.content, now),
    )
    db.execute("UPDATE sessions SET updated_at=?, message_count=message_count+1 WHERE id=?", (now, session_id))
    db.commit()
    return {"success": True}


# ── Proxy Chat ────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    node_id: str
    prompt: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = None


@router.post("/chat")
async def chat_with_node(req: ChatRequest):
    import httpx
    db = _db()
    node = db.execute("SELECT * FROM nodes WHERE id=?", (req.node_id,)).fetchone()
    if not node:
        raise HTTPException(404, "Node not found")
    if node["status"] == "offline":
        raise HTTPException(503, "Node is offline")

    now = _now()
    session_id = req.session_id
    if not session_id:
        session_id = f"ses-{uuid.uuid4().hex[:10]}"
        db.execute(
            "INSERT INTO sessions (id, node_id, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, req.node_id, req.prompt[:60], now, now),
        )

    db.execute("INSERT INTO messages (session_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
               (session_id, req.prompt, now))

    headers = {"Content-Type": "application/json"}
    if node["api_key"]:
        headers["Authorization"] = f"Bearer {node['api_key']}"
    api_url = node["api_url"].rstrip("/")

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{api_url}/v1/chat/completions",
                json={"model": "default", "messages": [{"role": "user", "content": req.prompt}]},
                headers=headers,
            )
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

    return {"success": True, "session_id": session_id, "reply": reply}
