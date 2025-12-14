# LLM Utilities Module

A reusable LLM toolkit with MCP (Model Context Protocol) integration for tool-augmented AI workflows.

## Overview

This module provides a unified interface for LLM calls with:

- **LiteLLM Integration** - Support for multiple LLM providers (OpenAI, Anthropic, Mistral, etc.)
- **MCP Tool Support** - Integrate external tools via stdio or HTTP/SSE transports
- **JSON Sanitization** - Handle malformed JSON from LLM outputs
- **Batch Processing** - Efficient multi-call processing with shared sessions
- **Structured Output** - JSON schema validation for responses

## Folder Structure

```
src/utils/llm/
├── __init__.py          # Exports LLMClient, LLMConfig, type aliases
├── client.py            # Main LLMClient class
├── config.py            # LLMConfig dataclass and load_config()
├── types.py             # Type aliases for the module
├── handlers/
│   ├── __init__.py      # Exports json_utils functions
│   └── json_utils.py    # Core JSON utilities (sanitize, extract)
├── mcp/
│   ├── __init__.py      # Exports MCPClient, config, executor
│   ├── client.py        # MCPClient class
│   ├── config.py        # MCP configuration loading
│   ├── executor.py      # Tool execution logic
│   └── mcp.json         # MCP server configurations
├── prompt/
│   └── *.md             # Prompt templates
└── schemas/
    ├── __init__.py      # Exports from json/ and md/ submodules
    ├── postal_correction.py  # App-specific schema
    ├── json/
    │   ├── __init__.py
    │   └── json_schema.py    # JSON output formatting
    └── md/
        ├── __init__.py
        └── markdown_schema.py  # Markdown report generation
```

## Quick Start

### Basic LLM Call

```python
from utils.llm import LLMClient, LLMConfig, load_config

# Load config from llm_config.yaml
config = load_config()

# Or create config manually
config = LLMConfig(
    model="mistral/mistral-large-latest",
    temperature=0.1,
    max_tokens=4096,
)

# Initialize client
llm = LLMClient(config)

# Simple call
result = llm.call_llm(
    system_prompt="You are a helpful assistant.",
    user_prompt="What is the capital of Indonesia?",
    output_schema={"type": "object", "properties": {"answer": {"type": "string"}}},
)
print(result["answer"])  # "Jakarta"
```

### LLM Call with MCP Tools

```python
# Call with specific MCP servers
result = llm.call_llm(
    system_prompt="You are a data analyst with access to tools.",
    user_prompt="Search for latest Indonesia administrative data.",
    output_schema=schema,
    mcp=["databeak"],  # Use databeak MCP server
)

# Call with all configured MCP servers
result = llm.call_llm(..., mcp=True)

# Call with multiple servers
result = llm.call_llm(..., mcp=["exa", "databeak"])
```

### Batch Processing (Recommended for Multiple Calls)

When processing multiple LLM calls, use `call_llm_batch()` to avoid event loop issues and improve efficiency:

```python
# Prepare batch calls
calls = [
    {
        "system_prompt": "You are a data analyst.",
        "user_prompt": "Analyze batch 1...",
        "output_schema": schema,
    },
    {
        "system_prompt": "You are a data analyst.",
        "user_prompt": "Analyze batch 2...",
        "output_schema": schema,
    },
    {
        "system_prompt": "You are a data analyst.",
        "user_prompt": "Analyze batch 3...",
        "output_schema": schema,
    },
]

# Process all calls with shared MCP sessions
results = llm.call_llm_batch(calls, mcp=["databeak"], verbose=True)

# Results are in same order as calls
for i, result in enumerate(results):
    print(f"Batch {i+1}: {result}")
```

**Why use `call_llm_batch()`?**

| Issue | Sequential `call_llm()` | `call_llm_batch()` |
|-------|------------------------|-------------------|
| Event loop | New loop per call (causes errors) | Single shared loop |
| MCP stdio server | Spawns new process per call | Spawns once, reused |
| MCP HTTP connection | New connection per call | Single connection |
| Performance | Slow (overhead per call) | Fast (shared resources) |

## Configuration

### LLMConfig

```python
from utils.llm.config import LLMConfig

config = LLMConfig(
    # Model settings
    model="mistral/mistral-large-latest",
    temperature=0.1,
    max_tokens=4096,
    
    # API settings (optional - uses env vars by default)
    api_key="your-api-key",
    api_base="https://api.mistral.ai/v1",
    
    # Confidence thresholds (app-specific)
    confidence_threshold_auto_apply=0.85,
    confidence_threshold_flag=0.70,
    
    # Output directories
    output_log_dir=Path("log"),
    output_markdown_dir=Path("docs"),
    output_json_dir=Path("output"),
)
```

