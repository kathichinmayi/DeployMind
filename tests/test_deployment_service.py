from models.deployment import Deployment, parse_changed_files, validate_deployment
from services.deployment_service import build_recall_query, format_deployment_experience, validate_result_experience


def test_deployment_validation_requires_identifiers_and_summary():
    deployment = Deployment("", "", "Unknown")
    errors = validate_deployment(deployment)
    assert len(errors) == 4
    assert "Deployment ID is required." in errors
    assert "Choose a valid environment." in errors


def test_recall_query_contains_change_context():
    deployment = Deployment("DEP-042", "Payment API", "Production", ["database.yml"], "Update pool size")
    query = build_recall_query(deployment)
    assert "Payment API" in query
    assert "database.yml" in query
    assert "Update pool size" in query


def test_structured_experience_includes_all_resolution_fields():
    experience = format_deployment_experience(
        {
            "deployment_id": "DEP-025",
            "service": "Payment API",
            "environment": "Production",
            "changed_files": "database.yml\nconfig.env",
            "change_summary": "Updated database configuration",
            "result": "FAILED",
            "error": "Database connection timeout",
            "root_cause": "Pool too small",
            "fixes_attempted": "Restarted worker",
            "successful_fix": "Pool size 30",
            "resolution_notes": "Verified after redeploy",
            "lessons_learned": "Validate pool settings",
        }
    )
    assert experience["changed_files"] == ["database.yml", "config.env"]
    assert experience["timestamp"]
    assert experience["successful_fix"] == "Pool size 30"
    assert validate_result_experience(Deployment("D", "S", "Production", [], "change", result="FAILED")) == []


def test_changed_file_parser_accepts_commas_and_lines():
    assert parse_changed_files("a.yml, b.env\nc.py") == ["a.yml", "b.env", "c.py"]