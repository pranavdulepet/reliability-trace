from backend.reliability_graph.benchmarks import build_benchmark_report
from backend.reliability_graph.retrieval import build_chunks, evidence_for_claims, search_chunks, support_relation
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