### Loading from YAML

Create `llm_config.yaml`:

```yaml
model: mistral/mistral-large-latest
temperature: 0.1
max_tokens: 4096
confidence_threshold_auto_apply: 0.85
confidence_threshold_flag: 0.70
```

Load it:

```python
from utils.llm.config import load_config

config = load_config()  # Loads from llm_config.yaml
config = load_config("custom_config.yaml")  # Custom path
```

## MCP Integration

### MCP Server Configuration

Configure MCP servers in `mcp/mcp.json`:

```json
{
  "mcpServers": {
    "databeak": {
      "transport": "stdio",
      "command": "uv",
      "args": ["--directory", "D:\\path\\to\\databeak", "run", "databeak"],
      "env": {}
    },
    "exa": {
      "transport": "http",
      "url": "https://mcp.exa.ai/mcp?tools=web_search_exa",
      "headers": {
        "Authorization": "Bearer ${EXA_API_KEY}"
      }
    }
  }
}
```

### Transport Types

| Transport | Use Case | Example |
|-----------|----------|---------|
| `stdio` | Local tools, subprocess-based | databeak, filesystem |
| `http` | Remote HTTP APIs | REST-based MCP servers |
| `sse` | Server-Sent Events | Streaming MCP servers |

### Environment Variables

Use `${VAR_NAME}` syntax in mcp.json for secrets:

```json
{
  "headers": {
    "Authorization": "Bearer ${EXA_API_KEY}"
  }
}
```

### Available MCP Functions

```python
from utils.llm.mcp import (
    MCPClient,
    get_available_servers,
    load_mcp_config,
    get_server_transport,
)

# List available servers
servers = get_available_servers()  # ["databeak", "exa"]

# Load specific servers
config = load_mcp_config(servers=["databeak"])

# Use MCPClient directly (advanced)
async with MCPClient(["databeak"]) as client:
    tools = await client.load_tools()
    result = await client.call_tool("health_check", {})
```

## JSON Utilities

### Sanitizing LLM Output

LLMs sometimes produce malformed JSON. Use the handlers:

```python
from utils.llm.handlers import sanitize_json, extract_json

# Extract JSON from markdown code blocks
raw_response = '''Here's the data:
```json
{"name": "test", "value": 123}
```
'''
json_str = extract_json(raw_response)

# Sanitize control characters in JSON strings
dirty_json = '{"text": "line1\nline2"}'  # Raw newline (invalid)
clean_json = sanitize_json(dirty_json)   # Escaped newline (valid)

# Parse with fallback
from utils.llm.handlers import safe_json_loads
data = safe_json_loads(json_str, default={})
```

## Type Aliases

The module provides type aliases for better code clarity:

```python
from utils.llm import (
    # JSON types
    JSONDict,
    JSONList,
    JSONValue,
    
    # Message types
    Message,
    MessageList,
    
    # Tool types
    ToolDefinition,
    ToolList,
    ToolCall,
    
    # MCP types
    MCPServerConfig,
    MCPSessionInfo,
)
```

## Schemas Module

### JSON Output Schema

```python
from utils.llm.schemas.json import (
    build_json_output,
    save_json_output,
    validate_correction,
    export_corrections_to_csv,
)

# Build structured output
output = build_json_output(
    province="aceh",
    corrections=corrections_list,
    confidence_threshold=0.85,
)

# Save to file
save_json_output("aceh", corrections, output_dir=Path("output"))
```

### Markdown Reports

```python
from utils.llm.schemas.md import (
    generate_markdown_report,
    save_markdown_report,
)

# Generate report
markdown = generate_markdown_report(
    province="aceh",
    corrections=corrections,
    unmapped_detail=unmapped_df,
)

# Save to file
save_markdown_report("aceh", corrections, output_dir=Path("docs"))
```

## Error Handling

### Common Issues

#### 1. Event Loop Error (Multiple Calls)

```
RuntimeError: <Queue at 0x...> is bound to a different event loop
```

**Solution:** Use `call_llm_batch()` instead of multiple `call_llm()` calls.

#### 2. MCP Session Cleanup on CTRL-C

The module handles CTRL-C gracefully:

```python
try:
    result = llm.call_llm(..., mcp=["databeak"])
except KeyboardInterrupt:
    # Sessions are automatically cleaned up
    print("Interrupted")
```

#### 3. JSON Parse Errors

```python
try:
    result = llm.call_llm(...)
except json.JSONDecodeError as e:
    print(f"Failed to parse LLM response: {e}")
    # The client already attempts extraction and sanitization
```

