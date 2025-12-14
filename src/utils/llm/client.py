"""
LLM Client - Reusable LiteLLM wrapper with JSON sanitization and MCP support.

This module provides a unified interface for LLM calls with:
- Streaming support
- JSON response sanitization
- Token counting
- MCP tool integration via litellm experimental_mcp_client
- Error handling
"""

import asyncio
import json
import logging
import re
from contextlib import AsyncExitStack
from typing import Any, Dict, List, cast

import litellm
from litellm.utils import token_counter

from utils.llm.config import LLMConfig

# Configure logging
logger = logging.getLogger(__name__)


class LLMClient:
    """Reusable LiteLLM wrapper with JSON sanitization and MCP support."""

    def __init__(self, config: LLMConfig):
        """Initialize LLM client with configuration."""
        self.config = config

    @staticmethod
    def sanitize_json(content: str) -> str:
        """
        Sanitize JSON string by escaping control characters.

        LLMs sometimes put raw newlines/tabs in JSON strings which are invalid.
        This method escapes them properly.
        """

        def escape_in_string(match: re.Match[str]) -> str:
            s = match.group(0)
            s = s.replace("\n", "\\n")
            s = s.replace("\r", "\\r")
            s = s.replace("\t", "\\t")
            return s

        # Match JSON strings (accounting for escaped quotes)
        return re.sub(r'"(?:[^"\\]|\\.)*"', escape_in_string, content)

    @staticmethod
    def extract_json(content: str) -> str:
        """Extract JSON from response that may be wrapped in markdown."""
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        return content

    def call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: dict | None = None,
        mcp: bool | list[str] = False,
        stream: bool = True,
        verbose: bool = True,
    ) -> dict[str, Any]:
        """
        Call LLM for structured JSON output, optionally with MCP tools.

        Args:
            system_prompt: System role definition
            user_prompt: User query with data
            output_schema: JSON schema for structured output (optional)
            mcp: MCP server selection
                - False = no MCP (default)
                - True = load ALL servers from mcp.json
                - ["databeak"] = load only specified servers
                - [] = no MCP
            stream: Whether to stream the response
            verbose: Whether to print progress

        Returns:
            Parsed JSON response
        """
        # Check if MCP is requested
        if mcp is True or (isinstance(mcp, list) and len(mcp) > 0):
            try:
                return asyncio.run(
                    self._call_llm_with_mcp(
                        system_prompt, user_prompt, output_schema, mcp, verbose
                    )
                )
            except KeyboardInterrupt:
                print("\n[MCP] Interrupted by user (CTRL-C)")
                print("[MCP] Cleaning up MCP sessions...")
                raise

        # Standard LLM call without MCP
        return self._call_llm_standard(
            system_prompt, user_prompt, output_schema, stream, verbose
        )

    def call_llm_batch(
        self,
        calls: list[dict[str, Any]],
        mcp: bool | list[str] = False,
        verbose: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Process multiple LLM calls in a single event loop with shared MCP sessions.

        This avoids the "bound to a different event loop" error that occurs when
        calling asyncio.run() multiple times with LiteLLM's internal logging queue.

        Args:
            calls: List of call configs, each with:
                - system_prompt: str
                - user_prompt: str
                - output_schema: dict | None (optional)
            mcp: MCP server selection (same as call_llm)
            verbose: Whether to print progress

        Returns:
            List of parsed JSON responses (in same order as calls)

        Example:
            results = llm.call_llm_batch([
                {"system_prompt": "...", "user_prompt": "batch 1"},
                {"system_prompt": "...", "user_prompt": "batch 2"},
            ], mcp=["databeak"])
        """
        if mcp is True or (isinstance(mcp, list) and len(mcp) > 0):
            try:
                return asyncio.run(self._call_llm_batch_with_mcp(calls, mcp, verbose))
            except KeyboardInterrupt:
                print("\n[MCP] Interrupted by user (CTRL-C)")
                print("[MCP] Cleaning up MCP sessions...")
                raise

        # Standard LLM calls without MCP
        results = []
        for call in calls:
            result = self._call_llm_standard(
                call["system_prompt"],
                call["user_prompt"],
                call.get("output_schema"),
                stream=True,
                verbose=verbose,
            )
            results.append(result)
        return results

    async def _call_llm_batch_with_mcp(
        self,
        calls: list[dict[str, Any]],
        mcp: bool | list[str] = True,
        verbose: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Process multiple LLM calls with shared MCP sessions in a single async context.

        This keeps MCP sessions open across all calls, avoiding repeated subprocess
        spawning and event loop issues.
        """
        import os

        from litellm import experimental_mcp_client
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from mcp.client.streamable_http import streamablehttp_client

        from utils.llm.mcp.client import MCPClient

        # Initialize MCP client
        mcp_client = MCPClient(mcp)
        llm_params = self.config.get_litellm_params()

        if verbose:
            print(f"\n[MCP Batch] Processing {len(calls)} calls")
            print(f"[MCP Batch] LLM: {llm_params['model']}")

        # Load tools and sessions once
        all_tools: List[Any] = []
        server_sessions: dict[str, tuple[Any, str]] = {}
        stdio_processes: list[Any] = []

        async with AsyncExitStack() as stack:
            # Setup MCP servers once
            for server_name, server_config in mcp_client.servers_config.items():
                transport = server_config.get("transport", "")
                server_type = server_config.get("type", "")

                if not transport:
                    if server_type in ("http", "sse"):
                        transport = server_type
                    elif "url" in server_config:
                        url = server_config.get("url", "")
                        transport = "sse" if "/sse" in url else "http"
                    elif "command" in server_config:
                        transport = "stdio"
                    else:
                        transport = "http"

                if transport == "stdio":
                    command = server_config.get("command", "")
                    args = server_config.get("args", [])
                    env = server_config.get("env", {})

                    if not command:
                        continue

                    print(
                        f"[MCP Batch] Spawning stdio server: {server_name} (reused for all calls)"
                    )

                    server_params = StdioServerParameters(
                        command=command,
                        args=args,
                        env={**os.environ, **env} if env else None,
                    )

                    stdio_ctx = stdio_client(server_params)
                    read, write = await stack.enter_async_context(stdio_ctx)
                    stdio_processes.append(stdio_ctx)

                    session = await stack.enter_async_context(
                        ClientSession(read, write)
                    )
                    await session.initialize()

                    tools = await experimental_mcp_client.load_mcp_tools(
                        session=session, format="openai"
                    )
                    all_tools.extend(tools)
                    server_sessions[server_name] = (session, "stdio")

                elif transport in ("http", "sse"):
                    url = server_config.get("url", "")
                    if not url:
                        continue

                    headers = server_config.get("headers", {})
                    auth_type = server_config.get("auth_type", "")
                    auth_value = server_config.get("auth_value", "")
                    if auth_type == "api_key" and auth_value:
                        headers["Authorization"] = f"Bearer {auth_value}"

                    print(
                        f"[MCP Batch] Connecting to {transport} server: {server_name}"
                    )

                    read, write, _ = await stack.enter_async_context(
                        streamablehttp_client(url, headers=headers)
                    )
                    session = await stack.enter_async_context(
                        ClientSession(read, write)
                    )
                    await session.initialize()

                    tools = await experimental_mcp_client.load_mcp_tools(
                        session=session, format="openai"
                    )
                    all_tools.extend(tools)
                    server_sessions[server_name] = (session, transport)

                # Map tools to server
                for tool in tools:
                    if isinstance(tool, dict):
                        tool_name = tool.get("function", {}).get("name", "")
                    else:
                        tool_name = getattr(tool, "name", "") or ""
                    if tool_name:
                        mcp_client.tool_to_server[tool_name] = server_name

                print(f"[MCP Batch] Loaded {len(tools)} tools from {server_name}")

            if verbose:
                print(f"[MCP Batch] Total tools loaded: {len(all_tools)}")

            # Process all calls with shared sessions
            results = []
            for idx, call in enumerate(calls):
                if verbose:
                    print(f"\n[MCP Batch] Processing call {idx + 1}/{len(calls)}")

                result = await self._execute_single_mcp_call(
                    call["system_prompt"],
                    call["user_prompt"],
                    call.get("output_schema"),
                    all_tools,
                    server_sessions,
                    mcp_client,
                    llm_params,
                    verbose,
                )
                results.append(result)

            print(f"\n[MCP Batch] All {len(calls)} calls completed")
            return results

        print("[MCP Batch] All sessions closed")
        return []

    async def _execute_single_mcp_call(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: dict | None,
        all_tools: List[Any],
        server_sessions: dict[str, tuple[Any, str]],
        mcp_client: Any,
        llm_params: dict[str, Any],
        verbose: bool,
        max_iterations: int = 10,
    ) -> dict[str, Any]:
        """Execute a single LLM call with pre-loaded MCP tools and sessions."""
        from litellm import experimental_mcp_client

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        if output_schema:
            messages.append(
                {
                    "role": "user",
                    "content": f"Output must be valid JSON matching this schema:\n{json.dumps(output_schema, indent=2)}",
                }
            )

        for iteration in range(max_iterations):
            response = await litellm.acompletion(
                messages=messages,
                tools=all_tools if all_tools else None,
                **llm_params,
            )

            response_typed = cast(Dict[str, Any], response)
            assistant_message = response_typed["choices"][0]["message"]

            if hasattr(assistant_message, "model_dump"):
                messages.append(assistant_message.model_dump())
            else:
                messages.append(assistant_message)

            tool_calls = getattr(assistant_message, "tool_calls", None)

            if not tool_calls:
                content = assistant_message.content or ""
                content = self.extract_json(content)
                content = self.sanitize_json(content)
                return json.loads(content)

            # Execute tool calls
            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                server_name = mcp_client.tool_to_server.get(tool_name)

                if server_name and server_name in server_sessions:
                    session, _ = server_sessions[server_name]

                    call_result = await experimental_mcp_client.call_openai_tool(
                        session=session,
                        openai_tool={
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": tool_call.function.arguments,
                            },
                        },
                    )

                    if hasattr(call_result, "content") and call_result.content:
                        first_content = call_result.content[0]
                        result = str(getattr(first_content, "text", str(first_content)))
                    else:
                        result = str(call_result)
                else:
                    result = f"Error: Tool {tool_name} not found"

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    }
                )

        raise RuntimeError(f"Max iterations ({max_iterations}) reached")

    def _call_llm_standard(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: dict | None = None,
        stream: bool = True,
        verbose: bool = True,
    ) -> dict[str, Any]:
        """Standard LLM call without MCP tools."""
        llm_params = self.config.get_litellm_params()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        if output_schema:
            messages.append(
                {
                    "role": "user",
                    "content": f"Output must be valid JSON matching this schema:\n{json.dumps(output_schema, indent=2)}",
                }
            )

        if verbose:
            print(f"\nCalling LLM: {llm_params['model']}")
            print(
                f"Temperature: {llm_params['temperature']}, Max Tokens: {llm_params.get('max_tokens', 'default')}"
            )

        # Calculate input tokens
        input_tokens = None
        try:
            input_tokens = token_counter(model=llm_params["model"], messages=messages)
            if verbose:
                print(f"Input tokens: {input_tokens}")
        except Exception as e:
            if verbose:
                print(f"Could not calculate input tokens: {e}")

        content = ""
        try:
            response = litellm.completion(
                messages=messages, stream=stream, **llm_params
            )

            if stream:
                for chunk in response:
                    delta = getattr(getattr(chunk, "choices", [{}])[0], "delta", {})
                    delta_content = delta.get("content", "")
                    if delta_content:
                        if verbose:
                            print(delta_content, end="", flush=True)
                        content += delta_content
            else:
                # Use cast to tell Pylance about the expected response structure
                response_typed = cast(Dict[str, Any], response)
                content = response_typed["choices"][0]["message"]["content"]

            if not isinstance(content, str):
                raise ValueError(f"Unexpected response content type: {type(content)}")

            # Extract and sanitize JSON
            content = self.extract_json(content)
            content = self.sanitize_json(content)
            result = json.loads(content)

            if verbose:
                print("\n[OK] LLM call successful")
                try:
                    output_tokens = token_counter(
                        model=llm_params["model"], text=content
                    )
                    total_tokens = (
                        (input_tokens + output_tokens)
                        if input_tokens
                        else output_tokens
                    )
                    print(
                        f"  Tokens used: {total_tokens} (input: {input_tokens or 'unknown'}, output: {output_tokens})"
                    )
                except Exception:
                    print("  Tokens used: unknown")

            return result

        except json.JSONDecodeError as e:
            print("Error: Failed to parse LLM response as JSON")
            print(f"JSON Error: {e}")
            if content:
                print(f"Response length: {len(content)} characters")
                print(f"Response content (first 500 chars): {content[:500]}...")

                # Try to extract JSON if wrapped in other text
                json_match = re.search(r"\{.*\}", content, re.DOTALL)
                if json_match:
                    try:
                        result = json.loads(self.sanitize_json(json_match.group()))
                        print("[OK] Successfully extracted JSON from response")
                        return result
                    except json.JSONDecodeError:
                        pass
            raise

        except Exception as e:
            print(f"Error calling LLM: {e}")
            raise

    async def _call_llm_with_mcp(
        self,
        system_prompt: str,
        user_prompt: str,
        output_schema: dict | None = None,
        mcp: bool | list[str] = True,
        verbose: bool = True,
        max_iterations: int = 10,
    ) -> dict[str, Any]:
        """
        Call LLM with MCP tool support (async).

        Uses litellm.acompletion and experimental_mcp_client for tool calling.
        Implements agentic loop: LLM calls tools, results fed back until final answer.
        Token usage is accumulated across all iterations.
        """
        import os

        from litellm import experimental_mcp_client
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        from mcp.client.streamable_http import streamablehttp_client

        from utils.llm.mcp.client import MCPClient

        # Initialize MCP client and load tools
        mcp_client = MCPClient(mcp)

        llm_params = self.config.get_litellm_params()

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        if output_schema:
            messages.append(
                {
                    "role": "user",
                    "content": f"Output must be valid JSON matching this schema:\n{json.dumps(output_schema, indent=2)}",
                }
            )

        if verbose:
            print(f"\n[MCP] Calling LLM: {llm_params['model']}")
            print(f"[MCP] Max iterations: {max_iterations}")

        # Token tracking
        total_prompt_tokens = 0
        total_completion_tokens = 0

        # Load tools and get server config for tool execution
        all_tools: List[Any] = []
        server_sessions: dict[str, tuple[Any, str]] = {}  # (session, transport_type)

        # Track stdio processes for cleanup on interruption
        stdio_processes: list[Any] = []

        # Use AsyncExitStack for proper cleanup of all context managers
        async with AsyncExitStack() as stack:
            # Register callback to ensure stdio processes are terminated
            async def cleanup_stdio_processes() -> None:
                """Cleanup callback for stdio processes."""
                for proc_info in stdio_processes:
                    try:
                        if hasattr(proc_info, "terminate"):
                            proc_info.terminate()
                            print(f"[MCP] Terminated stdio process")
                    except Exception as e:
                        logger.debug(f"Error terminating process: {e}")

            stack.push_async_callback(lambda: cleanup_stdio_processes())
            # Load tools from all configured servers
            for server_name, server_config in mcp_client.servers_config.items():
                # Determine transport type
                transport = server_config.get("transport", "")
                server_type = server_config.get("type", "")

                # Infer transport if not specified
                if not transport:
                    if server_type in ("http", "sse"):
                        transport = server_type
                    elif "url" in server_config:
                        url = server_config.get("url", "")
                        transport = "sse" if "/sse" in url else "http"
                    elif "command" in server_config:
                        transport = "stdio"
                    else:
                        transport = "http"

                if transport == "stdio":
                    command = server_config.get("command", "")
                    args = server_config.get("args", [])
                    env = server_config.get("env", {})

                    if not command:
                        continue

                    print(
                        f"[MCP] Spawning stdio server: {server_name} ({command} {' '.join(args)})"
                    )

                    server_params = StdioServerParameters(
                        command=command,
                        args=args,
                        env={**os.environ, **env} if env else None,
                    )

                    # Use AsyncExitStack to manage context managers
                    stdio_ctx = stdio_client(server_params)
                    read, write = await stack.enter_async_context(stdio_ctx)

                    # Track the stdio context for cleanup
                    stdio_processes.append(stdio_ctx)

                    session = await stack.enter_async_context(
                        ClientSession(read, write)
                    )
                    await session.initialize()

                    # Load tools
                    tools = await experimental_mcp_client.load_mcp_tools(
                        session=session, format="openai"
                    )
                    all_tools.extend(tools)

                    # Store session for tool execution
                    server_sessions[server_name] = (session, "stdio")

                elif transport in ("http", "sse"):
                    url = server_config.get("url", "")
                    if not url:
                        continue

                    headers = server_config.get("headers", {})

                    # Add auth from config
                    auth_type = server_config.get("auth_type", "")
                    auth_value = server_config.get("auth_value", "")
                    if auth_type == "api_key" and auth_value:
                        headers["Authorization"] = f"Bearer {auth_value}"

                    print(
                        f"[MCP] Connecting to {transport} server: {server_name} ({url})"
                    )

                    # Use AsyncExitStack to manage context managers
                    read, write, _ = await stack.enter_async_context(
                        streamablehttp_client(url, headers=headers)
                    )
                    session = await stack.enter_async_context(
                        ClientSession(read, write)
                    )
                    await session.initialize()

                    # Load tools
                    tools = await experimental_mcp_client.load_mcp_tools(
                        session=session, format="openai"
                    )
                    all_tools.extend(tools)

                    # Store session for tool execution
                    server_sessions[server_name] = (session, transport)

                else:
                    print(f"[MCP] Skipping unsupported transport: {transport}")
                    continue

                # Map tools to server
                for tool in tools:
                    if isinstance(tool, dict):
                        tool_name = tool.get("function", {}).get("name", "")
                    else:
                        tool_name = getattr(tool, "name", "") or ""
                    if tool_name:
                        mcp_client.tool_to_server[tool_name] = server_name

                print(f"[MCP] Loaded {len(tools)} tools from {server_name}")

            if verbose:
                print(f"\n[MCP] Total tools loaded: {len(all_tools)}")
                for tool in all_tools[:5]:
                    print(f"  - {tool['function']['name']}")
                if len(all_tools) > 5:
                    print(f"  ... and {len(all_tools) - 5} more")

            # Agentic loop
            for iteration in range(max_iterations):
                if verbose:
                    print(f"\n{'=' * 50}")
                    print(f"[MCP] Iteration {iteration + 1}/{max_iterations}")
                    print(f"{'=' * 50}")

                # Use litellm.acompletion for async call
                response = await litellm.acompletion(
                    messages=messages,
                    tools=all_tools if all_tools else None,
                    **llm_params,
                )

                # Track tokens
                usage = getattr(response, "usage", None)
                if usage:
                    total_prompt_tokens += getattr(usage, "prompt_tokens", 0)
                    total_completion_tokens += getattr(usage, "completion_tokens", 0)
                    if verbose:
                        print(
                            f"[MCP] Tokens this call: prompt={getattr(usage, 'prompt_tokens', 0)}, completion={getattr(usage, 'completion_tokens', 0)}"
                        )

                # Get assistant message
                response_typed = cast(Dict[str, Any], response)
                assistant_message = response_typed["choices"][0]["message"]

                # Convert message to dict if needed
                if hasattr(assistant_message, "model_dump"):
                    messages.append(assistant_message.model_dump())
                else:
                    messages.append(assistant_message)

                # Check for tool calls
                tool_calls = getattr(assistant_message, "tool_calls", None)

                if not tool_calls:
                    # No tool calls - extract final answer
                    content = assistant_message.content or ""

                    if verbose:
                        print("\n[MCP] Final response received")
                        print(
                            f"[MCP] Total tokens: prompt={total_prompt_tokens}, completion={total_completion_tokens}, total={total_prompt_tokens + total_completion_tokens}"
                        )
                        print(f"[MCP] Iterations used: {iteration + 1}")

                    content = self.extract_json(content)
                    content = self.sanitize_json(content)
                    return json.loads(content)

                # Execute tool calls
                if verbose:
                    print(f"[MCP] Tool calls: {len(tool_calls)}")

                for tool_call in tool_calls:
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)

                    if verbose:
                        print(f"\n[MCP] Calling: {tool_name}")
                        print(f"[MCP] Args: {json.dumps(tool_args, indent=2)[:200]}...")

                    # Find the server for this tool
                    server_name = mcp_client.tool_to_server.get(tool_name)
                    if server_name and server_name in server_sessions:
                        session, _ = server_sessions[server_name]

                        # Use litellm's experimental_mcp_client to call tool
                        call_result = await experimental_mcp_client.call_openai_tool(
                            session=session,
                            openai_tool={
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": tool_call.function.arguments,
                                },
                            },  # type: ignore[arg-type]
                        )

                        # Extract result text
                        if hasattr(call_result, "content") and call_result.content:
                            first_content = call_result.content[0]
                            result = str(
                                getattr(first_content, "text", str(first_content))
                            )
                        else:
                            result = str(call_result)
                    else:
                        result = f"Error: Tool {tool_name} not found"

                    if verbose:
                        result_preview = (
                            result[:300] + "..." if len(result) > 300 else result
                        )
                        print(f"[MCP] Result ({len(result)} chars): {result_preview}")

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        }
                    )

            # Max iterations reached without final answer
            print(f"\n[MCP ERROR] Max iterations ({max_iterations}) reached")
            print(
                f"[MCP] Total tokens used: {total_prompt_tokens + total_completion_tokens}"
            )
            raise RuntimeError(
                f"Max iterations ({max_iterations}) reached without final answer"
            )

        # AsyncExitStack handles cleanup automatically when exiting the context
        # This includes normal exit, exceptions, and cancellation
        # Stdio processes are also cleaned up via the registered callback
        print("[MCP] All sessions and stdio processes closed")
        # This line is only reached if the loop completes without returning or raising
        # which shouldn't happen, but we need a return for type checking
        raise RuntimeError("Unexpected exit from MCP loop")
