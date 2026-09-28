"""Groq-backed deployment risk analysis."""

from typing import Any

from groq import Groq

from utils.config import get_settings
from utils.helpers import parse_json_response
from utils.prompts import SYSTEM_PROMPT, build_analysis_prompt


class LLMConfigurationError(RuntimeError):
    """Raised if Groq is not configured."""


def analyze_deployment(deployment: dict[str, Any], memories: list[dict[str, Any]]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.groq_api_key:
        raise LLMConfigurationError("GROQ_API_KEY is not configured.")
    client = Groq(api_key=settings.groq_api_key, timeout=30.0, max_retries=1)
    completion = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_analysis_prompt(deployment, memories)},
        ],
        temperature=0.2,
    )
    content = completion.choices[0].message.content
    if not content:
        raise ValueError("Groq returned an empty analysis.")
    return parse_json_response(content)