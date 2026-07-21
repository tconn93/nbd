"""
nbd Hermes plugin — registers fleet orchestration tools and CLI commands.

This gives the agent direct tools to manage, chat with, and inspect
the fleet of connected Hermes nodes — no curl commands needed.
"""

import logging

from . import schemas, tools

logger = logging.getLogger("nbd-plugin")


def register(ctx):
    """Register all nbd fleet tools and hooks."""

    ctx.register_tool(
        name="nbd_list_nodes",
        toolset="nbd",
        schema=schemas.NBD_LIST_NODES,
        handler=tools.nbd_list_nodes,
    )
    ctx.register_tool(
        name="nbd_node_status",
        toolset="nbd",
        schema=schemas.NBD_NODE_STATUS,
        handler=tools.nbd_node_status,
    )
    ctx.register_tool(
        name="nbd_chat_with_node",
        toolset="nbd",
        schema=schemas.NBD_CHAT_WITH_NODE,
        handler=tools.nbd_chat_with_node,
    )
    ctx.register_tool(
        name="nbd_get_sessions",
        toolset="nbd",
        schema=schemas.NBD_GET_SESSIONS,
        handler=tools.nbd_get_sessions,
    )
    ctx.register_tool(
        name="nbd_get_session",
        toolset="nbd",
        schema=schemas.NBD_GET_SESSION,
        handler=tools.nbd_get_session,
    )

    logger.info("nbd plugin registered: 5 fleet tools available")
