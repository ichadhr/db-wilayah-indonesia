"""
LLM utilities for data correction systems.

This module provides reusable components for LLM-based data correction:
- LLMClient: LiteLLM wrapper with JSON sanitization
- MCPClient: MCP server integration for tool-augmented calls
- Schemas: Prompt templates and output schemas
- Handlers: Core utilities for JSON processing
- Types: Type aliases for the module
"""

from .client import LLMClient
from .config import LLMConfig, load_config
from .types import (
    CorrectionList,
    CorrectionRecord,
    JSONDict,
    JSONList,
    JSONSchema,
    JSONValue,
    LLMResponse,
    MCPServerConfig,
    MCPServersConfig,
    MCPSessionInfo,
    MCPSessionsDict,
    Message,
    MessageList,
    TokenUsage,
    ToolCall,
    ToolCallList,
    ToolDefinition,
    ToolList,
    ToolServerMapping,
)

__all__ = [
    # Main classes
    "LLMClient",
    "LLMConfig",
    "load_config",
    # Type aliases - Basic
    "JSONValue",
    "JSONDict",
    "JSONList",
    # Type aliases - Messages
    "Message",
    "MessageList",
    "ToolDefinition",
    "ToolList",
    "ToolCall",
    "ToolCallList",
    # Type aliases - MCP
    "MCPServerConfig",
    "MCPServersConfig",
    "MCPSessionInfo",
    "MCPSessionsDict",
    "ToolServerMapping",
    # Type aliases - LLM
    "LLMResponse",
    "TokenUsage",
    "JSONSchema",
    # Type aliases - App-specific
    "CorrectionRecord",
    "CorrectionList",
]
