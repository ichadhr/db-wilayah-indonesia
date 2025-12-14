"""
MCP Client - LiteLLM experimental_mcp_client integration.

Uses litellm.experimental_mcp_client for MCP tool loading and execution.
Supports multiple transport types: stdio, http, sse.

This module provides the main MCPClient class that coordinates:
- Configuration loading (via mcp/config.py)
- Tool execution (via mcp/executor.py)
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, cast

from .config import (
    get_available_servers,
    get_server_auth_headers,
    get_server_transport,
    load_mcp_config,
)
from .executor import execute_tool

# Configure logging
logger = logging.getLogger(__name__)

# MCP imports - optional dependency
MCP_AVAILABLE = False
try:
    from litellm import experimental_mcp_client
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamablehttp_client

    MCP_AVAILABLE = True
except ImportError:
    experimental_mcp_client = None  # type: ignore[assignment]
    ClientSession = None  # type: ignore[assignment, misc]
    StdioServerParameters = None  # type: ignore[assignment, misc]
    stdio_client = None  # type: ignore[assignment]
    streamablehttp_client = None  # type: ignore[assignment]

# Re-export for convenience
__all__ = ["MCPClient", "get_available_servers"]


class MCPClient:
    """LiteLLM-based MCP client for tool-augmented LLM calls."""

    def __init__(self, servers: bool | list[str] = False):
        """
        Initialize MCP client with server selection.

        Args:
            servers:
                False = no MCP
                True = load ALL servers from mcp.json
                ["databeak"] = load only specified servers
                [] = no MCP
        """
        self.servers_config: dict[str, dict[str, Any]] = {}
        self.tool_to_server: dict[str, str] = {}
        self.sessions: dict[str, Any] = {}  # Active MCP sessions
        self.tools: list[dict[str, Any]] = []

        if servers is False or servers == []:
            return

        if not MCP_AVAILABLE:
            raise ImportError(
                "MCP/LiteLLM libraries not available. Install with: pip install mcp litellm"
            )

        # Load configuration using config module
        self.servers_config = load_mcp_config(servers=servers)

    async def __aenter__(self) -> "MCPClient":
        """Async context manager entry - load tools from all servers."""
        await self.load_tools()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit - cleanup sessions."""
        await self.close()

    async def load_tools(self) -> list[dict[str, Any]]:
        """
        Load tools from all configured MCP servers using litellm experimental_mcp_client.

        Returns:
            List of OpenAI-compatible tool definitions
        """
        if not self.servers_config:
            return []

        if not MCP_AVAILABLE:
            logger.warning("MCP not available, returning empty tools")
            return []

        all_tools: list[dict[str, Any]] = []

        for server_name, server_config in self.servers_config.items():
            try:
                tools = await self._load_server_tools(server_name, server_config)
                all_tools.extend(tools)
                logger.info(f"Loaded {len(tools)} tools from {server_name}")
                print(f"[MCP] Loaded {len(tools)} tools from {server_name}")
            except Exception as e:
                logger.error(f"Failed to load tools from {server_name}: {e}")
                print(f"[MCP] Failed to load tools from {server_name}: {e}")

        self.tools = all_tools
        return all_tools

    async def _load_server_tools(
        self, server_name: str, server_config: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Load tools from a single MCP server based on transport type."""
        transport = get_server_transport(server_config)

        if transport == "stdio":
            return await self._load_stdio_tools(server_name, server_config)
        elif transport in ("http", "sse"):
            return await self._load_http_tools(server_name, server_config, transport)
        else:
            logger.warning(f"Unsupported transport type: {transport}")
            return []

    async def _load_stdio_tools(
        self, server_name: str, server_config: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Load tools from stdio MCP server using litellm experimental_mcp_client."""
        if not MCP_AVAILABLE or stdio_client is None or StdioServerParameters is None:
            raise ImportError("MCP libraries not available")

        command = server_config.get("command", "")
        args = server_config.get("args", [])
        env = server_config.get("env", {})

        if not command:
            raise ValueError(f"No command specified for stdio server: {server_name}")

        print(
            f"[MCP] Spawning stdio server: {server_name} ({command} {' '.join(args)})"
        )

        # Create server parameters for stdio connection
        server_params = StdioServerParameters(
            command=command,
            args=args,
            env={**os.environ, **env} if env else None,
        )

        # Store context managers for later cleanup
        self.sessions[server_name] = {
            "type": "stdio",
            "params": server_params,
            "tools": [],
        }

        # Load tools using litellm experimental_mcp_client
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:  # type: ignore[misc]
                await session.initialize()

                # Use litellm's experimental_mcp_client to load tools in OpenAI format
                tools_result = await experimental_mcp_client.load_mcp_tools(  # type: ignore[union-attr]
                    session=session, format="openai"
                )

                tools = self._convert_tools_to_dict(tools_result, server_name)
                self.sessions[server_name]["tools"] = tools
                return tools

    async def _load_http_tools(
        self, server_name: str, server_config: dict[str, Any], transport: str
    ) -> list[dict[str, Any]]:
        """Load tools from HTTP/SSE MCP server using streamablehttp_client."""
        if not MCP_AVAILABLE or streamablehttp_client is None:
            raise ImportError("MCP libraries not available")

        url = server_config.get("url", "")
        if not url:
            raise ValueError(f"No URL specified for {transport} server: {server_name}")

        headers = get_server_auth_headers(server_config)

        print(f"[MCP] Connecting to {transport} server: {server_name} ({url})")

        # Store session info
        self.sessions[server_name] = {
            "type": transport,
            "url": url,
            "headers": headers,
            "tools": [],
        }

        # Load tools using streamablehttp_client
        async with streamablehttp_client(url, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:  # type: ignore[misc]
                await session.initialize()

                # Use litellm's experimental_mcp_client to load tools in OpenAI format
                tools_result = await experimental_mcp_client.load_mcp_tools(  # type: ignore[union-attr]
                    session=session, format="openai"
                )

                tools = self._convert_tools_to_dict(tools_result, server_name)
                self.sessions[server_name]["tools"] = tools
                return tools

    def _convert_tools_to_dict(
        self, tools_result: Any, server_name: str
    ) -> list[dict[str, Any]]:
        """Convert tools result to list of dicts and map to server."""
        tools: list[dict[str, Any]] = []
        for tool in tools_result:
            if isinstance(tool, dict):
                tool_dict = tool
            else:
                # Handle Tool or ChatCompletionToolParam objects
                tool_dict = (
                    dict(tool)
                    if hasattr(tool, "keys")
                    else {"type": "function", "function": {"name": str(tool)}}
                )

            tools.append(cast(dict[str, Any], tool_dict))

            # Extract tool name for mapping
            if isinstance(tool_dict, dict):
                tool_name = tool_dict.get("function", {}).get("name", "")
                if tool_name:
                    self.tool_to_server[tool_name] = server_name

        return tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """
        Execute a tool call using litellm experimental_mcp_client.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Tool execution result as string
        """
        server_name = self.tool_to_server.get(tool_name)
        if not server_name:
            return f"Error: Unknown tool {tool_name}"

        server_config = self.servers_config.get(server_name)
        if not server_config:
            return f"Error: Server config not found for {server_name}"

        transport = get_server_transport(server_config)

        # Use executor module for actual execution
        return await execute_tool(server_config, transport, tool_name, arguments)

    async def close(self) -> None:
        """Close all MCP sessions and cleanup resources."""
        self.sessions.clear()
        self.tool_to_server.clear()
        self.tools.clear()
        print("[MCP] All sessions closed")

    def load_tools_sync(self) -> list[dict[str, Any]]:
        """Synchronous wrapper for load_tools."""
        return asyncio.run(self.load_tools())

    def call_tool_sync(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Synchronous wrapper for call_tool."""
        return asyncio.run(self.call_tool(tool_name, arguments))