## Examples

### Example 1: Data Analysis with MCP Tools

```python
from utils.llm import LLMClient, load_config

config = load_config()
llm = LLMClient(config)

result = llm.call_llm(
    system_prompt="""You are a data analyst with access to DataBeak tools.
    Use the tools to load and analyze CSV data.""",
    user_prompt="Load the sales data and calculate total revenue by region.",
    output_schema={
        "type": "object",
        "properties": {
            "analysis": {"type": "string"},
            "total_revenue": {"type": "number"},
            "by_region": {"type": "object"},
        },
    },
    mcp=["databeak"],
)
```

### Example 2: Batch Processing Pipeline

```python
from utils.llm import LLMClient, load_config
from tqdm import tqdm

config = load_config()
llm = LLMClient(config)

# Prepare batches
batches = [{"id": i, "data": chunk} for i, chunk in enumerate(data_chunks)]

# Build calls
calls = []
for batch in batches:
    calls.append({
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": f"Process this data:\n{batch['data']}",
        "output_schema": OUTPUT_SCHEMA,
    })

# Process all at once
print(f"Processing {len(calls)} batches...")
results = llm.call_llm_batch(calls, mcp=["databeak"], verbose=True)

# Handle results
for batch, result in zip(batches, results):
    print(f"Batch {batch['id']}: {len(result.get('items', []))} items")
```

### Example 3: Web Search with Exa

```python
result = llm.call_llm(
    system_prompt="You are a research assistant with web search capabilities.",
    user_prompt="Find the latest news about Indonesia administrative changes in 2024.",
    output_schema={
        "type": "object",
        "properties": {
            "findings": {"type": "array", "items": {"type": "string"}},
            "sources": {"type": "array", "items": {"type": "string"}},
        },
    },
    mcp=["exa"],
)
```

## Best Practices

### 1. Use `call_llm_batch()` for Multiple Calls

❌ **Don't** - Sequential calls cause event loop issues:

```python
# BAD: Creates new event loop per call, causes LiteLLM queue errors
results = []
for batch in batches:
    result = llm.call_llm(system, user, schema, mcp=["databeak"])
    results.append(result)
```

✅ **Do** - Batch calls share event loop and MCP sessions:

```python
# GOOD: Single event loop, shared MCP sessions
calls = [{"system_prompt": s, "user_prompt": u, "output_schema": schema} for ...]
results = llm.call_llm_batch(calls, mcp=["databeak"])
```

### 2. Specify Only Needed MCP Servers

❌ **Don't** - Load all servers when you only need one:

```python
# BAD: Loads all servers (slow, unnecessary connections)
result = llm.call_llm(..., mcp=True)
```

✅ **Do** - Specify only the servers you need:

```python
# GOOD: Only loads databeak
result = llm.call_llm(..., mcp=["databeak"])

# GOOD: Multiple specific servers
result = llm.call_llm(..., mcp=["databeak", "exa"])
```

### 3. Use Structured Output Schemas

❌ **Don't** - Request unstructured responses:

```python
# BAD: No schema, unpredictable output format
result = llm.call_llm(system, "Give me the data", output_schema=None)
```

✅ **Do** - Define explicit JSON schemas:

```python
# GOOD: Predictable, validated output
schema = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {"type": "string"}},
        "count": {"type": "integer"},
    },
    "required": ["items", "count"],
}
result = llm.call_llm(system, user, output_schema=schema)
```

### 4. Handle Errors Gracefully

❌ **Don't** - Ignore potential failures:

```python
# BAD: No error handling
result = llm.call_llm(...)
process(result["data"])  # May crash if LLM fails
```

✅ **Do** - Wrap calls with proper error handling:

```python
# GOOD: Handle errors gracefully
try:
    result = llm.call_llm(...)
    if "data" in result:
        process(result["data"])
    else:
        logger.warning(f"Unexpected response: {result}")
except json.JSONDecodeError as e:
    logger.error(f"Failed to parse LLM response: {e}")
except KeyboardInterrupt:
    logger.info("Interrupted by user")
    raise
except Exception as e:
    logger.error(f"LLM call failed: {e}")
```

### 5. Keep Prompts Focused and Clear

❌ **Don't** - Vague or overly complex prompts:

```python
# BAD: Vague instructions
system = "You are helpful."
user = "Do something with this data."
```

✅ **Do** - Clear, specific instructions with examples:

