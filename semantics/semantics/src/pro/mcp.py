"""Model Context Protocol (MCP) client.

Lets a Semantics run call out to external MCP servers (filesystem,
databases, SaaS APIs, whatever the user has configured) as additional
tools alongside the built-in read_file/write_file/execute_bash set.

Servers are configured in `.semantics/mcp.json`:

    {
      "servers": [
        {"name": "filesystem", "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]}
      ]
    }
"""

from __future__ import annotations

import json
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    _HAS_MCP = True
except ImportError:  # pragma: no cover - mcp SDK is an optional/pro dependency
    _HAS_MCP = False


class MCPError(RuntimeError):
    pass


@dataclass
class MCPServerConfig:
    name: str
    command: str
    args: list[str]
    env: Optional[dict[str, str]] = None


def load_server_configs(config_path: Path) -> list[MCPServerConfig]:
    if not config_path.exists():
        return []
    data = json.loads(config_path.read_text())
    return [MCPServerConfig(**server) for server in data.get("servers", [])]


class MCPClient:
    """Owns one stdio connection per configured MCP server for the lifetime of a run.

    Must be used as an async context manager so every subprocess/session is
    torn down cleanly, even on error:

        async with MCPClient() as mcp:
            await mcp.connect_server(cfg)
            result = await mcp.call_tool("filesystem.read_file", {"path": "x"})
    """

    def __init__(self) -> None:
        if not _HAS_MCP:
            raise MCPError("The `mcp` package is not installed. `pip install -r requirements.pro.txt`.")
        self._stack = AsyncExitStack()
        self.sessions: dict[str, ClientSession] = {}
        self.tools: dict[str, dict[str, Any]] = {}  # "server.tool" -> {"session": ..., "schema": ...}

    async def __aenter__(self) -> "MCPClient":
        await self._stack.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._stack.__aexit__(exc_type, exc, tb)

    async def connect_server(self, config: MCPServerConfig) -> list[Any]:
        params = StdioServerParameters(command=config.command, args=config.args, env=config.env)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        self.sessions[config.name] = session
        response = await session.list_tools()
        for tool in response.tools:
            qualified_name = f"{config.name}.{tool.name}"
            self.tools[qualified_name] = {"session": session, "schema": tool}
        return response.tools

    def get_schemas(self) -> list[dict]:
        """Tool schemas in the same function-calling format ToolRegistry uses."""
        schemas = []
        for qualified_name, entry in self.tools.items():
            tool = entry["schema"]
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": qualified_name,
                        "description": tool.description or "",
                        "parameters": tool.inputSchema or {"type": "object", "properties": {}},
                    },
                }
            )
        return schemas

    async def call_tool(self, qualified_name: str, arguments: dict[str, Any]) -> str:
        if qualified_name not in self.tools:
            raise MCPError(f"MCP tool '{qualified_name}' not found among connected servers.")
        session = self.tools[qualified_name]["session"]
        _, tool_name = qualified_name.split(".", 1)
        result = await session.call_tool(tool_name, arguments)
        parts = [block.text for block in result.content if getattr(block, "type", None) == "text"]
        return "\n".join(parts) if parts else str(result.content)
