"""nbd fleet plugin — tool schemas (what the LLM sees)."""

NBD_LIST_NODES = {
    "name": "nbd_list_nodes",
    "description": (
        "List all Hermes agent nodes registered with this fleet master. "
        "Returns each node's ID, name, status (online/idle/busy/offline), "
        "API URL, and last heartbeat time. Use this to check fleet health "
        "before sending tasks to specific nodes."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
        "required": [],
    },
}

NBD_NODE_STATUS = {
    "name": "nbd_node_status",
    "description": (
        "Get detailed status and metadata for a specific registered node. "
        "Returns the node's full info including API URL, label, host info, "
        "last heartbeat timestamp, and current task if busy."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "node_id": {
                "type": "string",
                "description": "ID of the node to check (e.g., 'node-abc12345')",
            },
        },
        "required": ["node_id"],
    },
}

NBD_CHAT_WITH_NODE = {
    "name": "nbd_chat_with_node",
    "description": (
        "Send a natural language prompt to a registered Hermes agent node "
        "and get its response. The node runs `hermes proxy` so this calls "
        "its OpenAI-compatible API. The conversation is automatically stored "
        "in the Fleet database as a session. Use this to delegate tasks, ask "
        "questions, or orchestrate work across your agent fleet."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "node_id": {
                "type": "string",
                "description": "Node ID to send the prompt to (e.g., 'node-abc12345')",
            },
            "prompt": {
                "type": "string",
                "description": "The natural language prompt or task to send",
            },
        },
        "required": ["node_id", "prompt"],
    },
}

NBD_GET_SESSIONS = {
    "name": "nbd_get_sessions",
    "description": (
        "List all conversation sessions with fleet nodes. Optionally filter "
        "by node_id to see only sessions with a specific node. Returns session "
        "ID, title, node, message count, and timestamps."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "node_id": {
                "type": "string",
                "description": "Optional: filter sessions for a specific node ID",
            },
            "limit": {
                "type": "integer",
                "description": "Max sessions to return (default 20, max 100)",
                "default": 20,
            },
        },
        "required": [],
    },
}

NBD_GET_SESSION = {
    "name": "nbd_get_session",
    "description": (
        "Get the full conversation history for a specific session, including "
        "all user and assistant messages. Use this to review past "
        "conversations with fleet nodes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {
                "type": "string",
                "description": "Session ID (e.g., 'ses-abc1234567')",
            },
        },
        "required": ["session_id"],
    },
}
