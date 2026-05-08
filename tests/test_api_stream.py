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
        export_response = client.get(f"/api/runs/{run['run_id']}/export")
    completed = storage.get_run(api_module.settings.user_id, run["run_id"])

    assert response.status_code == 200
    assert export_response.status_code == 200
    assert export_response.json() == completed["graph"]
    assert completed["graph"]["graph_version"] == "v2"
    assert body.index("event: answer_delta") < body.index("event: completed")
    assert "event: audit_progress" in body
    assert "reliability_score" not in body.split("event: completed", 1)[0]
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


def test_followup_reuses_prior_context_and_thread_sources(tmp_path, monkeypatch):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()
    monkeypatch.setattr(api_module, "storage", storage)
    monkeypatch.setattr(api_module, "entailment_verifier", FixtureEntailmentVerifier())
    monkeypatch.setattr(engine_module, "build_provider", lambda _provider, _api_key: FakeProvider())
    monkeypatch.setenv("OPENAI_API_KEY", "test-provider-key")
    conversation = storage.create_conversation(api_module.settings.user_id, "ExampleOS")
    document = storage.save_document(
        api_module.settings.user_id,
        "ExampleOS note",
        "ExampleOS 9 supports enterprise deployments.",
        None,
        "chat_attachment",
        [{"chunk_index": 0, "text": "ExampleOS 9 supports enterprise deployments.", "embedding_json": "[]", "token_count": 5}],
    )
    storage.add_message(
        api_module.settings.user_id,
        conversation["conversation_id"],
        "user",
        "Use this release note.",
        attachment_document_ids=[document["document_id"]],
    )
    storage.link_conversation_documents(api_module.settings.user_id, conversation["conversation_id"], [document["document_id"]])
    storage.add_message(
        api_module.settings.user_id,
        conversation["conversation_id"],
        "assistant",
        "The note says ExampleOS 9 supports enterprise deployments.",
    )

    with TestClient(api_module.app) as client:
        created = client.post(
            f"/api/conversations/{conversation['conversation_id']}/messages",
            json={"content": "What does that imply for buyers?", "attachment_document_ids": []},
        )
        run_id = created.json()["run"]["run_id"]
        with client.stream("GET", f"/api/runs/{run_id}/events") as response:
            body = "".join(response.iter_text())

    completed = storage.get_run(api_module.settings.user_id, run_id)

    assert created.status_code == 201
    assert response.status_code == 200
    assert "event: completed" in body
    assert completed["thread_document_ids"] == [document["document_id"]]
    assert any("ExampleOS 9 supports" in item["content"] for item in completed["prior_context"])
    assert completed["graph"]["run"]["used_conversation_context"] is True
    assert completed["graph"]["run"]["used_thread_sources"] is True


def test_prior_context_keeps_recent_turns_and_summarizes_older_turns():
    messages = []
    for index in range(12):
        messages.append(
            {
                "role": "user" if index % 2 == 0 else "assistant",
                "content": "Turn %d about the reliability plan." % index,
            }
        )
    context = api_module._conversation_prior_context({"summary": "", "messages": messages})

    assert context[0]["role"] == "system"
    assert "Turn 0" in context[0]["content"]
    assert len([item for item in context if item["role"] in {"user", "assistant"}]) == 8
    assert context[-1]["content"] == "Turn 11 about the reliability plan."


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


def test_demo_access_guard_requires_valid_session(monkeypatch):
    monkeypatch.setattr(api_module.settings, "access_token", "demo-code")
    monkeypatch.setattr(api_module.settings, "public_demo", True)
    monkeypatch.setattr(api_module.settings, "secret", "test-secret")
    monkeypatch.setattr(api_module.settings, "cookie_secure", False)
    monkeypatch.setattr(api_module.settings, "rate_limit_requests", 120)

    with TestClient(api_module.app) as client:
        blocked = client.get("/api/providers")
        wrong = client.post("/api/access/session", json={"access_code": "wrong"})
        session = client.post("/api/access/session", json={"access_code": "demo-code"})
        allowed = client.get("/api/providers")

    assert blocked.status_code == 401
    assert blocked.json()["detail"]["code"] == "access_required"
    assert wrong.status_code == 401
    assert session.status_code == 200
    assert "rg_access=" in session.headers["set-cookie"]
    assert allowed.status_code == 200


