import json

import backend.reliability_graph.web_search as web_search_module
from backend.reliability_graph.web_search import choose_research_route, normalize_tavily_results, search_tavily


def test_research_router_covers_no_search_attachment_web_and_hybrid():
    assert choose_research_route("Explain semantic entropy simply.", [], "auto").route == "no_search"
    assert choose_research_route("Summarize this document.", ["doc_1"], "auto").route == "attachments_only"
    assert choose_research_route("What is the latest SimpleQA result?", [], "auto").route == "web_search"
    assert choose_research_route("Compare this document with current policy.", ["doc_1"], "auto").route == "hybrid"


def test_research_router_rewrites_search_queries_without_answer_instructions():
    route = choose_research_route(
        "What is the latest stable Python release today? Answer in one sentence and cite sources.",
        [],
        "auto",
    )

    assert route.route == "web_search"
    assert route.query == "official latest stable Python release"
    assert route.recency is None


def test_research_router_respects_manual_search_modes():
    assert choose_research_route("Tell me a story.", [], "always").route == "web_search"
    assert choose_research_route("What is current?", [], "off").route == "no_search"
    assert choose_research_route("What is current in this file?", ["doc_1"], "off").route == "attachments_only"
    assert choose_research_route("Do not search. What is current?", [], "always").route == "no_search"


def test_normalize_tavily_results_dedupes_and_requires_content():
    results = normalize_tavily_results(
        [
            {"title": "A", "url": "https://example.com/a", "content": "short"},
            {"title": "A", "url": "https://example.com/a", "content": "This result has enough useful content to index."},
            {"title": "B", "url": "https://example.com/b", "raw_content": "This raw content is long enough to become evidence."},
            {"title": "B2", "url": "https://example.com/b", "content": "Duplicate URL should not be kept even with content."},
        ]
    )

    assert [item["url"] for item in results] == ["https://example.com/a", "https://example.com/b"]
    assert results[1]["content"].startswith("This raw content")


def test_search_tavily_uses_bearer_auth_and_returns_normalized_results(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeSearchResponse(
            {
                "query": "executed query",
                "results": [
                    {
                        "title": "Source",
                        "url": "https://example.com/source",
                        "content": "This source contains enough useful content to index for reliability checks.",
                        "score": 0.7,
                    }
                ],
                "response_time": 0.12,
                "request_id": "req_1",
            }
        )

    monkeypatch.setattr(web_search_module.urllib.request, "urlopen", fake_urlopen)

    result = search_tavily("tvly-" + "test-secret", "latest reliability evals", max_results=20, recency="week", timeout=7)

    assert captured["authorization"] == "Bearer " + "tvly-" + "test-secret"
    assert captured["timeout"] == 7
    assert captured["body"]["include_answer"] is False
    assert captured["body"]["include_raw_content"] == "text"
    assert captured["body"]["max_results"] == 10
    assert captured["body"]["time_range"] == "week"
    assert result["results"][0]["url"] == "https://example.com/source"
    assert result["request_id"] == "req_1"


class FakeSearchResponse:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self, *_args):
        return json.dumps(self.data).encode("utf-8")
