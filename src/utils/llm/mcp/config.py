"""
MCP Configuration Loader.

Handles loading and processing of MCP server configurations from mcp.json.
Supports environment variable substitution and server filtering.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

# Type aliases
MCPServerConfig = dict[str, Any]
MCPServersConfig = dict[str, MCPServerConfig]


def get_config_path() -> Path:
    """Get the default path to mcp.json configuration file."""
    return Path(__file__).parent / "mcp.json"


def load_mcp_config(
    config_path: Path | None = None,
    servers: bool | list[str] = True,
) -> MCPServersConfig:
    """
    Load MCP server configurations from mcp.json.

    Args:
        config_path: Path to mcp.json file (defaults to module directory)
        servers: Server selection
            - True = load ALL servers
            - False or [] = return empty dict
            - ["server1", "server2"] = load only specified servers

    Returns:
        Dictionary of server configurations

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If specified server name not found in config
    """
    if servers is False or servers == []:
        return {}

    if config_path is None:
        config_path = get_config_path()

    if not config_path.exists():
        raise FileNotFoundError(f"MCP config not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    all_servers: MCPServersConfig = config.get("mcpServers", {})

    # Filter servers if specific list provided
    if servers is True:
        selected_servers = all_servers
    elif isinstance(servers, list):
        selected_servers = {}
        for name in servers:
            if name not in all_servers:
                available = list(all_servers.keys())
                raise ValueError(f"Unknown MCP server: {name}. Available: {available}")
            selected_servers[name] = all_servers[name]
    else:
        selected_servers = {}

    # Substitute environment variables
    return substitute_env_vars(selected_servers)


def substitute_env_vars(config: MCPServersConfig) -> MCPServersConfig:
    """
    Replace ${VAR} patterns with environment variable values.

    Recursively processes all string values in the configuration,
    replacing ${VAR_NAME} patterns with corresponding environment
    variable values.

    Args:
        config: Server configuration dictionary

    Returns:
        Configuration with environment variables substituted
    """

    def replace_env(obj: Any) -> Any:
        if isinstance(obj, str):
            pattern = r"\$\{([^}]+)\}"
            matches = re.findall(pattern, obj)
            for var_name in matches:
                env_value = os.environ.get(var_name, "")
                obj = obj.replace(f"${{{var_name}}}", env_value)
            return obj
        elif isinstance(obj, dict):
            return {k: replace_env(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [replace_env(item) for item in obj]
        return obj

    return replace_env(config)


def get_available_servers(config_path: Path | None = None) -> list[str]:
    """
    Get list of available MCP server names from config.

    Args:
        config_path: Path to mcp.json file (defaults to module directory)

    Returns:
        List of server names, or empty list if config doesn't exist
    """
    if config_path is None:
        config_path = get_config_path()

    if not config_path.exists():
        return []

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    return list(config.get("mcpServers", {}).keys())


def get_server_transport(server_config: MCPServerConfig) -> str:
    """
    Determine the transport type for a server configuration.

    Args:
        server_config: Single server configuration dict

    Returns:
        Transport type: "stdio", "http", or "sse"
    """
    # Check explicit transport field
    transport = server_config.get("transport", "")
    if transport:
        return transport

    # Check type field
    server_type = server_config.get("type", "")
    if server_type in ("http", "sse"):
        return server_type

    # Infer from URL
    if "url" in server_config:
        url = server_config.get("url", "")
        if "/sse" in url or url.endswith("/sse"):
            return "sse"
        return "http"

    # Infer from command (stdio)
    if "command" in server_config:
        return "stdio"

    # Default to http
    return "http"


def get_server_auth_headers(server_config: MCPServerConfig) -> dict[str, str]:
    """
    Extract authentication headers from server configuration.

    Args:
        server_config: Single server configuration dict

    Returns:
        Dictionary of headers to include in requests
    """
    headers = dict(server_config.get("headers", {}))

    # Add auth from explicit config
    auth_type = server_config.get("auth_type", "")
    auth_value = server_config.get("auth_value", "")
    if auth_type == "api_key" and auth_value:
        headers["Authorization"] = f"Bearer {auth_value}"

    # Add auth from env config
    env_config = server_config.get("env", {})
    for key, value in env_config.items():
        if value and "API_KEY" in key:
            headers["Authorization"] = f"Bearer {value}"

    return headers
