import urllib.error

from backend.reliability_graph.benchmarks import build_benchmark_report
import backend.reliability_graph.retrieval as retrieval_module
from backend.reliability_graph.retrieval import build_chunks, evidence_for_claims, fetch_url_text, search_chunks, support_relation
from backend.reliability_graph.schemas import RunCreate
from backend.reliability_graph.storage import Storage


def test_document_chunks_match_claims():
    chunks = build_chunks(
        "Claim-level reliability systems should match atomic claims to source passages. "
        "Source provenance and chunk identifiers make audits easier to inspect."
    )
    stored_chunks = [
        {
            **chunk,
            "chunk_id": "chunk_1",
            "document_id": "doc_1",
            "title": "Reliability Notes",
            "source_url": "https://example.com/notes",
            "source_type": "manual_source",
        }
        for chunk in chunks
    ]
    claims = [
        {
            "claim_id": "c1",
            "text": "Reliability systems should match atomic claims to source passages.",
        }
    ]

    evidence = evidence_for_claims(claims, stored_chunks)

    assert evidence
    assert evidence[0]["claim_id"] == "c1"
    assert evidence[0]["source_title"] == "Reliability Notes"
    assert evidence[0]["support_relation"] in {"supports", "partially_supports"}


def test_support_relation_does_not_overread_unrelated_negation():
    claim = "Provider adapters are normal API connectors."
    snippet = (
        "Provider adapters are normal API connectors. "
        "Extra perturbation probes are behavioral diagnostics and do not reveal hidden reasoning."
    )

    assert support_relation(claim, snippet) == "supports"


def test_support_relation_does_not_treat_page_fallback_as_claim_contradiction():
    claim = "The information is stated on the Python Source Releases page on Python.org."
    snippet = (
        "Python Source Releases | Python.org Notice: This page displays a fallback because "
        "interactive scripts did not run. Latest Python 3 Release - Python 3.14.4."
    )

    assert support_relation(claim, snippet) in {"supports", "partially_supports"}


def test_support_relation_detects_direct_negation_near_claim_terms():
    claim = "Python 3.14.4 is the latest stable release."
    snippet = "Python 3.14.4 is not the latest stable release."

    assert support_relation(claim, snippet) == "contradicts"


def test_storage_saves_documents_and_searches_chunks(tmp_path):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()
    chunks = build_chunks("Perturbation probes compare baseline answers against pressure prompts.")

    document = storage.save_document("user_a", "Probe Notes", "Perturbation probes compare baseline answers.", None, "uploaded_document", chunks)
    matches = search_chunks("baseline perturbation probes", storage.list_document_chunks("user_a"))

    assert document["chunk_count"] == 1
    assert matches[0]["title"] == "Probe Notes"


def test_search_prefers_official_release_sources_over_secondary_sources():
    official = {
        **build_chunks("Python source releases include the latest stable release downloads and version history.")[0],
        "chunk_id": "official_1",
        "document_id": "doc_official",
        "title": "Python Source Releases",
        "source_url": "https://www.python.org/downloads/source/",
        "source_type": "web_search_result",
    }
    secondary = {
        **build_chunks("How to get the latest stable release of Python via a single HTTP request.")[0],
        "chunk_id": "secondary_1",
        "document_id": "doc_secondary",
        "title": "How to get the version number of the latest stable release of Python",
        "source_url": "https://stackoverflow.com/questions/70378786/example",
        "source_type": "web_search_result",
    }

    matches = search_chunks("official latest stable Python release", [secondary, official], limit=2)

    assert matches[0]["title"] == "Python Source Releases"


def test_storage_reuses_duplicate_documents_by_hash(tmp_path):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()
    text = "ReliabilityGraph stores attachment chunks for claim matching."
    first = storage.save_document("user_a", "First", text, None, "uploaded_document", build_chunks(text))
    duplicate = storage.find_document_by_signature("user_a", first["content_sha256"], None)

    assert duplicate["document_id"] == first["document_id"]


def test_storage_filters_chunks_to_chat_attachments(tmp_path):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()
    doc_a = storage.save_document("user_a", "Attached", "Attached source says ReliabilityGraph uses claim checks.", None, "uploaded_document", build_chunks("Attached source says ReliabilityGraph uses claim checks."))
    storage.save_document("user_a", "Unattached", "Unattached source says unrelated material.", None, "uploaded_document", build_chunks("Unattached source says unrelated material."))

    chunks = storage.list_document_chunks("user_a", [doc_a["document_id"]])

    assert len(chunks) == 1
    assert chunks[0]["title"] == "Attached"


def test_storage_conversation_messages_and_run_linkage(tmp_path):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()
    conversation = storage.create_conversation("user_a", "Provider setup")
    user_message = storage.add_message("user_a", conversation["conversation_id"], "user", "What should I trust?")
    run = storage.create_run(
        "user_a",
        RunCreate(
            question="What should I trust?",
            provider="tinker",
            conversation_id=conversation["conversation_id"],
            user_message_id=user_message["message_id"],
            attachment_document_ids=["doc_a"],
        ),
    )
    assistant_message = storage.add_message("user_a", conversation["conversation_id"], "assistant", "Trust the supported answer.", run_id=run["run_id"])
    reloaded = storage.get_conversation("user_a", conversation["conversation_id"])

    assert reloaded["messages"][0]["role"] == "user"
    assert reloaded["messages"][1]["message_id"] == assistant_message["message_id"]
    assert reloaded["messages"][1]["run"]["run_id"] == run["run_id"]
    assert storage.get_run("user_a", run["run_id"])["attachment_document_ids"] == ["doc_a"]


