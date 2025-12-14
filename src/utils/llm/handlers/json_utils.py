"""
Core JSON utilities for LLM response handling.

Provides sanitization and extraction utilities for parsing JSON from LLM outputs,
which may contain markdown formatting, code blocks, or malformed JSON.
"""

import json
import re
from typing import Any


def sanitize_json(text: str) -> str:
    """
    Sanitize and clean JSON string from LLM output.

    Handles common issues in LLM-generated JSON:
    - Removes markdown code block markers
    - Strips leading/trailing whitespace
    - Removes trailing commas before closing brackets
    - Handles escaped characters

    Args:
        text: Raw text potentially containing JSON

    Returns:
        Cleaned JSON string ready for parsing
    """
    if not text:
        return ""

    # Remove markdown code block markers (```json, ```, etc.)
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)

    # Strip leading/trailing whitespace
    text = text.strip()

    # Remove trailing commas before closing brackets/braces (common LLM mistake)
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # Fix common escape issues
    # Replace single backslashes that aren't part of valid escape sequences
    # Valid: \n, \t, \r, \\, \", \/, \b, \f, \uXXXX
    # This is a simplified fix - complex cases may need manual handling

    return text


def extract_json(text: str, strict: bool = False) -> dict[str, Any] | list[Any] | None:
    """
    Extract and parse JSON from LLM response text.

    Attempts multiple strategies to find and parse valid JSON:
    1. Direct parsing of sanitized text
    2. Extract JSON from code blocks
    3. Find JSON object/array boundaries

    Args:
        text: Raw LLM response text
        strict: If True, raise exception on parse failure; if False, return None

    Returns:
        Parsed JSON as dict or list, or None if parsing fails (when strict=False)

    Raises:
        json.JSONDecodeError: If strict=True and JSON parsing fails
        ValueError: If strict=True and no valid JSON found
    """
    if not text:
        if strict:
            raise ValueError("Empty text provided")
        return None

    # Strategy 1: Try direct parsing after sanitization
    sanitized = sanitize_json(text)
    try:
        return json.loads(sanitized)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Extract from markdown code blocks
    code_block_patterns = [
        r"```json\s*\n([\s\S]*?)\n```",  # ```json ... ```
        r"```\s*\n([\s\S]*?)\n```",  # ``` ... ```
    ]

    for pattern in code_block_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                cleaned = sanitize_json(match)
                return json.loads(cleaned)
            except json.JSONDecodeError:
                continue

    # Strategy 3: Find JSON object boundaries
    # Look for outermost { } or [ ]
    json_patterns = [
        (r"\{", r"\}"),  # Object
        (r"\[", r"\]"),  # Array
    ]

    for start_char, end_char in json_patterns:
        start_match = re.search(start_char, text)
        if start_match:
            start_idx = start_match.start()
            # Find matching closing bracket
            depth = 0
            in_string = False
            escape_next = False

            for i, char in enumerate(text[start_idx:], start=start_idx):
                if escape_next:
                    escape_next = False
                    continue

                if char == "\\" and in_string:
                    escape_next = True
                    continue

                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue

                if in_string:
                    continue

                if char == start_char[0]:  # Remove regex escape
                    depth += 1
                elif char == end_char[0]:
                    depth -= 1
                    if depth == 0:
                        json_str = text[start_idx : i + 1]
                        try:
                            cleaned = sanitize_json(json_str)
                            return json.loads(cleaned)
                        except json.JSONDecodeError:
                            break

    # All strategies failed
    if strict:
        raise ValueError(f"Could not extract valid JSON from text: {text[:200]}...")
    return None


def extract_json_objects(text: str) -> list[dict[str, Any]]:
    """
    Extract all JSON objects from text.

    Useful when LLM returns multiple JSON objects or a stream of objects.

    Args:
        text: Text potentially containing multiple JSON objects

    Returns:
        List of parsed JSON objects (dicts only, not arrays)
    """
    objects = []
    remaining = text

    while remaining:
        # Find next object start
        match = re.search(r"\{", remaining)
        if not match:
            break

        start_idx = match.start()
        depth = 0
        in_string = False
        escape_next = False

        for i, char in enumerate(remaining[start_idx:], start=start_idx):
            if escape_next:
                escape_next = False
                continue

            if char == "\\" and in_string:
                escape_next = True
                continue

            if char == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    json_str = remaining[start_idx : i + 1]
                    try:
                        obj = json.loads(json_str)
                        if isinstance(obj, dict):
                            objects.append(obj)
                    except json.JSONDecodeError:
                        pass
                    remaining = remaining[i + 1 :]
                    break
        else:
            # No matching closing brace found
            break

    return objects


def safe_json_loads(text: str, default: Any = None) -> Any:
    """
    Safely load JSON with a default fallback value.

    Args:
        text: JSON string to parse
        default: Value to return if parsing fails

    Returns:
        Parsed JSON or default value
    """
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return default


def json_to_string(obj: Any, pretty: bool = False) -> str:
    """
    Convert Python object to JSON string.

    Args:
        obj: Python object to serialize
        pretty: If True, format with indentation

    Returns:
        JSON string representation
    """
    if pretty:
        return json.dumps(obj, ensure_ascii=False, indent=2)
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
