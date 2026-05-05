import json

import pytest
from fastapi.testclient import TestClient

import backend.reliability_graph.api as api_module
import backend.reliability_graph.pipeline.engine as engine_module
from backend.reliability_graph.providers.base import GenerateResponse
from backend.reliability_graph.schemas import RunCreate
from backend.reliability_graph.storage import Storage
from backend.reliability_graph.verifier import FixtureEntailmentVerifier


def test_run_event_stream_completes_without_shadowing_run_state(tmp_path, monkeypatch):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()
    monkeypatch.setattr(api_module, "storage", storage)
    monkeypatch.setattr(api_module, "entailment_verifier", FixtureEntailmentVerifier())
    monkeypatch.setattr(engine_module, "build_provider", lambda _provider, _api_key: FakeProvider())
    monkeypatch.setenv("OPENAI_API_KEY", "test-provider-key")

    run = storage.create_run(
        api_module.settings.user_id,
        RunCreate(
            question="Explain reliability scores simply.",
            provider="openai",
            use_live_provider=True,
            search_mode="off",
        ),
    )

    with TestClient(api_module.app) as client:
        with client.stream("GET", f"/api/runs/{run['run_id']}/events") as response:
            body = "".join(response.iter_text())

    assert response.status_code == 200
    assert body.index("event: answer_delta") < body.index("event: completed")
    assert "event: completed" in body
    assert "Reliability Evidence Graph ready" in body
    assert "UnboundLocalError" not in body


def test_run_event_stream_indexes_web_search_results(tmp_path, monkeypatch):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()
    monkeypatch.setattr(api_module, "storage", storage)
    monkeypatch.setattr(api_module, "entailment_verifier", FixtureEntailmentVerifier())
    monkeypatch.setattr(engine_module, "build_provider", lambda _provider, _api_key: FakeProvider())
    monkeypatch.setenv("OPENAI_API_KEY", "test-provider-key")
    monkeypatch.setenv("TAVILY_API_KEY", "test-search-key")

    def fake_search(_api_key, query, max_results, recency):
        return {
            "query": query,
            "results": [
                {
                    "title": "Reliability Search Source",
                    "url": "https://example.com/reliability-search",
                    "content": "Reliability scores are diagnostic summaries, not calibrated probabilities. They help rank answers by support and uncertainty.",
                    "snippet": "Reliability scores are diagnostic summaries.",
                    "score": 0.9,
                    "published_date": "2026-05-01",
                }
            ],
            "response_time": 0.01,
            "request_id": "req_test",
        }

    monkeypatch.setattr(api_module, "search_tavily", fake_search)
    run = storage.create_run(
        api_module.settings.user_id,
        RunCreate(
            question="What is the latest status of reliability scores?",
            provider="openai",
            use_live_provider=True,
            search_mode="always",
        ),
    )

    with TestClient(api_module.app) as client:
        with client.stream("GET", f"/api/runs/{run['run_id']}/events") as response:
            body = "".join(response.iter_text())

    completed = storage.get_run(api_module.settings.user_id, run["run_id"])

    assert response.status_code == 200
    assert "event: completed" in body
    assert completed["graph"]["run"]["search_used"] is True
    assert completed["graph"]["web_search"]["calls"][0]["result_count"] == 1
    assert completed["graph"]["web_search"]["documents"][0]["source_type"] == "web_search_result"
    assert completed["graph"]["answer"]["citation_annotations"]
    chunks = storage.list_document_chunks(api_module.settings.user_id, [completed["graph"]["web_search"]["documents"][0]["document_id"]])
    assert chunks[0]["text"].startswith("Published date: 2026-05-01")


