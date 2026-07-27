import asyncio
import json
from typing import Any, Optional

import json_repair

from agents.constants import JSON_REPAIR_TIMEOUT_SECONDS


class LLMJSONParsingError(Exception):
    def __init__(
        self,
        message: str,
        raw_response: str,
        validation_error: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.raw_response = raw_response
        self.validation_error = validation_error


def extract_json_candidate(raw: str) -> str:
    first_char = None
    start_idx = -1
    for index, char in enumerate(raw):
        if char in ("{", "["):
            start_idx = index
            first_char = char
            break

    json_str = raw
    if start_idx != -1:
        matching_char = "}" if first_char == "{" else "]"
        end_idx = raw.rfind(matching_char)
        if end_idx != -1 and end_idx > start_idx:
            json_str = raw[start_idx:end_idx + 1]
    return json_str


def strip_markdown_fence(raw: str) -> str:
    stripped = raw
    if stripped.startswith("```"):
        parts = stripped.split("\n", 1)
        if len(parts) > 1:
            stripped = parts[1]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        stripped = stripped.strip()
    return stripped


async def _repair_json(candidate: str) -> Any:
    def _repair(text):
        return json_repair.loads(text)

    return await asyncio.wait_for(
        asyncio.to_thread(_repair, candidate),
        timeout=JSON_REPAIR_TIMEOUT_SECONDS,
    )


async def parse_llm_json_response(raw: str, response_schema: Optional[Any] = None) -> dict:
    raw = raw.strip()
    json_str = extract_json_candidate(raw)
    parsed = None
    try:
        parsed = json.loads(json_str, strict=False)
    except json.JSONDecodeError:
        stripped = strip_markdown_fence(raw)
        try:
            parsed = json.loads(stripped, strict=False)
        except json.JSONDecodeError as error:
            try:
                repaired = await _repair_json(json_str)
                if isinstance(repaired, (dict, list)):
                    parsed = repaired
                else:
                    repaired_stripped = await _repair_json(stripped)
                    if isinstance(repaired_stripped, (dict, list)):
                        parsed = repaired_stripped
            except asyncio.TimeoutError:
                print(f"[json_repair failed]: Timeout after {JSON_REPAIR_TIMEOUT_SECONDS}s")
            except Exception as repair_err:
                print(f"[json_repair failed]: {repair_err}")

            if parsed is None:
                print(f"[call_llm_json parsing error] Failed to parse: {error}")
                print(f"[call_llm_json raw output]: {raw[:500]}...")
                raise LLMJSONParsingError(
                    f"Failed to parse JSON response: {error}",
                    raw_response=raw,
                )

    if response_schema is not None:
        try:
            validated_obj = response_schema.model_validate(parsed)
            return validated_obj.model_dump(by_alias=True)
        except Exception as validation_error:
            print(f"[call_llm_json schema validation error]: {validation_error}")
            raw_parsed = json.dumps(parsed, ensure_ascii=False) if parsed is not None else raw
            raise LLMJSONParsingError(
                f"Schema validation failed: {validation_error}",
                raw_response=raw_parsed,
                validation_error=validation_error,
            )

    return parsed
