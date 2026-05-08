import asyncio

import backend.reliability_graph.pipeline.engine as engine_module
from backend.reliability_graph.evals import (
    EvalExample,
    auroc,
    average_precision,
    baseline_report,
    build_markdown_report,
    expected_calibration_error,
    filter_examples_for_mode,
    grade_simpleqa_prediction,
    _root_cause,
    ragtruth_to_example,
    redact_value,
    run_eval_example,
    selfcheck_to_example,
    simpleqa_to_example,
    stable_split_bucket,
    summarize_eval_results,
)
from scripts.run_reliability_evals import _append_result, _default_output_dir, _internal_regressions, _read_results, _sample_examples


def test_eval_metric_math_on_tiny_fixture():
    labels = [1, 0, 1, 0]
    risk_scores = [0.9, 0.2, 0.7, 0.1]
    confidences = [0.1, 0.8, 0.3, 0.9]
    correctness = [0.0, 1.0, 0.0, 1.0]

    assert auroc(labels, risk_scores) == 1.0
    assert average_precision(labels, risk_scores) == 1.0
    assert round(expected_calibration_error(confidences, correctness, bins=2), 3) == 0.175


def test_capped_eval_sampling_is_stable_and_seeded():
    examples = list(range(20))

    first = _sample_examples(examples, 5, 7)
    second = _sample_examples(examples, 5, 7)
    different_seed = _sample_examples(examples, 5, 8)

    assert first == second
    assert first != examples[:5]
    assert first != different_seed


def test_default_eval_output_dir_is_collision_resistant():
    first = _default_output_dir()
    second = _default_output_dir()

    assert first != second
    assert first.parent.as_posix() == "data/evals/runs"
    assert second.parent.as_posix() == "data/evals/runs"


def test_ragtruth_label_mapping():
    example = ragtruth_to_example(
        {
            "id": "r1",
            "source_id": "s1",
            "response": "The product launched in 2027.",
            "labels": [{"label_type": "Evident Baseless Info", "text": "2027"}],
            "quality": "good",
            "split": "test",
        },
        {
            "source_id": "s1",
            "task_type": "QA",
            "source_info": {"question": "When did it launch?", "passages": "The product launched in 2026."},
        },
    )

    assert example.benchmark == "ragtruth"
    assert example.question == "When did it launch?"
    assert example.gold_labels["bad_answer"] is True
    assert example.gold_labels["label_types"] == ["Evident Baseless Info"]
    assert example.source_texts == ["The product launched in 2026."]


def test_selfcheck_annotation_mapping():
    example = selfcheck_to_example(
        {
            "wiki_bio_test_idx": "w1",
            "gpt3_text": "Ada Lovelace was a mathematician. She won a Nobel Prize.",
            "wiki_bio_text": "Ada Lovelace was a mathematician. The Nobel Prizes did not exist in her lifetime.",
            "annotation": ["accurate", "major_inaccurate"],
            "gpt3_text_samples": ["Ada Lovelace was a mathematician."],
        }
    )

    assert example.benchmark == "selfcheck"
    assert example.gold_labels["bad_answer"] is True
    assert example.gold_labels["bad_sentence_count"] == 1
    assert example.metadata["sample_answers"] == ["Ada Lovelace was a mathematician."]


def test_simpleqa_strict_grading_marks_ambiguous_review():
    example = simpleqa_to_example(
        {"id": "s1", "problem": "What city is OpenAI headquartered in?", "answer": "San Francisco, California"}
    )

    assert example.answer == "San Francisco, California"
    assert grade_simpleqa_prediction(example.question, example.answer, "San Francisco, California") == "correct"
    assert grade_simpleqa_prediction(example.question, example.answer, "San Francisco") == "needs_review"
    assert grade_simpleqa_prediction(example.question, example.answer, "I don't know.") == "not_attempted"
    assert grade_simpleqa_prediction(example.question, example.answer, "Los Angeles") == "incorrect"


def test_eval_dev_test_split_is_stable():
    rag_train = EvalExample("ragtruth", "train", "q", "a", [], {}, {"split": "train"})
    rag_test = EvalExample("ragtruth", "test", "q", "a", [], {}, {"split": "test"})
    selfcheck = [EvalExample("selfcheck", str(index), "q", "a", [], {}, {}) for index in range(20)]

    assert filter_examples_for_mode([rag_train, rag_test], "dev", seed=7) == [rag_train]
    assert filter_examples_for_mode([rag_train, rag_test], "test", seed=7) == [rag_test]
    assert stable_split_bucket("selfcheck:1", 7) == stable_split_bucket("selfcheck:1", 7)
    assert len(filter_examples_for_mode(selfcheck, "dev", seed=7)) + len(filter_examples_for_mode(selfcheck, "test", seed=7)) == 20


