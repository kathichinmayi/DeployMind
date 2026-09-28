"""Small presentation and response parsing helpers."""

import json
from typing import Any


def parse_json_response(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lstrip().startswith("json"):
            text = text.lstrip()[4:].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("The AI returned a malformed response. Please retry the analysis.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("The AI response must be a JSON object.")
    return parsed


def parse_memory_text(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_memory_impact_facts(memories: list[dict[str, Any]]) -> dict[str, str]:
    """Select verbatim DEP-025 evidence snippets for the Memory Impact Demo."""
    facts: dict[str, str] = {}
    for memory in memories:
        text = memory.get("text", "")
        if not isinstance(text, str):
            continue
        parts = [part.strip() for part in text.split(" | ") if part.strip()]
        lowered = text.lower()
        if "DEP-025" in text:
            facts.setdefault("deployment_id", "DEP-025")
        if "database connection timeout" in lowered:
            facts.setdefault("previous_failure", parts[0])
        for part in parts:
            part_lower = part.lower()
            if "connection pool" in part_lower and ("too small" in part_lower or "undersized" in part_lower):
                facts.setdefault("previous_cause", part)
            if "increased from 10 to 30" in part_lower:
                facts.setdefault("previous_fix", part)
    return facts