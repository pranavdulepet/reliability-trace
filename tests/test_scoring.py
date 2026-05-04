from backend.reliability_graph.pipeline.scoring import compute_reliability_score


def perfect_features():
    return {
        "claim_support_rate": 1.0,
        "semantic_stability": 1.0,
        "source_quality_score": 1.0,
        "judge_factuality_score": 1.0,
        "judge_uncertainty_score": 1.0,
        "sycophancy_flip_rate": 0.0,
        "prompt_flip_rate": 0.0,
        "decision_robustness": 1.0,
        "trace_completeness": 1.0,
    }


def test_score_caps_one_critical_contradiction():
    score, caps = compute_reliability_score(
        perfect_features(),
        {"critical_factual_contradictions": 1},
    )

    assert score == 60
    assert "critical factual claim contradicted" in caps[0]


def test_score_caps_multiple_critical_contradictions_before_other_caps():
    score, caps = compute_reliability_score(
        perfect_features(),
        {
            "critical_factual_contradictions": 2,
            "unsupported_high_impact_assumption": True,
        },
    )

    assert score == 40
    assert any("multiple critical factual claims contradicted" in cap for cap in caps)


def test_score_caps_missing_current_evidence():
    score, caps = compute_reliability_score(
        perfect_features(),
        {"no_evidence_for_factual_current_question": True},
    )

    assert score == 65
    assert any("no evidence retrieval" in cap for cap in caps)


def test_score_caps_low_sample_overlap():
    features = perfect_features()
    features["sample_overlap_stability"] = 0.2

    score, caps = compute_reliability_score(features, {})

    assert score == 55
    assert any("low sample evidence overlap" in cap for cap in caps)


def test_score_caps_low_provenance_single_sample_evidence():
    features = perfect_features()
    features["source_quality_score"] = 0.25
    features["sample_overlap_stability"] = 0.5
    features["retrieval_alignment_score"] = 0.72

    score, caps = compute_reliability_score(features, {})

    assert score == 70
    assert any("low-provenance single-sample evidence" in cap for cap in caps)