def test_resume_result_read_deduplicates(tmp_path):
    path = tmp_path / "results.jsonl"
    row = {"benchmark": "ragtruth", "example_id": "a", "metrics": {"score": 0.5}}

    _append_result(path, row)
    _append_result(path, row)

    assert len(_read_results(path)) == 1


def test_eval_answer_override_does_not_call_provider(monkeypatch):
    def fail_provider(*_args, **_kwargs):
        raise AssertionError("provider should not be built for fixed-answer evals")

    monkeypatch.setattr(engine_module, "build_provider", fail_provider)
    example = EvalExample(
        benchmark="fixed",
        example_id="one",
        question="What does the source say?",
        answer="The source says the release date is April 2, 2026.",
        source_texts=["The release date is April 2, 2026."],
        gold_labels={"bad_answer": False},
        metadata={},
    )

    result = asyncio.run(run_eval_example(example, live_provider="tinker"))

    assert result["answer"] == "The source says the release date is April 2, 2026."
    assert result["graph"]["run"]["provider"] == "local"
    assert result["labels"]["is_correct"] is True


def test_eval_redacts_provider_secrets_from_outputs():
    fake_tinker_key = "tml-" + "someVerySecretProviderKeyValue"
    fake_openai_key = "sk-" + "thisShouldNeverLeak"
    fake_gemini_key = "AIza" + "ThisShouldAlsoBeRedacted123456789"
    payload = {
        "api_key": fake_tinker_key,
        "error": "Authorization: Bearer " + fake_openai_key,
        "nested": [fake_gemini_key],
    }

    redacted = redact_value(payload)

    assert redacted["api_key"] == "[redacted]"
    assert fake_openai_key not in redacted["error"]
    assert "[redacted]" in redacted["nested"][0]


def test_eval_report_contains_required_sections():
    results = [
        {
            "benchmark": "ragtruth",
            "example_id": "r1",
            "score": 82,
            "verdict": "rely",
            "evidence_status": "Sources support the main checked claims.",
            "features": {"claim_support_rate": 1.0, "semantic_stability": 1.0},
            "graph": {"evidence": [{"relevance_score": 0.9}], "claim_assessments": []},
            "labels": {"bad_answer": False, "is_correct": True, "include_in_calibration": True},
            "metrics": {"score": 0.82, "risk_score": 0.18, "correctness": 1.0, "bad_answer": False, "false_safe": False},
        }
    ]
    summary = summarize_eval_results(results, notes=["fixture"])
    report = build_markdown_report(summary, results)

    assert "## Aggregate Metrics" in report
    assert "Claim recall" in report
    assert "## Baselines" in report
    assert "## Ablations" in report
    assert "## Failure Cases" in report
    assert "## Fix Candidates" in report


def test_selfcheck_sentence_metrics_and_baselines():
    result = {
        "benchmark": "selfcheck",
        "example_id": "w1",
        "score": 40,
        "verdict": "use_with_caution",
        "evidence_status": "mixed",
        "features": {"claim_support_rate": 0.2, "semantic_stability": 0.3},
        "graph": {
            "evidence": [{"relevance_score": 0.2}],
            "claim_assessments": [],
        },
        "labels": {
            "bad_answer": True,
            "is_correct": False,
            "include_in_calibration": True,
            "bad_sentence_rate": 1.0,
        },
        "metrics": {
            "score": 0.4,
            "risk_score": 0.6,
            "correctness": 0.0,
            "bad_answer": True,
            "false_safe": False,
            "selfcheck_ngram_risk": 0.8,
            "sentence_items": [{"is_nonfactual": True, "risk_score": 0.9}],
        },
    }

    summary = summarize_eval_results([result])

    assert summary["benchmark_details"]["selfcheck"]["sentence_nonfact_auprc"] == 1.0
    assert baseline_report([result])["claim_support_only"]["scored_count"] == 1


def test_baseline_report_preserves_relation_recall_metric():
    result = {
        "benchmark": "ragtruth",
        "example_id": "r1",
        "features": {"claim_support_rate": 0.1, "retrieval_alignment_score": 0.2, "semantic_stability": 0.3},
        "metrics": {
            "score": 0.2,
            "risk_score": 0.8,
            "correctness": 0.0,
            "bad_answer": True,
            "false_safe": False,
            "relation_detected": True,
        },
    }

    assert baseline_report([result])["full_score"]["claim_relation_recall_on_bad"] == 1.0


