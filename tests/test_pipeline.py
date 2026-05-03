import asyncio
import json

from backend.reliability_graph.pipeline import ReliabilityPipeline
from backend.reliability_graph.retrieval import build_chunks


def run_pipeline(run, retrieval_chunks=None):
    async def execute():
        pipeline = ReliabilityPipeline(retrieval_chunks=retrieval_chunks)

        async def resolver(_provider):
            return None

        events = []
        async for event in pipeline.run(run, resolver):
            events.append(event)
        return events

    return asyncio.run(execute())


def base_run(**overrides):
    run = {
        "run_id": "run_test",
        "question": "Should I build an LLM answer-reliability product?",
        "provider": "local",
        "model": None,
        "samples": 3,
        "max_cost_usd": 1.0,
        "use_live_provider": False,
        "status": "queued",
        "created_at": "2026-05-02T12:00:00Z",
        "completed_at": None,
        "graph": None,
        "error": None,
    }
    run.update(overrides)
    return run


def test_pipeline_builds_complete_decision_graph():
    events = run_pipeline(base_run())
    final = events[-1]
    graph = final["graph"]

    assert final["type"] == "completed"
    assert graph["run"]["question_type"] == "decision_qa"
    assert graph["answer"]["calibration_status"] == "uncalibrated_diagnostic"
    assert graph["decision_analysis"]["applicable"] is True
    assert graph["export"]["contains_plaintext_provider_keys"] is False
    assert len(graph["trace"]) == len(ReliabilityPipeline.steps)
    assert "likely correct" not in json.dumps(graph).lower()


def test_pipeline_marks_closed_model_causal_probe_unavailable():
    events = run_pipeline(
        base_run(
            provider="openai",
            model="gpt-4.1-mini",
            use_live_provider=False,
        )
    )
    graph = events[-1]["graph"]

    assert graph["causal_probe"]["available"] is False
    assert graph["causal_probe"]["mode"] == "not_available"


def test_pipeline_uses_document_evidence_for_claim_matching():
    chunks = [
        {
            **chunk,
            "chunk_id": "chunk_1",
            "document_id": "doc_1",
            "title": "Answer Reliability Guide",
            "source_url": None,
            "source_type": "uploaded_document",
        }
        for chunk in build_chunks(
            "The best provisional answer is to proceed only if the decision can be decomposed into claims, assumptions, risks, and reversible next steps. "
            "The main reliability need is evidence, not confidence language."
        )
    ]
    graph = run_pipeline(base_run(), retrieval_chunks=chunks)[-1]["graph"]

    assert any(item["source_type"] == "uploaded_document" for item in graph["evidence"])
    assert any(assessment["status"] in {"supported", "partially_supported"} for assessment in graph["claim_assessments"])


def test_pipeline_requires_tinker_key_for_perturbation_probe():
    events = run_pipeline(
        base_run(
            provider="tinker",
            model="tinker://example/sampler_weights/000080",
            use_live_provider=True,
        )
    )
    graph = events[-1]["graph"]

    assert graph["causal_probe"]["available"] is False
    assert graph["causal_probe"]["mode"] == "missing_key"
