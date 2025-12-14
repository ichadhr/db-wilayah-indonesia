#!/usr/bin/env python3
"""
MCP Tool Checker - Test MCP tool support using LLMClient.

Usage:
    # List available tools
    python src/scripts/mcp_tool_checker.py --list-tools

    # Ask AI with MCP tools
    python src/scripts/mcp_tool_checker.py --ask-ai "search for latest kabupaten/kota updates in indonesia"
"""

import argparse
import sys
from pathlib import Path

# Add src directory to path
src_dir = Path(__file__).parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from utils.llm.client import LLMClient  # noqa: E402
from utils.llm.config import load_config  # noqa: E402
from utils.llm.mcp.client import MCPClient, get_available_servers  # noqa: E402


def list_tools():
    """List all available MCP tools."""
    print("\n=== Available MCP Servers ===")
    servers = get_available_servers()
    print(f"Servers: {servers}\n")

    for server in servers:
        print(f"\n--- Tools from '{server}' ---")
        try:
            client = MCPClient([server])
            tools = client.load_tools_sync()
            for tool in tools:
                name = tool["function"]["name"]
                desc = tool["function"].get("description", "No description")[:100]
                print(f"  • {name}: {desc}...")
        except Exception as e:
            print(f"  Error loading tools: {e}")


def ask_ai(prompt: str, servers: list[str] | None = None):
    """Ask AI with MCP tools."""
    print("\n=== MCP Tool Test ===")
    print(f"Prompt: {prompt}")
    print(f"Servers: {servers or 'all'}\n")

    config = load_config()
    llm = LLMClient(config)

    # Use all servers if none specified
    mcp_setting = servers if servers else True

    system_prompt = """You are a helpful assistant with access to web search tools.
Use the available tools to find accurate, up-to-date information.
Always cite your sources and provide clear, structured answers."""

    # Simple output schema for testing
    output_schema = {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "description": "Your answer to the question"},
            "sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "URLs or references used",
            },
        },
        "required": ["answer"],
    }

    try:
        result = llm.call_llm(
            system_prompt=system_prompt,
            user_prompt=prompt,
            output_schema=output_schema,
            mcp=mcp_setting,
            verbose=True,
        )

        print("\n" + "=" * 50)
        print("FINAL RESULT:")
        print("=" * 50)
        print(f"\nAnswer: {result.get('answer', 'No answer')}")

        sources = result.get("sources", [])
        if sources:
            print("\nSources:")
            for src in sources:
                print(f"  - {src}")

        return result

    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback

        traceback.print_exc()
        return None


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="MCP Tool Checker - Test MCP tool support",
    )
    parser.add_argument(
        "--list-tools", action="store_true", help="List available MCP tools"
    )
    parser.add_argument("--ask-ai", type=str, help="Ask AI with MCP tools")
    parser.add_argument(
        "--servers",
        type=str,
        help="Comma-separated list of servers to use (default: all)",
    )

    args = parser.parse_args()

    if args.list_tools:
        list_tools()
    elif args.ask_ai:
        servers = args.servers.split(",") if args.servers else None
        ask_ai(args.ask_ai, servers)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