def test_root_cause_labels_partial_support_without_overstating_contradiction():
    result = {
        "metrics": {"bad_answer": True, "relation_detected": False, "score": 0.55},
        "labels": {"bad_answer": True},
        "graph": {
            "evidence": [{"support_relation": "supports", "relevance_score": 0.6}],
            "claim_assessments": [{"relation": "partially_supported"}],
        },
    }

    assert _root_cause(result) == "partial-support ambiguity"


def test_root_cause_labels_claim_source_matching_when_evidence_exists():
    result = {
        "metrics": {"bad_answer": True, "relation_detected": False, "score": 0.55},
        "labels": {"bad_answer": True},
        "graph": {
            "evidence": [{"support_relation": "unknown", "relevance_score": 0.3}],
            "claim_assessments": [{"relation": "supported"}],
        },
    }

    assert _root_cause(result) == "claim/source matching miss"


def test_root_cause_labels_detected_bad_answer_as_severity_tuning():
    result = {
        "metrics": {"bad_answer": True, "relation_detected": True, "score": 0.55},
        "labels": {"bad_answer": True},
        "graph": {
            "evidence": [{"support_relation": "contradicts", "relevance_score": 0.6}],
            "claim_assessments": [{"relation": "supported", "source_conflict": True}],
        },
    }

    assert _root_cause(result) == "risk detected; severity tuning"


def test_regression_gate_compares_baselines_on_same_rows():
    results = [
        _gate_result("selfcheck", "bad", risk=0.9, baseline_risk=0.8, bad=True),
        _gate_result("selfcheck", "good", risk=0.1, baseline_risk=0.2, bad=False),
        {
            "benchmark": "simpleqa",
            "example_id": "all-correct",
            "features": {"claim_support_rate": 0.0, "semantic_stability": 1.0},
            "metrics": {
                "score": 0.4,
                "risk_score": 0.6,
                "correctness": 1.0,
                "bad_answer": False,
                "false_safe": False,
            },
        },
    ]

    assert _internal_regressions(results) == []


def test_regression_gate_flags_same_row_baseline_win():
    results = [
        _gate_result("selfcheck", "bad-low-risk", risk=0.1, baseline_risk=0.95, bad=True, baseline_name="sample_consistency_only"),
        _gate_result("selfcheck", "bad-high-risk", risk=0.2, baseline_risk=0.9, bad=True, baseline_name="sample_consistency_only"),
        _gate_result("selfcheck", "good", risk=0.8, baseline_risk=0.05, bad=False, baseline_name="sample_consistency_only"),
    ]

    regressions = _internal_regressions(results)

    assert regressions
    assert any("beat full score" in item for item in regressions)


def test_regression_gate_reports_selfcheck_ngram_but_does_not_block_on_ranking():
    results = [
        _gate_result("selfcheck", "bad-low-risk", risk=0.4, baseline_risk=0.95, bad=True),
        _gate_result("selfcheck", "bad-high-risk", risk=0.3, baseline_risk=0.9, bad=True),
        _gate_result("selfcheck", "good", risk=0.8, baseline_risk=0.05, bad=False),
    ]

    assert _internal_regressions(results) == []


def test_regression_gate_does_not_block_on_unsafe_baseline_win():
    results = [
        _gate_result("selfcheck", "bad-ranked-high", risk=0.6, baseline_risk=0.95, bad=True),
        _gate_result("selfcheck", "bad-false-safe", risk=0.4, baseline_risk=0.2, bad=True),
        _gate_result("selfcheck", "good-a", risk=0.5, baseline_risk=0.1, bad=False),
        _gate_result("selfcheck", "good-b", risk=0.45, baseline_risk=0.1, bad=False),
    ]

    assert _internal_regressions(results) == []


def _gate_result(benchmark: str, example_id: str, risk: float, baseline_risk: float, bad: bool, baseline_name: str = "selfcheck_ngram") -> dict:
    semantic_stability = 1.0 - (baseline_risk if baseline_name == "sample_consistency_only" else risk)
    return {
        "benchmark": benchmark,
        "example_id": example_id,
        "features": {"claim_support_rate": 1.0 - risk, "semantic_stability": semantic_stability},
        "metrics": {
            "score": 1.0 - risk,
            "risk_score": risk,
            "correctness": 0.0 if bad else 1.0,
            "bad_answer": bad,
            "false_safe": bad and risk <= 0.25,
            "selfcheck_ngram_risk": baseline_risk if baseline_name == "selfcheck_ngram" else None,
        },
        "graph": {"evidence": [{"relevance_score": 1.0 - risk}]},
    }
