"""All persistent-memory operations use the official Hindsight client."""

import json
from datetime import datetime, timezone
from typing import Any

from hindsight_client import Hindsight

from models.deployment import Deployment
from utils.config import get_settings, missing_hindsight_settings


class HindsightConfigurationError(RuntimeError):
    """Raised when required Hindsight configuration is absent."""


def _client() -> tuple[Hindsight, str]:
    settings = get_settings()
    missing = missing_hindsight_settings(settings)
    if missing:
        raise HindsightConfigurationError("Missing required settings: " + ", ".join(missing))
    return Hindsight(
        base_url=settings.hindsight_base_url,
        api_key=settings.hindsight_api_key,
        timeout=12.0,
        max_attempts=1,
    ), settings.hindsight_bank_id


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict") and callable(value.dict):
        return value.dict()
    if hasattr(value, "__dict__"):
        return vars(value)
    return value


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def normalize_recall_results(response: Any) -> list[dict[str, Any]]:
    """Normalize RecallResult objects and mapping-based test/API responses."""
    results = _field(response, "results", [])
    if not isinstance(results, (list, tuple)):
        return []

    normalized = []
    for result in results:
        text = _field(result, "text", "")
        if not isinstance(text, str) or not text.strip():
            continue
        scores = _plain(_field(result, "scores")) or {}
        score = None
        if isinstance(scores, dict):
            score = scores.get("final", scores.get("reranker", scores.get("semantic")))
        else:
            score = _field(scores, "final", _field(scores, "reranker", _field(scores, "semantic")))
        normalized.append(
            {
                "id": _field(result, "id", "") or "",
                "text": text,
                "type": _field(result, "type", "") or "",
                "context": _field(result, "context", "") or "",
                "metadata": _field(result, "metadata", {}) or {},
                "score": score,
            }
        )
    return normalized


def recall_similar_deployments(query: str) -> list[dict[str, Any]]:
    if not query.strip():
        raise ValueError("A deployment memory query is required.")
    client, bank_id = _client()
    response = client.recall(bank_id=bank_id, query=query)
    return normalize_recall_results(response)


def retain_deployment_experience(experience: Deployment | dict[str, Any]) -> Any:
    payload = experience.to_dict() if isinstance(experience, Deployment) else dict(experience)
    payload.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    payload.setdefault("deployment_id", "")
    if not str(payload.get("deployment_id", "")).strip():
        raise ValueError("Deployment ID is required before storing an experience.")
    content = json.dumps(payload, ensure_ascii=True, indent=2, default=str)
    service = str(payload.get("service", "unknown service"))
    environment = str(payload.get("environment", "unknown environment"))
    context = f"Deployment {payload['deployment_id']} for {service} in {environment}"
    client, bank_id = _client()
    return client.retain(
        bank_id=bank_id,
        content=content,
        timestamp=datetime.now(timezone.utc),
        context=context,
        document_id=str(payload["deployment_id"]),
        metadata={
            "deployment_id": str(payload["deployment_id"]),
            "service": service,
            "environment": environment,
            "result": str(payload.get("result", "")),
        },
        tags=["deployment", "deployment-experience"],
    )


def check_hindsight_connection() -> tuple[bool, str]:
    try:
        recall_similar_deployments("DeployMind memory connection check")
        return True, "Hindsight is reachable."
    except Exception as exc:
        return False, str(exc)