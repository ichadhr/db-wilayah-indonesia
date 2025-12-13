"""
LLM Client - Reusable LiteLLM wrapper with JSON sanitization and MCP support.

This module provides a unified interface for LLM calls with:
- Streaming support
- JSON response sanitization
- Token counting
- MCP tool integration
- Error handling
"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional, Union, cast

import litellm
from litellm.utils import token_counter

from utils.llm.config import LLMConfig


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

        def escape_in_string(match):
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
                - ["exa"] = load only specified servers
                - [] = no MCP
            stream: Whether to stream the response
            verbose: Whether to print progress

        Returns:
            Parsed JSON response
        """
        # Check if MCP is requested
        if mcp is True or (isinstance(mcp, list) and len(mcp) > 0):
            return asyncio.run(
                self._call_llm_with_mcp(
                    system_prompt, user_prompt, output_schema, mcp, verbose
                )
            )

        # Standard LLM call without MCP
        return self._call_llm_standard(
            system_prompt, user_prompt, output_schema, stream, verbose
        )

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
                print(f"\n[OK] LLM call successful")
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
                    print(f"  Tokens used: unknown")

            return result

        except json.JSONDecodeError as e:
            print(f"Error: Failed to parse LLM response as JSON")
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

        Implements agentic loop: LLM calls tools, results fed back until final answer.
        Token usage is accumulated across all iterations.
        """
        from utils.llm.mcp.client import MCPClient

        # Initialize MCP client and load tools
        mcp_client = MCPClient(mcp)
        tools = await mcp_client.load_tools()

        if verbose:
            print(f"\n[MCP] Loaded {len(tools)} tools from servers")
            for tool in tools[:5]:  # Show first 5 tools
                print(f"  - {tool['function']['name']}")
            if len(tools) > 5:
                print(f"  ... and {len(tools) - 5} more")

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
            print(f"\n[MCP] Calling LLM: {llm_params['model']}")
            print(f"[MCP] Max iterations: {max_iterations}")

        # Token tracking
        total_prompt_tokens = 0
        total_completion_tokens = 0

        # Agentic loop
        for iteration in range(max_iterations):
            if verbose:
                print(f"\n{'=' * 50}")
                print(f"[MCP] Iteration {iteration + 1}/{max_iterations}")
                print(f"{'=' * 50}")

            response = litellm.completion(
                messages=messages, tools=tools if tools else None, **llm_params
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

            # Use cast to tell Pylance about the expected response structure
            response_typed = cast(Dict[str, Any], response)
            assistant_message = response_typed["choices"][0]["message"]
            # Convert message to dict if it's not already (handles both dict and object cases)
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
                    print(f"\n[MCP] Final response received")
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

                result = await mcp_client.execute_tool(tool_name, tool_args)

                if verbose:
                    result_preview = (
                        result[:300] + "..." if len(result) > 300 else result
                    )
                    print(f"[MCP] Result ({len(result)} chars): {result_preview}")

                messages.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": result}
                )

        print(f"\n[MCP ERROR] Max iterations ({max_iterations}) reached")
        print(
            f"[MCP] Total tokens used: {total_prompt_tokens + total_completion_tokens}"
        )
        raise RuntimeError(
            f"Max iterations ({max_iterations}) reached without final answer"
        )
