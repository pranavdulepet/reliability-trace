from backend.reliability_graph.benchmarks import build_benchmark_report
from backend.reliability_graph.retrieval import build_chunks, evidence_for_claims, search_chunks, support_relation
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
    claim = "Tinker is a training and sampling API from Thinking Machines."
    snippet = (
        "Tinker is a training and sampling API from Thinking Machines. "
        "Extra perturbation probes are behavioral diagnostics and do not reveal hidden reasoning."
    )

    assert support_relation(claim, snippet) == "supports"


def test_storage_saves_documents_and_searches_chunks(tmp_path):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()
    chunks = build_chunks("Tinker perturbation probes compare baseline answers against pressure prompts.")

    document = storage.save_document("user_a", "Probe Notes", "Tinker perturbation probes compare baseline answers.", None, "uploaded_document", chunks)
    matches = search_chunks("baseline perturbation probes", storage.list_document_chunks("user_a"))

    assert document["chunk_count"] == 1
    assert matches[0]["title"] == "Probe Notes"


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
