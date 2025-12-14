"""
MCP Tool Executor.

Handles execution of MCP tools across different transport types (stdio, http, sse).
Provides both async and sync interfaces for tool execution.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

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

# Type aliases
MCPServerConfig = dict[str, Any]
ToolServerMapping = dict[str, str]


def check_mcp_available() -> bool:
    """Check if MCP libraries are available."""
    return MCP_AVAILABLE


def create_openai_tool_call(
    tool_name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """
    Create an OpenAI-style tool call object.

    Args:
        tool_name: Name of the tool to call
        arguments: Tool arguments as dictionary

    Returns:
        OpenAI-compatible tool call dict
    """
    return {
        "id": f"call_{tool_name}",
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": json.dumps(arguments),
        },
    }


def extract_result_text(call_result: Any) -> str:
    """
    Extract text content from MCP tool call result.

    Args:
        call_result: Raw result from MCP tool execution

    Returns:
        Extracted text content as string
    """
    if hasattr(call_result, "content") and call_result.content:
        content_parts = []
        for c in call_result.content:
            if hasattr(c, "text"):
                content_parts.append(str(getattr(c, "text", "")))
            else:
                content_parts.append(str(c))
        return "\n".join(content_parts)

    return str(call_result)


async def execute_stdio_tool(
    server_config: MCPServerConfig,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    """
    Execute tool on stdio MCP server.

    Args:
        server_config: Server configuration dict
        tool_name: Name of the tool to execute
        arguments: Tool arguments

    Returns:
        Tool execution result as string
    """
    if not MCP_AVAILABLE or stdio_client is None or StdioServerParameters is None:
        return "Error: MCP libraries not available"

    command = server_config.get("command", "")
    args = server_config.get("args", [])
    env = server_config.get("env", {})

    if not command:
        return f"Error: No command specified for stdio server"

    server_params = StdioServerParameters(
        command=command,
        args=args,
        env={**os.environ, **env} if env else None,
    )

    openai_tool = create_openai_tool_call(tool_name, arguments)

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:  # type: ignore[misc]
            await session.initialize()

            call_result = await experimental_mcp_client.call_openai_tool(  # type: ignore[union-attr]
                session=session,
                openai_tool=openai_tool,  # type: ignore[arg-type]
            )

            return extract_result_text(call_result)


async def execute_http_tool(
    server_config: MCPServerConfig,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    """
    Execute tool on HTTP/SSE MCP server.

    Args:
        server_config: Server configuration dict
        tool_name: Name of the tool to execute
        arguments: Tool arguments

    Returns:
        Tool execution result as string
    """
    if not MCP_AVAILABLE or streamablehttp_client is None:
        return "Error: MCP libraries not available"

    url = server_config.get("url", "")
    if not url:
        return "Error: No URL specified for HTTP server"

    headers = dict(server_config.get("headers", {}))

    # Add auth from config
    auth_type = server_config.get("auth_type", "")
    auth_value = server_config.get("auth_value", "")
    if auth_type == "api_key" and auth_value:
        headers["Authorization"] = f"Bearer {auth_value}"

    openai_tool = create_openai_tool_call(tool_name, arguments)

    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:  # type: ignore[misc]
            await session.initialize()

            call_result = await experimental_mcp_client.call_openai_tool(  # type: ignore[union-attr]
                session=session,
                openai_tool=openai_tool,  # type: ignore[arg-type]
            )

            return extract_result_text(call_result)


async def execute_tool(
    server_config: MCPServerConfig,
    transport: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    """
    Execute a tool based on transport type.

    Args:
        server_config: Server configuration dict
        transport: Transport type ("stdio", "http", or "sse")
        tool_name: Name of the tool to execute
        arguments: Tool arguments

    Returns:
        Tool execution result as string
    """
    try:
        if transport == "stdio":
            return await execute_stdio_tool(server_config, tool_name, arguments)
        elif transport in ("http", "sse"):
            return await execute_http_tool(server_config, tool_name, arguments)
        else:
            return f"Error: Unsupported transport type: {transport}"
    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {e}")
        return f"Error executing {tool_name}: {e}"


def execute_tool_sync(
    server_config: MCPServerConfig,
    transport: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    """
    Synchronous wrapper for execute_tool.

    Args:
        server_config: Server configuration dict
        transport: Transport type ("stdio", "http", or "sse")
        tool_name: Name of the tool to execute
        arguments: Tool arguments

    Returns:
        Tool execution result as string
    """
    return asyncio.run(execute_tool(server_config, transport, tool_name, arguments))


async def execute_tool_with_session(
    session: Any,
    tool_name: str,
    tool_call_id: str,
    arguments: str | dict[str, Any],
) -> str:
    """
    Execute a tool using an existing MCP session.

    This is used during the agentic loop where sessions are kept open
    across multiple tool calls.

    Args:
        session: Active MCP ClientSession
        tool_name: Name of the tool to execute
        tool_call_id: ID of the tool call (from LLM response)
        arguments: Tool arguments (string or dict)

    Returns:
        Tool execution result as string
    """
    if not MCP_AVAILABLE or experimental_mcp_client is None:
        return "Error: MCP libraries not available"

    # Handle arguments as string or dict
    if isinstance(arguments, dict):
        args_str = json.dumps(arguments)
    else:
        args_str = arguments

    openai_tool = {
        "id": tool_call_id,
        "type": "function",
        "function": {
            "name": tool_name,
            "arguments": args_str,
        },
    }

    try:
        call_result = await experimental_mcp_client.call_openai_tool(
            session=session,
            openai_tool=openai_tool,  # type: ignore[arg-type]
        )
        return extract_result_text(call_result)
    except Exception as e:
        logger.error(f"Error executing tool {tool_name} with session: {e}")
        return f"Error executing {tool_name}: {e}"
