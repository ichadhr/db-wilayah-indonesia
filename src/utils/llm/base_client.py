"""
LLM Client - Reusable LiteLLM wrapper with JSON sanitization.

This module provides a unified interface for LLM calls with:
- Streaming support
- JSON response sanitization
- Token counting
- Error handling
"""

import json
import re
from typing import Any

import litellm
from litellm.utils import token_counter

from utils.llm.config import LLMConfig


class LLMClient:
    """Reusable LiteLLM wrapper with JSON sanitization."""

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
            s = s.replace('\n', '\\n')
            s = s.replace('\r', '\\r')
            s = s.replace('\t', '\\t')
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
        stream: bool = True,
        verbose: bool = True
    ) -> dict[str, Any]:
        """
        Call LLM for structured JSON output.
        
        Args:
            system_prompt: System role definition
            user_prompt: User query with data
            output_schema: JSON schema for structured output (optional)
            stream: Whether to stream the response
            verbose: Whether to print progress
            
        Returns:
            Parsed JSON response
        """
        llm_params = self.config.get_litellm_params()
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        if output_schema:
            messages.append({
                "role": "user",
                "content": f"Output must be valid JSON matching this schema:\n{json.dumps(output_schema, indent=2)}"
            })
        
        if verbose:
            print(f"\nCalling LLM: {llm_params['model']}")
            print(f"Temperature: {llm_params['temperature']}, Max Tokens: {llm_params.get('max_tokens', 'default')}")

        # Calculate input tokens
        input_tokens = None
        try:
            input_tokens = token_counter(model=llm_params['model'], messages=messages)
            if verbose:
                print(f"Input tokens: {input_tokens}")
        except Exception as e:
            if verbose:
                print(f"Could not calculate input tokens: {e}")

        content = ""
        try:
            response = litellm.completion(
                messages=messages,
                stream=stream,
                **llm_params
            )

            if stream:
                for chunk in response:
                    delta = getattr(getattr(chunk, 'choices', [{}])[0], 'delta', {})
                    delta_content = delta.get('content', '')
                    if delta_content:
                        if verbose:
                            print(delta_content, end='', flush=True)
                        content += delta_content
            else:
                content = response.choices[0].message.content

            if not isinstance(content, str):
                raise ValueError(f"Unexpected response content type: {type(content)}")

            # Extract and sanitize JSON
            content = self.extract_json(content)
            content = self.sanitize_json(content)
            result = json.loads(content)

            if verbose:
                print(f"\n[OK] LLM call successful")
                try:
                    output_tokens = token_counter(model=llm_params['model'], text=content)
                    total_tokens = (input_tokens + output_tokens) if input_tokens else output_tokens
                    print(f"  Tokens used: {total_tokens} (input: {input_tokens or 'unknown'}, output: {output_tokens})")
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
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
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