def test_demo_rate_limit_counts_authenticated_requests(monkeypatch):
    monkeypatch.setattr(api_module.settings, "access_token", "demo-code")
    monkeypatch.setattr(api_module.settings, "public_demo", True)
    monkeypatch.setattr(api_module.settings, "secret", "test-secret")
    monkeypatch.setattr(api_module.settings, "cookie_secure", False)
    monkeypatch.setattr(api_module.settings, "rate_limit_requests", 1)
    monkeypatch.setattr(api_module.settings, "rate_limit_window_seconds", 3600)
    api_module._rate_limit_buckets.clear()

    with TestClient(api_module.app) as client:
        session = client.post("/api/access/session", json={"access_code": "demo-code"})
        first = client.get("/api/providers")
        second = client.get("/api/verifier")

    assert session.status_code == 200
    assert first.status_code == 200
    assert second.status_code == 429


def test_demo_rate_limit_counts_access_attempts(monkeypatch):
    monkeypatch.setattr(api_module.settings, "access_token", "demo-code")
    monkeypatch.setattr(api_module.settings, "public_demo", True)
    monkeypatch.setattr(api_module.settings, "secret", "test-secret")
    monkeypatch.setattr(api_module.settings, "cookie_secure", False)
    monkeypatch.setattr(api_module.settings, "rate_limit_requests", 1)
    monkeypatch.setattr(api_module.settings, "rate_limit_window_seconds", 3600)
    api_module._rate_limit_buckets.clear()

    with TestClient(api_module.app) as client:
        first = client.post("/api/access/session", json={"access_code": "wrong"})
        second = client.post("/api/access/session", json={"access_code": "demo-code"})

    assert first.status_code == 401
    assert second.status_code == 429


def test_demo_sessions_get_isolated_conversation_scopes(tmp_path, monkeypatch):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()
    monkeypatch.setattr(api_module, "storage", storage)
    monkeypatch.setattr(api_module.settings, "access_token", "demo-code")
    monkeypatch.setattr(api_module.settings, "public_demo", True)
    monkeypatch.setattr(api_module.settings, "secret", "test-secret")
    monkeypatch.setattr(api_module.settings, "cookie_secure", False)
    monkeypatch.setattr(api_module.settings, "rate_limit_requests", 120)
    api_module._rate_limit_buckets.clear()

    with TestClient(api_module.app) as first_client, TestClient(api_module.app) as second_client:
        assert first_client.post("/api/access/session", json={"access_code": "demo-code"}).status_code == 200
        assert second_client.post("/api/access/session", json={"access_code": "demo-code"}).status_code == 200

        created = first_client.post("/api/conversations", json={"title": "first client chat"})
        first_list = first_client.get("/api/conversations")
        second_list = second_client.get("/api/conversations")

    assert created.status_code == 201
    assert len(first_list.json()["conversations"]) == 1
    assert second_list.json()["conversations"] == []


def test_demo_can_disable_key_management(monkeypatch):
    monkeypatch.setattr(api_module.settings, "access_token", None)
    monkeypatch.setattr(api_module.settings, "allow_key_management", False)

    with TestClient(api_module.app) as client:
        provider_response = client.post("/api/keys", json={"provider": "tinker", "api_key": "demo-key"})
        search_response = client.post("/api/search-key", json={"api_key": "demo-search-key"})

    assert provider_response.status_code == 403
    assert search_response.status_code == 403


def test_public_demo_allows_frontend_shell_but_blocks_api_without_session(monkeypatch):
    monkeypatch.setattr(api_module.settings, "access_token", "demo-code")
    monkeypatch.setattr(api_module.settings, "public_demo", True)

    assert api_module._is_public_path("/")
    assert api_module._is_public_path("/assets/index.js")
    assert api_module._is_public_path("/settings")
    assert api_module._is_public_path("/api/access/status")
    assert not api_module._is_public_path("/api/providers")
    assert not api_module._is_public_path("/docs")
    assert not api_module._is_public_path("/openapi.json")


def test_public_health_redacts_internal_paths_and_sets_security_headers(monkeypatch):
    monkeypatch.setattr(api_module.settings, "public_demo", True)
    monkeypatch.setattr(api_module.settings, "access_token", "demo-code")
    monkeypatch.setattr(api_module.settings, "secret", "test-secret")
    monkeypatch.setattr(api_module.settings, "cookie_secure", True)
    monkeypatch.setattr(api_module, "entailment_verifier", FixtureEntailmentVerifier())

    with TestClient(api_module.app) as client:
        response = client.get("/health")

    body = response.json()

    assert response.status_code == 200
    assert "db_path" not in body
    assert "user_scope" not in body
    assert "cache_dir" not in body["verifier"]
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


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