def test_conversation_chat_forces_web_search_even_when_payload_says_off(tmp_path, monkeypatch):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()
    monkeypatch.setattr(api_module, "storage", storage)
    monkeypatch.setattr(api_module, "entailment_verifier", FixtureEntailmentVerifier())
    monkeypatch.setattr(engine_module, "build_provider", lambda _provider, _api_key: FakeProvider())
    monkeypatch.setenv("OPENAI_API_KEY", "test-provider-key")
    monkeypatch.setenv("TAVILY_API_KEY", "test-search-key")
    calls = []

    def fake_search(_api_key, query, max_results, recency):
        calls.append(query)
        return {
            "query": query,
            "results": [
                {
                    "title": "Source",
                    "url": "https://example.com/source",
                    "content": "Reliability scores are diagnostic summaries, not calibrated probabilities.",
                    "snippet": "Reliability scores are diagnostic summaries.",
                    "score": 0.9,
                }
            ],
            "response_time": 0.01,
        }

    monkeypatch.setattr(api_module, "search_tavily", fake_search)
    conversation = storage.create_conversation(api_module.settings.user_id)

    with TestClient(api_module.app) as client:
        created = client.post(
            f"/api/conversations/{conversation['conversation_id']}/messages",
            json={"content": "Explain reliability scores simply.", "attachment_document_ids": [], "search_mode": "off"},
        )
        run_id = created.json()["run"]["run_id"]
        with client.stream("GET", f"/api/runs/{run_id}/events") as response:
            body = "".join(response.iter_text())

    completed = storage.get_run(api_module.settings.user_id, run_id)

    assert created.status_code == 201
    assert created.json()["run"]["search_mode"] == "always"
    assert response.status_code == 200
    assert calls
    assert "event: completed" in body
    assert completed["graph"]["run"]["search_mode"] == "always"


def test_missing_search_key_is_reported_as_degraded_evidence(tmp_path, monkeypatch):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()
    monkeypatch.setattr(api_module, "storage", storage)
    monkeypatch.setattr(api_module, "entailment_verifier", FixtureEntailmentVerifier())
    monkeypatch.setattr(engine_module, "build_provider", lambda _provider, _api_key: FakeProvider())
    monkeypatch.setenv("OPENAI_API_KEY", "test-provider-key")
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)

    run = storage.create_run(
        api_module.settings.user_id,
        RunCreate(
            question="What is the latest status of reliability scores?",
            provider="openai",
            use_live_provider=True,
        ),
    )

    with TestClient(api_module.app) as client:
        with client.stream("GET", f"/api/runs/{run['run_id']}/events") as response:
            body = "".join(response.iter_text())

    completed = storage.get_run(api_module.settings.user_id, run["run_id"])

    assert response.status_code == 200
    assert "No web search key is configured in Settings." in body
    assert completed["graph"]["web_search"]["calls"][0]["error"] == "No web search key is configured in Settings."
    assert "no evidence retrieval for source-required question" in " ".join(completed["graph"]["score_caps"])


def test_create_message_rejects_missing_provider_without_saving_user_message(tmp_path, monkeypatch):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()
    monkeypatch.setattr(api_module, "storage", storage)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    conversation = storage.create_conversation(api_module.settings.user_id)

    with TestClient(api_module.app) as client:
        response = client.post(
            f"/api/conversations/{conversation['conversation_id']}/messages",
            json={"content": "What is ReliabilityGraph?", "attachment_document_ids": [], "search_mode": "off"},
        )

    assert response.status_code == 400
    assert "connect an LLM provider" in response.text
    assert storage.get_conversation(api_module.settings.user_id, conversation["conversation_id"])["messages"] == []


