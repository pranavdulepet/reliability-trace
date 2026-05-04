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
