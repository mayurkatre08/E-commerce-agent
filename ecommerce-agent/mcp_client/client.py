"""
mcp_client/client.py
Connects to the FastMCP server via stdio transport and exposes all 5 tools
as LangChain-compatible BaseTool instances for use by agents.

Usage (async context):
    async with get_mcp_tools() as tools:
        # tools is a list[BaseTool]
        result = await tools[0].ainvoke({"query": "return policy"})
"""

import os
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_core.tools import BaseTool

# Absolute path to the server script
SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "mcp_server", "server.py")
PYTHON_EXE    = sys.executable          # same venv python that runs the client


@asynccontextmanager
async def get_mcp_tools() -> AsyncGenerator[list[BaseTool], None]:
    """
    Async context manager that:
      1. Spawns the MCP server as a subprocess (stdio transport)
      2. Loads all tools via langchain-mcp-adapters
      3. Yields the list of LangChain BaseTool instances
      4. Cleans up the subprocess on exit
    """
    server_params = StdioServerParameters(
        command=PYTHON_EXE,
        args=[SERVER_SCRIPT],
        env=None,           # inherits current env (picks up .env vars)
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            yield tools


def get_tool_names() -> list[str]:
    """Return the expected tool names — useful for validation without spawning a process."""
    return [
        "policy_search",
        "get_order",
        "cancel_order",
        "change_size",
        "escalate_to_human",
    ]
