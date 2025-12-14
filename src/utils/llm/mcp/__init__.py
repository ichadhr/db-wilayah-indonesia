"""
MCP integration for LLM toolkit.

This module provides MCP (Model Context Protocol) integration for tool-augmented
LLM calls. It includes:

- MCPClient: Main client for loading and executing MCP tools
- Configuration loading utilities
- Tool execution across different transports (stdio, http, sse)
"""

from .client import MCPClient
from .config import (
    get_available_servers,
    get_config_path,
    get_server_auth_headers,
    get_server_transport,
    load_mcp_config,
)
from .executor import (
    check_mcp_available,
    create_openai_tool_call,
    execute_http_tool,
    execute_stdio_tool,
    execute_tool,
    execute_tool_sync,
    execute_tool_with_session,
    extract_result_text,
)

__all__ = [
    # Main client
    "MCPClient",
    # Config utilities
    "get_available_servers",
    "get_config_path",
    "get_server_auth_headers",
    "get_server_transport",
    "load_mcp_config",
    # Executor utilities
    "check_mcp_available",
    "create_openai_tool_call",
    "execute_http_tool",
    "execute_stdio_tool",
    "execute_tool",
    "execute_tool_sync",
    "execute_tool_with_session",
    "extract_result_text",
]