def test_create_message_rejects_unready_verifier_without_saving_user_message(tmp_path, monkeypatch):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()
    monkeypatch.setattr(api_module, "storage", storage)
    monkeypatch.setattr(api_module, "entailment_verifier", NotReadyVerifier())
    monkeypatch.setenv("OPENAI_API_KEY", "test-provider-key")
    conversation = storage.create_conversation(api_module.settings.user_id)

    with TestClient(api_module.app) as client:
        response = client.post(
            f"/api/conversations/{conversation['conversation_id']}/messages",
            json={"content": "What is ReliabilityGraph?", "attachment_document_ids": [], "search_mode": "off"},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "verifier_not_ready"
    assert storage.get_conversation(api_module.settings.user_id, conversation["conversation_id"])["messages"] == []


def test_delete_conversation_endpoint_removes_chat_messages_and_runs(tmp_path, monkeypatch):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()
    monkeypatch.setattr(api_module, "storage", storage)
    conversation = storage.create_conversation(api_module.settings.user_id, "Delete me")
    user_message = storage.add_message(
        api_module.settings.user_id,
        conversation["conversation_id"],
        "user",
        "Please answer this.",
    )
    run = storage.create_run(
        api_module.settings.user_id,
        RunCreate(
            question="Please answer this.",
            provider="openai",
            conversation_id=conversation["conversation_id"],
            user_message_id=user_message["message_id"],
            use_live_provider=True,
        ),
    )
    storage.add_message(
        api_module.settings.user_id,
        conversation["conversation_id"],
        "assistant",
        "Answer.",
        run_id=run["run_id"],
    )

    with TestClient(api_module.app) as client:
        response = client.delete(f"/api/conversations/{conversation['conversation_id']}")
        missing = client.get(f"/api/conversations/{conversation['conversation_id']}")

    assert response.status_code == 200
    assert response.json() == {"deleted": True}
    assert missing.status_code == 404
    with pytest.raises(KeyError):
        storage.get_run(api_module.settings.user_id, run["run_id"])


class FakeProvider:
    async def generate(self, request):
        system = "\n".join(message.content for message in request.messages if message.role == "system")
        if "candidate answer" in system:
            text = "Reliability scores are diagnostic summaries, not calibrated probabilities."
        elif "extract answer claims" in system:
            text = json.dumps(
                {
                    "claims": [
                        {
                            "text": "Reliability scores are diagnostic summaries, not calibrated probabilities.",
                            "type": "factual",
                            "importance": "high",
                            "checkability": "externally_checkable",
                        }
                    ]
                }
            )
        elif "trust assumptions" in system:
            text = json.dumps(
                {
                    "assumptions": [
                        {
                            "text": "The answer can be evaluated from available source evidence.",
                            "importance": "high",
                            "evidence_status": "untested",
                            "would_change_recommendation_if_false": True,
                            "sensitivity_notes": "More evidence can change the trust decision.",
                        }
                    ]
                }
            )
        elif "whether untrusted evidence supports answer claims" in system:
            text = json.dumps(
                {
                    "assessments": [
                        {
                            "claim_id": "c1",
                            "relation": "supported",
                            "why": "The source says reliability scores are diagnostic summaries.",
                            "source_limit": "Limited to retrieved snippets.",
                            "support_score": 0.9,
                            "evidence_ids": ["e1"],
                        }
                    ]
                }
            )
        elif "decision support" in system:
            text = json.dumps(
                {
                    "applicable": True,
                    "alternatives": [
                        {
                            "name": "Use with source context",
                            "evidence_status": "supported",
                            "basis": "The retrieved source supports the main claim.",
                            "risk": "The score still needs calibration.",
                        }
                    ],
                    "criteria": [{"name": "evidence quality", "basis": "Check source support."}],
                    "recommendation": "Use with source context",
                    "sensitivity_summary": "The recommendation changes if better evidence contradicts the source.",
                    "label": "Decision support, not objective truth.",
                }
            )
        else:
            text = "Reliability scores are diagnostic summaries, not calibrated probabilities."
        return GenerateResponse(text=text, model=request.model or "fake-model", provider="fake", raw={})


class NotReadyVerifier:
    def status(self):
        return {
            "ready": False,
            "provider": "onnxruntime",
            "model": "cross-encoder/nli-deberta-base",
            "cache_dir": "data/models/nli-deberta-base",
            "message": "NLI verifier model is missing.",
        }
