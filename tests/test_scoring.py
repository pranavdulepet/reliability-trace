from backend.reliability_graph.pipeline.scoring import (
    DEFAULT_EVIDENCE_OPTIONAL_WEIGHTS,
    DEFAULT_EVIDENCE_REQUIRED_WEIGHTS,
    compute_reliability_score,
)


def perfect_features():
    return {
        "evidence_required": 1.0,
        "claim_support_rate": 1.0,
        "semantic_stability": 1.0,
        "source_quality_score": 1.0,
        "retrieval_alignment_score": 1.0,
        "retrieval_peak_score": 1.0,
        "sample_overlap_stability": 1.0,
    }


def test_score_caps_one_critical_contradiction():
    score, caps = compute_reliability_score(
        perfect_features(),
        {"critical_factual_contradictions": 1},
    )

    assert score == 60
    assert "critical factual claim contradicted" in caps[0]


def test_score_does_not_overweight_low_provenance_contradiction_caps():
    features = perfect_features()
    features["source_quality_score"] = 0.25
    features["retrieval_alignment_score"] = 0.9
    features["retrieval_peak_score"] = 0.9

    score, caps = compute_reliability_score(
        features,
        {"critical_factual_contradictions": 1, "unsupported_high_impact_assumption": True},
    )

    assert score > 70
    assert not any("critical factual claim contradicted" in cap for cap in caps)
    assert not any("unsupported high-impact assumption" in cap for cap in caps)


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

    assert score == 45
    assert any("source-required question" in cap for cap in caps)


def test_score_caps_low_sample_overlap():
    features = perfect_features()
    features["sample_overlap_stability"] = 0.2

    score, caps = compute_reliability_score(features, {})

    assert score == 55
    assert any("low sample evidence overlap" in cap for cap in caps)


def test_score_caps_partial_source_support_below_rely_threshold():
    score, caps = compute_reliability_score(
        perfect_features(),
        {"evidence_required": True, "partial_support_claims": 1},
    )

    assert score == 74
    assert any("partial source support" in cap for cap in caps)


def test_score_caps_low_provenance_partial_support_as_not_reliable():
    features = perfect_features()
    features["source_quality_score"] = 0.25
    features["retrieval_alignment_score"] = 0.7
    features["retrieval_peak_score"] = 0.7

    score, caps = compute_reliability_score(
        features,
        {"evidence_required": True, "partial_support_claims": 1},
    )

    assert score == 50
    assert any("partial support from low-provenance sources" in cap for cap in caps)


def test_score_caps_uncorroborated_partial_support_as_not_reliable():
    features = perfect_features()
    features["sample_overlap_stability"] = 0.5

    score, caps = compute_reliability_score(
        features,
        {"evidence_required": True, "partial_support_claims": 1},
    )

    assert score == 60
    assert any("partial source support without sample corroboration" in cap for cap in caps)


def test_score_caps_candidate_answer_conflicts():
    features = perfect_features()
    features["sample_conflict_rate"] = 1.0

    score, caps = compute_reliability_score(features, {})

    assert score == 60
    assert any("candidate answers conflict" in cap for cap in caps)


def test_score_caps_low_provenance_single_sample_evidence():
    features = perfect_features()
    features["source_quality_score"] = 0.25
    features["sample_overlap_stability"] = 0.5
    features["retrieval_alignment_score"] = 0.72
    features["retrieval_peak_score"] = 0.72

    score, caps = compute_reliability_score(features, {})

    assert score == 70
    assert any("low-provenance single-sample evidence" in cap for cap in caps)


def test_score_does_not_overweight_single_peak_retrieval_match():
    features = perfect_features()
    features["claim_support_rate"] = 0.2
    features["retrieval_alignment_score"] = 0.1
    features["retrieval_peak_score"] = 0.9
    features["sample_overlap_stability"] = 0.5
    features["source_quality_score"] = 0.62

    score, caps = compute_reliability_score(features, {})

    assert score < 60
    assert caps == []


def test_score_uses_consistency_more_when_external_evidence_is_optional():
    features = perfect_features()
    features.update(
        {
            "evidence_required": 0.0,
            "claim_support_rate": 0.0,
            "retrieval_alignment_score": 0.0,
            "retrieval_peak_score": 0.0,
            "source_quality_score": 0.0,
            "sample_overlap_stability": 1.0,
            "semantic_stability": 1.0,
        }
    )

    default_score, default_caps = compute_reliability_score(
        features,
        {},
        DEFAULT_EVIDENCE_REQUIRED_WEIGHTS,
        DEFAULT_EVIDENCE_OPTIONAL_WEIGHTS,
    )
    score, caps = compute_reliability_score(features, {})

    assert default_score == 70
    assert default_caps == []
    assert score >= 60
    assert caps == []


def test_score_accepts_explicit_weight_overrides():
    features = perfect_features()
    features["claim_support_rate"] = 0.0
    required_weights = {key: 0.0 for key in DEFAULT_EVIDENCE_REQUIRED_WEIGHTS}
    required_weights["claim_support_rate"] = 1.0

    score, caps = compute_reliability_score(
        features,
        {},
        required_weights,
        DEFAULT_EVIDENCE_OPTIONAL_WEIGHTS,
    )

    assert score == 0
    assert caps == []