```python
# GOOD: Clear role, specific task, example output
system = """You are a data extraction specialist.
Extract administrative name changes from Indonesian government records.
Focus on: kabupaten_kota, kecamatan, kelurahan_desa fields."""

user = """Extract changes from this record:
| Field | Value |
|-------|-------|
| keterangan | Pemekaran dari Kec. Lama menjadi Kec. Baru |

Return JSON with: field, old_name, new_name, confidence (0-1)."""
```

### 6. Use Environment Variables for Secrets

❌ **Don't** - Hardcode API keys:

```json
{
  "headers": {
    "Authorization": "Bearer sk-abc123..."
  }
}
```

✅ **Do** - Use environment variable substitution:

```json
{
  "headers": {
    "Authorization": "Bearer ${EXA_API_KEY}"
  }
}
```

### 7. Set Appropriate Temperature

| Use Case | Temperature | Reason |
|----------|-------------|--------|
| Data extraction | 0.0 - 0.1 | Deterministic, consistent |
| Analysis | 0.1 - 0.3 | Slight variation OK |
| Creative tasks | 0.7 - 1.0 | More diverse outputs |

```python
# For data extraction (deterministic)
config = LLMConfig(model="...", temperature=0.1)

# For creative tasks
config = LLMConfig(model="...", temperature=0.8)
```

### 8. Batch Size Optimization

| Data Size | Recommended Batch Size | Reason |
|-----------|----------------------|--------|
| < 100 rows | 10-20 | Fewer API calls |
| 100-1000 rows | 5-10 | Balance speed/context |
| > 1000 rows | 3-5 | Avoid context overflow |

```python
# Adjust based on data complexity
BATCH_SIZE = 5  # For complex records
BATCH_SIZE = 15  # For simple records
```

### 9. Reuse LLMClient Instance

❌ **Don't** - Create new client per call:

```python
# BAD: Creates new client each time
for batch in batches:
    llm = LLMClient(config)  # Wasteful
    result = llm.call_llm(...)
```

✅ **Do** - Reuse single client instance:

```python
# GOOD: Single client, reused
llm = LLMClient(config)
for batch in batches:
    result = llm.call_llm(...)
```

### 10. Log and Monitor Token Usage

```python
# Enable verbose mode to track tokens
result = llm.call_llm(..., verbose=True)

# Output shows:
# [MCP] Tokens this call: prompt=15763, completion=518
# [MCP] Total tokens: prompt=15763, completion=518, total=16281
```

### Summary Checklist

- [ ] Use `call_llm_batch()` for multiple calls
- [ ] Specify only needed MCP servers
- [ ] Define JSON output schemas
- [ ] Handle errors gracefully
- [ ] Write clear, specific prompts
- [ ] Use environment variables for secrets
- [ ] Set appropriate temperature for task
- [ ] Optimize batch sizes
- [ ] Reuse LLMClient instance
- [ ] Monitor token usage

## API Reference

### LLMClient

| Method | Description |
|--------|-------------|
| `call_llm(system, user, schema, mcp, stream, verbose)` | Single LLM call |
| `call_llm_batch(calls, mcp, verbose)` | Batch LLM calls with shared sessions |
| `sanitize_json(content)` | Escape control characters in JSON |
| `extract_json(content)` | Extract JSON from markdown blocks |

### MCPClient

| Method | Description |
|--------|-------------|
| `load_tools()` | Load tools from configured servers |
| `call_tool(name, arguments)` | Execute a tool |
| `close()` | Close all sessions |

### Config Functions

| Function | Description |
|----------|-------------|
| `load_config(path)` | Load LLMConfig from YAML |
| `load_mcp_config(servers)` | Load MCP server configs |
| `get_available_servers()` | List configured MCP servers |

## Changelog

### 2025-12-14 (Latest)

- **Refactored folder structure**
  - Renamed `base_client.py` → `client.py`
  - Created `types.py` for centralized type aliases
  - Created `mcp/config.py` for MCP configuration loading
  - Created `mcp/executor.py` for tool execution logic
  - Moved `handlers/json_handler.py` → `schemas/json/json_schema.py`
  - Moved `handlers/markdown_handler.py` → `schemas/md/markdown_schema.py`
  - Created `handlers/json_utils.py` for core JSON utilities

- **Added `call_llm_batch()` method**
  - Process multiple LLM calls in single event loop
  - Shared MCP sessions across all calls
  - Fixes LiteLLM `LoggingWorker` event loop binding issue

- **Improved MCP session cleanup**
  - Use `AsyncExitStack` for proper context manager cleanup
  - Graceful handling of CTRL-C interruption
  - Automatic stdio subprocess termination

- **Updated imports across project**
  - All scripts updated to use new module paths
  - Added `# noqa: E402` for post-sys.path imports

## License

Part of the db-wilayah-indonesia project.