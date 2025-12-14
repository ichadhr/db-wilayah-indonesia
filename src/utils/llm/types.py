"""
Type aliases for LLM module.

Centralizes type definitions used across the LLM utilities for better
maintainability and type safety.
"""

from typing import Any, Callable, Coroutine, TypeAlias

# =============================================================================
# Basic Types
# =============================================================================

# JSON-compatible types
JSONValue: TypeAlias = (
    str | int | float | bool | None | list["JSONValue"] | dict[str, "JSONValue"]
)
JSONDict: TypeAlias = dict[str, Any]
JSONList: TypeAlias = list[dict[str, Any]]

# =============================================================================
# Message Types
# =============================================================================

# OpenAI-style message format
Message: TypeAlias = dict[str, Any]
MessageList: TypeAlias = list[Message]

# Tool definition (OpenAI format)
ToolDefinition: TypeAlias = dict[str, Any]
ToolList: TypeAlias = list[ToolDefinition]

# Tool call from LLM response
ToolCall: TypeAlias = dict[str, Any]
ToolCallList: TypeAlias = list[ToolCall]

# =============================================================================
# MCP Types
# =============================================================================

# MCP server configuration
MCPServerConfig: TypeAlias = dict[str, Any]
MCPServersConfig: TypeAlias = dict[str, MCPServerConfig]

# MCP session info stored during agentic loop
# Tuple of (context_manager, session_context, session, transport_type)
MCPSessionInfo: TypeAlias = tuple[Any, Any, Any, str]
MCPSessionsDict: TypeAlias = dict[str, MCPSessionInfo]

# Tool to server mapping
ToolServerMapping: TypeAlias = dict[str, str]

# =============================================================================
# Callback Types
# =============================================================================

# Async tool executor function signature
AsyncToolExecutor: TypeAlias = Callable[
    [str, dict[str, Any]],  # tool_name, arguments
    Coroutine[Any, Any, str],  # returns result string
]

# Sync tool executor function signature
SyncToolExecutor: TypeAlias = Callable[
    [str, dict[str, Any]],  # tool_name, arguments
    str,  # returns result string
]

# =============================================================================
# LLM Response Types
# =============================================================================

# LLM completion response (simplified)
LLMResponse: TypeAlias = dict[str, Any]

# Token usage info
TokenUsage: TypeAlias = dict[str, int]

# =============================================================================
# Schema Types
# =============================================================================

# JSON Schema for structured output
JSONSchema: TypeAlias = dict[str, Any]

# Correction record (app-specific but commonly used)
CorrectionRecord: TypeAlias = dict[str, Any]
CorrectionList: TypeAlias = list[CorrectionRecord]
