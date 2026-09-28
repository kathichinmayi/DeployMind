from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from services import hindsight_service, llm_service
from services.llm_service import LLMConfigurationError
from utils.helpers import build_memory_impact_facts, parse_json_response
from utils.prompts import build_analysis_prompt


def test_recall_normalizer_uses_actual_response_fields():
    response = SimpleNamespace(
        results=[
            SimpleNamespace(
                id="memory-1",
                text="Database connection timeout",
                context="DEP-025, Payment API",
                scores=SimpleNamespace(final=0.91),
                metadata={"deployment_id": "DEP-025"},
                type="experience",
                occurred_start=None,
            )
        ]
    )
    result = hindsight_service.normalize_recall_results(response)
    assert result == [
        {
            "id": "memory-1",
            "text": "Database connection timeout",
            "type": "experience",
            "context": "DEP-025, Payment API",
            "metadata": {"deployment_id": "DEP-025"},
            "score": 0.91,
        }
    ]


def test_normalizer_handles_empty_results_without_fabrication():
    assert hindsight_service.normalize_recall_results({"results": []}) == []
    assert hindsight_service.normalize_recall_results({"results": None}) == []


def test_analysis_prompt_explicitly_represents_no_memory():
    prompt = build_analysis_prompt({"deployment_id": "DEP-042"}, [])
    assert '"historical_memories": []' in prompt
    assert "do not infer incidents" in prompt


def test_memory_impact_facts_preserve_only_recalled_dep025_snippets():
    memories = [
        {
            "text": "Deployment DEP-025 for Payment API failed due to a database connection timeout. | "
            "When: 2026-09-28 | Database connection pool size was too small."
        },
        {"text": "The connection pool size was increased from 10 to 30 to fix the deployment failure. | When: 2026-09-28"},
    ]
    facts = build_memory_impact_facts(memories)
    assert facts == {
        "deployment_id": "DEP-025",
        "previous_failure": "Deployment DEP-025 for Payment API failed due to a database connection timeout.",
        "previous_cause": "Database connection pool size was too small.",
        "previous_fix": "The connection pool size was increased from 10 to 30 to fix the deployment failure.",
    }


def test_memory_impact_facts_do_not_create_missing_fields():
    assert build_memory_impact_facts([{"text": "A different deployment had an unrelated issue."}]) == {}


def test_malformed_llm_json_is_reported():
    with pytest.raises(ValueError, match="malformed response"):
        parse_json_response("not json")


def test_missing_groq_key_fails_clearly(monkeypatch):
    monkeypatch.setattr(
        llm_service,
        "get_settings",
        lambda: SimpleNamespace(groq_api_key="", groq_model="model"),
    )
    with pytest.raises(LLMConfigurationError, match="GROQ_API_KEY"):
        llm_service.analyze_deployment({}, [])


def test_recall_calls_official_sdk_and_propagates_api_errors(monkeypatch):
    client = MagicMock()
    client.recall.side_effect = TimeoutError("request timed out")
    monkeypatch.setattr(hindsight_service, "_client", lambda: (client, "bank"))
    with pytest.raises(TimeoutError, match="timed out"):
        hindsight_service.recall_similar_deployments("database timeout")


def test_recall_uses_unfiltered_sdk_call_and_normalizes_result_objects(monkeypatch):
    result = SimpleNamespace(
        id="memory-1",
        text="Database connection timeout",
        type="world",
        context="DEP-025, Payment API",
        metadata={"deployment_id": "DEP-025"},
    )
    client = MagicMock()
    client.recall.return_value = SimpleNamespace(results=[result])
    monkeypatch.setattr(hindsight_service, "_client", lambda: (client, "deploymind"))

    memories = hindsight_service.recall_similar_deployments("database timeout")

    client.recall.assert_called_once_with(bank_id="deploymind", query="database timeout")
    assert memories == [
        {
            "id": "memory-1",
            "text": "Database connection timeout",
            "type": "world",
            "context": "DEP-025, Payment API",
            "metadata": {"deployment_id": "DEP-025"},
            "score": None,
        }
    ]


def test_retain_uses_official_sdk_with_stable_document_id(monkeypatch):
    client = MagicMock()
    client.retain.return_value = SimpleNamespace(success=True)
    monkeypatch.setattr(hindsight_service, "_client", lambda: (client, "bank"))
    result = hindsight_service.retain_deployment_experience(
        {"deployment_id": "DEP-025", "service": "Payment API", "result": "FAILED"}
    )
    assert result.success is True
    kwargs = client.retain.call_args.kwargs
    assert kwargs["bank_id"] == "bank"
    assert kwargs["document_id"] == "DEP-025"
    assert "DEP-025" in kwargs["content"]