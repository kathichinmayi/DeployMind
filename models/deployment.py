"""Deployment data and validation helpers."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Deployment:
    deployment_id: str
    service: str
    environment: str
    changed_files: list[str] = field(default_factory=list)
    change_summary: str = ""
    build_status: str = "Not Run"
    test_status: str = "Not Run"
    logs: str = ""
    result: str = ""
    error: str = ""
    root_cause: str = ""
    fixes_attempted: str = ""
    successful_fix: str = ""
    resolution_notes: str = ""
    lessons_learned: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_deployment(deployment: Deployment, require_summary: bool = True) -> list[str]:
    errors = []
    if not deployment.deployment_id.strip():
        errors.append("Deployment ID is required.")
    if not deployment.service.strip():
        errors.append("Application / Service is required.")
    if deployment.environment not in {"Production", "Staging", "Development"}:
        errors.append("Choose a valid environment.")
    if require_summary and not deployment.change_summary.strip():
        errors.append("Change Summary is required.")
    return errors


def parse_changed_files(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return [item.strip() for item in value if item.strip()]
    return [line.strip() for line in value.replace(",", "\n").splitlines() if line.strip()]