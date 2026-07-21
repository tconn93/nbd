"""nbd fleet plugin — tool handlers (the code that runs)."""

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("nbd-plugin")

FLEET_API = os.environ.get(
    "NBD_API_URL",
    "http://127.0.0.1:9119/api/plugins/nbd",
)


def _fetch(path: str, method: str = "GET", body: Optional[dict] = None) -> dict:
    """Call the nbd fleet API."""
    import urllib.request
    import urllib.error

    url = f"{FLEET_API.rstrip('/')}/{path.lstrip('/')}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {"error": f"HTTP {e.code}: {body[:200]}"}
    except urllib.error.URLError as e:
        return {"error": f"Cannot reach nbd API: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def nbd_list_nodes(args: dict, **kwargs) -> str:
    """List all registered fleet nodes."""
    result = _fetch("/nodes")
    if "error" in result:
        return json.dumps({"success": False, "error": result["error"]})

    nodes = result.get("nodes", [])
    if not nodes:
        return json.dumps({"success": True, "nodes": [], "message": "No nodes registered."})

    summary = []
    for n in nodes:
        summary.append({
            "id": n.get("id"),
            "name": n.get("name", n.get("id")),
            "status": n.get("status", "offline"),
            "api_url": n.get("api_url", ""),
            "last_heartbeat": n.get("last_heartbeat", ""),
            "current_task": n.get("current_task_id"),
        })
    return json.dumps({"success": True, "nodes": summary, "count": len(summary)})


def nbd_node_status(args: dict, **kwargs) -> str:
    """Get detailed status for a specific node."""
    node_id = args.get("node_id", "")
    if not node_id:
        return json.dumps({"success": False, "error": "node_id required"})

    result = _fetch(f"/nodes/{node_id}")
    if "error" in result:
        return json.dumps({"success": False, "error": result["error"]})

    node = result.get("node", {})
    return json.dumps({"success": True, "node": {
        "id": node.get("id"),
        "name": node.get("name", node.get("id")),
        "status": node.get("status"),
        "api_url": node.get("api_url"),
        "last_heartbeat": node.get("last_heartbeat"),
        "first_seen": node.get("first_seen"),
        "current_task": node.get("current_task_id"),
    }})


def nbd_chat_with_node(args: dict, **kwargs) -> str:
    """Send a prompt to a node and get a response."""
    node_id = args.get("node_id", "")
    prompt = args.get("prompt", "")

    if not node_id:
        return json.dumps({"success": False, "error": "node_id required"})
    if not prompt:
        return json.dumps({"success": False, "error": "prompt required"})

    result = _fetch("/chat", method="POST", body={
        "node_id": node_id,
        "prompt": prompt,
    })

    if "error" in result:
        return json.dumps({"success": False, "error": result["error"]})

    return json.dumps({
        "success": True,
        "session_id": result.get("session_id"),
        "reply": result.get("reply", "(no response)"),
    })


def nbd_get_sessions(args: dict, **kwargs) -> str:
    """List conversation sessions, optionally filtered by node."""
    node_id = args.get("node_id")
    limit = min(int(args.get("limit", 20)), 100)

    path = f"/sessions?limit={limit}"
    if node_id:
        path += f"&node_id={node_id}"

    result = _fetch(path)
    if "error" in result:
        return json.dumps({"success": False, "error": result["error"]})

    sessions = result.get("sessions", [])
    summary = []
    for s in sessions:
        summary.append({
            "id": s.get("id"),
            "node_id": s.get("node_id"),
            "title": s.get("title", "Untitled"),
            "message_count": s.get("message_count", 0),
            "updated_at": s.get("updated_at", ""),
        })

    return json.dumps({"success": True, "sessions": summary, "count": len(summary)})


def nbd_get_session(args: dict, **kwargs) -> str:
    """Get full conversation history for a session."""
    session_id = args.get("session_id", "")
    if not session_id:
        return json.dumps({"success": False, "error": "session_id required"})

    result = _fetch(f"/sessions/{session_id}")
    if "error" in result:
        return json.dumps({"success": False, "error": result["error"]})

    session = result.get("session", {})
    messages = result.get("messages", [])

    return json.dumps({
        "success": True,
        "session": {
            "id": session.get("id"),
            "node_id": session.get("node_id"),
            "title": session.get("title", "Untitled"),
            "created_at": session.get("created_at"),
        },
        "messages": [
            {"role": m.get("role"), "content": m.get("content"), "time": m.get("created_at", "")[:19]}
            for m in messages
        ],
        "message_count": len(messages),
    })