def test_storage_provider_preferences_are_user_scoped(tmp_path):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()

    storage.save_provider_preference("user_a", "openai", "gpt-test", 2, 0.5)

    assert storage.get_provider_preference("user_a")["provider"] == "openai"
    assert storage.get_provider_preference("user_b")["provider"] is None


def test_storage_search_preferences_and_key_views_are_user_scoped(tmp_path):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()

    storage.save_search_preference("user_a", "always", 4)
    storage.save_search_key("user_a", "tavily", "ciphertext", "fp-test")

    assert storage.get_search_preference("user_a")["search_mode"] == "always"
    assert storage.get_search_preference("user_a")["max_results"] == 4
    assert storage.get_search_preference("user_b")["search_mode"] == "auto"
    assert storage.get_search_key_view("user_a", "tavily")["fingerprint"] == "fp-test"
    assert storage.get_search_key_ciphertext("user_b", "tavily") is None


def test_storage_preserves_run_search_mode(tmp_path):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()

    run = storage.create_run(
        "user_a",
        RunCreate(
            question="What is the latest evidence?",
            provider="tinker",
            search_mode="always",
        ),
    )

    assert run["search_mode"] == "always"
    assert storage.get_run("user_a", run["run_id"])["search_mode"] == "always"


def test_benchmark_report_uses_labeled_graphs():
    report = build_benchmark_report(
        [
            {
                "run_id": "run_1",
                "correctness": 5,
                "graph": {
                    "answer": {"reliability_score": 80},
                    "features": {
                        "claim_support_rate": 0.9,
                        "source_quality_score": 0.8,
                        "semantic_stability": 0.7,
                        "prompt_flip_rate": 0.0,
                        "sycophancy_flip_rate": 0.0,
                        "judge_factuality_score": 0.8,
                        "judge_uncertainty_score": 0.8,
                        "decision_robustness": 0.6,
                        "trace_completeness": 1.0,
                    },
                },
            }
        ]
    )

    assert report["status"] == "local_calibration"
    assert report["label_count"] == 1
    assert report["ablations"]


def test_fetch_url_blocks_private_and_credentialed_targets():
    for url in ["http://127.0.0.1/private", "http://user:pass@example.com/source"]:
        try:
            fetch_url_text(url)
        except ValueError as exc:
            assert "blocked network" in str(exc) or "credentials" in str(exc)
        else:
            raise AssertionError("unsafe URL was not blocked")


def test_fetch_url_rejects_unsupported_content_type(monkeypatch):
    monkeypatch.setattr(retrieval_module.socket, "getaddrinfo", public_getaddrinfo)
    monkeypatch.setattr(
        retrieval_module.urllib.request,
        "build_opener",
        lambda *_handlers: FakeOpener(FakeResponse({"content-type": "application/octet-stream"}, b"\x00\x01")),
    )

    try:
        fetch_url_text("https://example.com/file.bin")
    except ValueError as exc:
        assert "unsupported source content type" in str(exc)
    else:
        raise AssertionError("unsupported content type was not rejected")


def test_fetch_url_rejects_oversized_content(monkeypatch):
    monkeypatch.setattr(retrieval_module.socket, "getaddrinfo", public_getaddrinfo)
    monkeypatch.setattr(
        retrieval_module.urllib.request,
        "build_opener",
        lambda *_handlers: FakeOpener(FakeResponse({"content-type": "text/plain", "content-length": "1500001"}, b"too large")),
    )

    try:
        fetch_url_text("https://example.com/large.txt")
    except ValueError as exc:
        assert "too large" in str(exc)
    else:
        raise AssertionError("oversized content was not rejected")


def test_fetch_url_rejects_redirect_into_blocked_network(monkeypatch):
    monkeypatch.setattr(
        retrieval_module.socket,
        "getaddrinfo",
        lambda host, *args, **kwargs: public_getaddrinfo(host, *args, **kwargs)
        if host == "example.com"
        else [("inet", "sock", 0, "", ("127.0.0.1", 80))],
    )
    monkeypatch.setattr(
        retrieval_module.urllib.request,
        "build_opener",
        lambda *_handlers: FakeRedirectOpener("http://127.0.0.1/internal"),
    )

    try:
        fetch_url_text("https://example.com/source")
    except ValueError as exc:
        assert "blocked network" in str(exc)
    else:
        raise AssertionError("unsafe redirect was not blocked")


def public_getaddrinfo(*_args, **_kwargs):
    return [("inet", "sock", 0, "", ("93.184.216.34", 443))]


class FakeResponse:
    def __init__(self, headers, body):
        self.headers = headers
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self, *_args):
        return self.body


class FakeOpener:
    def __init__(self, response):
        self.response = response

    def open(self, *_args, **_kwargs):
        return self.response


class FakeRedirectOpener:
    def __init__(self, location):
        self.location = location

    def open(self, request, *_args, **_kwargs):
        raise urllib.error.HTTPError(
            request.full_url,
            302,
            "Found",
            {"location": self.location},
            None,
        )
