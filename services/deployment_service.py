"""Deployment validation, recall query, and experience formatting."""

from datetime import datetime, timezone
from typing import Any

from models.deployment import Deployment, parse_changed_files, validate_deployment


def build_recall_query(deployment: Deployment) -> str:
    files = ", ".join(deployment.changed_files) or "no changed files listed"
    return (
        f"Deployment incident history for {deployment.service} in {deployment.environment}. "
        f"Changed files: {files}. Change: {deployment.change_summary}. "
        f"Build: {deployment.build_status}. Tests: {deployment.test_status}. Logs: {deployment.logs}"
    )


def format_deployment_experience(values: dict[str, Any]) -> dict[str, Any]:
    """Return the complete, timestamped persistent experience payload."""
    payload = dict(values)
    payload["changed_files"] = parse_changed_files(payload.get("changed_files", []))
    payload["timestamp"] = payload.get("timestamp") or datetime.now(timezone.utc).isoformat()
    payload.setdefault("result", "")
    payload.setdefault("error", "")
    payload.setdefault("root_cause", "")
    payload.setdefault("fixes_attempted", "")
    payload.setdefault("successful_fix", "")
    payload.setdefault("resolution_notes", "")
    payload.setdefault("lessons_learned", "")
    return payload


def validate_result_experience(deployment: Deployment) -> list[str]:
    errors = validate_deployment(deployment)
    if deployment.result not in {"SUCCESS", "FAILED"}:
        errors.append("Choose SUCCESS or FAILED as the deployment result.")
    return errors