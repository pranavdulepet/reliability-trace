from fastapi.testclient import TestClient

import backend.reliability_graph.api as api_module
from backend.reliability_graph.schemas import RunCreate
from backend.reliability_graph.storage import Storage


def test_run_event_stream_completes_without_shadowing_run_state(tmp_path, monkeypatch):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()
    monkeypatch.setattr(api_module, "storage", storage)

    run = storage.create_run(
        api_module.settings.user_id,
        RunCreate(
            question="Explain reliability scores simply.",
            provider="local",
            use_live_provider=False,
            search_mode="off",
        ),
    )

    with TestClient(api_module.app) as client:
        with client.stream("GET", f"/api/runs/{run['run_id']}/events") as response:
            body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: completed" in body
    assert "Reliability Evidence Graph ready" in body
    assert "UnboundLocalError" not in body


def test_run_event_stream_indexes_web_search_results(tmp_path, monkeypatch):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()
    monkeypatch.setattr(api_module, "storage", storage)
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
                    "published_date": None,
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
            provider="local",
            use_live_provider=False,
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
