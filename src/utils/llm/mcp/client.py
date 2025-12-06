"""
MCP Client - Config-driven Model Context Protocol integration.

Loads MCP server configurations from mcp.json and provides unified tool access.
Supports HTTP/SSE servers with environment variable substitution.
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any

# MCP imports - optional dependency
MCP_AVAILABLE = False
try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    from mcp.types import TextContent, ImageContent, AudioContent, ResourceLink, EmbeddedResource
    MCP_AVAILABLE = True
except ImportError:
    ClientSession = None
    streamablehttp_client = None


class MCPClient:
    """Config-driven MCP client for tool-augmented LLM calls."""

    def __init__(self, servers: bool | list[str] = False):
        """
        Initialize MCP client with server selection.
        
        Args:
            servers: 
                False = no MCP
                True = load ALL servers from mcp.json
                ["exa"] = load only specified servers
                [] = no MCP
        """
        self.config_path = Path(__file__).parent / "mcp.json"
        self.servers_config: dict[str, dict] = {}
        self.tool_to_server: dict[str, str] = {}  # Maps tool name to server name
        
        if servers is False or servers == []:
            return
        
        if not MCP_AVAILABLE:
            raise ImportError("MCP library not available. Install with: pip install mcp")
        
        self._load_config(servers)

    def _load_config(self, servers: bool | list[str]) -> None:
        """Load MCP server configurations from mcp.json."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"MCP config not found: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        all_servers = config.get("mcpServers", {})
        
        if servers is True:
            # Load all servers
            self.servers_config = all_servers
        else:
            # Load only specified servers
            for name in servers:
                if name not in all_servers:
                    raise ValueError(f"Unknown MCP server: {name}. Available: {list(all_servers.keys())}")
                self.servers_config[name] = all_servers[name]
        
        # Substitute environment variables in config
        self._substitute_env_vars()

    def _substitute_env_vars(self) -> None:
        """Replace ${VAR} patterns with environment variable values."""
        def replace_env(obj):
            if isinstance(obj, str):
                # Replace ${VAR} with env value
                pattern = r'\$\{([^}]+)\}'
                matches = re.findall(pattern, obj)
                for var_name in matches:
                    env_value = os.environ.get(var_name, '')
                    obj = obj.replace(f'${{{var_name}}}', env_value)
                return obj
            elif isinstance(obj, dict):
                return {k: replace_env(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [replace_env(item) for item in obj]
            return obj
        
        self.servers_config = replace_env(self.servers_config)

    async def load_tools(self) -> list[dict]:
        """
        Load tools from all configured MCP servers.
        
        Returns:
            List of OpenAI-compatible tool definitions
        """
        if not self.servers_config:
            return []
        
        all_tools = []
        
        for server_name, server_config in self.servers_config.items():
            server_type = server_config.get("type", "http")
            
            if server_type not in ("http", "sse"):
                print(f"Skipping unsupported server type: {server_type}")
                continue
            
            url = server_config.get("url", "")
            headers = server_config.get("headers", {})
            
            # Add auth from env if specified
            env_config = server_config.get("env", {})
            for key, value in env_config.items():
                if value and "API_KEY" in key:
                    headers["Authorization"] = f"Bearer {value}"
            
            try:
                async with streamablehttp_client(url, headers=headers) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools_response = await session.list_tools()
                        
                        for tool in tools_response.tools:
                            # Map tool to server for later execution
                            self.tool_to_server[tool.name] = server_name
                            
                            # Convert to OpenAI format
                            all_tools.append({
                                "type": "function",
                                "function": {
                                    "name": tool.name,
                                    "description": tool.description,
                                    "parameters": tool.inputSchema
                                }
                            })
                
                print(f"Loaded {len([t for t in self.tool_to_server if self.tool_to_server[t] == server_name])} tools from {server_name}")
                
            except Exception as e:
                print(f"Failed to load tools from {server_name}: {e}")
        
        return all_tools

    async def execute_tool(self, tool_name: str, arguments: dict) -> str:
        """
        Execute a tool call by routing to the correct server.
        
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
        
        url = server_config.get("url", "")
        headers = server_config.get("headers", {})
        
        # Add auth from env
        env_config = server_config.get("env", {})
        for key, value in env_config.items():
            if value and "API_KEY" in key:
                headers["Authorization"] = f"Bearer {value}"
        
        try:
            async with streamablehttp_client(url, headers=headers) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, arguments)
                    
                    # Extract text content
                    content_parts = []
                    for c in result.content:
                        if isinstance(c, TextContent):
                            content_parts.append(getattr(c, 'text', ''))
                        elif isinstance(c, ImageContent):
                            content_parts.append(f"[Image: {getattr(c, 'uri', 'N/A')}]")
                        elif isinstance(c, AudioContent):
                            content_parts.append(f"[Audio: {getattr(c, 'uri', 'N/A')}]")
                        elif isinstance(c, ResourceLink):
                            content_parts.append(f"[Resource: {getattr(c, 'uri', 'N/A')}]")
                        elif isinstance(c, EmbeddedResource):
                            content_parts.append(f"[Embedded: {getattr(c, 'uri', 'N/A')}]")
                        else:
                            content_parts.append(str(c))
                    
                    return "\n".join(content_parts)
                    
        except Exception as e:
            return f"Error executing {tool_name}: {e}"

    def load_tools_sync(self) -> list[dict]:
        """Synchronous wrapper for load_tools."""
        return asyncio.run(self.load_tools())

    def execute_tool_sync(self, tool_name: str, arguments: dict) -> str:
        """Synchronous wrapper for execute_tool."""
        return asyncio.run(self.execute_tool(tool_name, arguments))


def get_available_servers() -> list[str]:
    """Get list of available MCP server names from config."""
    config_path = Path(__file__).parent / "mcp.json"
    if not config_path.exists():
        return []
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    return list(config.get("mcpServers", {}).keys())
