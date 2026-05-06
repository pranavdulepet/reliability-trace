import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_EVIDENCE_REQUIRED_WEIGHTS = {
    "claim_support_rate": 0.42,
    "retrieval_alignment_score": 0.20,
    "source_quality_score": 0.15,
    "sample_overlap_stability": 0.07,
    "semantic_stability": 0.08,
    "retrieval_peak_score": 0.08,
}

DEFAULT_EVIDENCE_OPTIONAL_WEIGHTS = {
    "sample_overlap_stability": 0.35,
    "semantic_stability": 0.35,
    "claim_support_rate": 0.10,
    "retrieval_alignment_score": 0.10,
    "source_quality_score": 0.05,
    "retrieval_peak_score": 0.05,
}

SCORE_WEIGHT_CONFIG_PATH = Path(
    os.getenv(
        "RG_SCORE_WEIGHTS_PATH",
        str(Path(__file__).resolve().parents[3] / "configs" / "reliability_score_weights.json"),
    )
)


def _load_weight_config() -> Tuple[Dict[str, float], Dict[str, float], Dict[str, Any]]:
    if not SCORE_WEIGHT_CONFIG_PATH.exists():
        return (
            dict(DEFAULT_EVIDENCE_REQUIRED_WEIGHTS),
            dict(DEFAULT_EVIDENCE_OPTIONAL_WEIGHTS),
            {"source": "built_in_defaults", "path": None},
        )
    try:
        data = json.loads(SCORE_WEIGHT_CONFIG_PATH.read_text(encoding="utf-8"))
        required = _validated_weights(data.get("evidence_required_weights"), DEFAULT_EVIDENCE_REQUIRED_WEIGHTS)
        optional = _validated_weights(data.get("evidence_optional_weights"), DEFAULT_EVIDENCE_OPTIONAL_WEIGHTS)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return (
            dict(DEFAULT_EVIDENCE_REQUIRED_WEIGHTS),
            dict(DEFAULT_EVIDENCE_OPTIONAL_WEIGHTS),
            {"source": "built_in_defaults_after_invalid_config", "path": str(SCORE_WEIGHT_CONFIG_PATH)},
        )
    metadata = {
        "source": data.get("source") or "benchmark_tuned",
        "path": str(SCORE_WEIGHT_CONFIG_PATH),
        "trained_at": data.get("trained_at"),
        "benchmark_scope": data.get("benchmark_scope"),
    }
    return required, optional, metadata


def _validated_weights(raw: Any, fallback: Dict[str, float]) -> Dict[str, float]:
    if not isinstance(raw, dict):
        return dict(fallback)
    weights = {key: max(0.0, float(raw.get(key, 0.0))) for key in fallback}
    total = sum(weights.values())
    if total <= 0:
        return dict(fallback)
    return {key: value / total for key, value in weights.items()}


EVIDENCE_REQUIRED_WEIGHTS, EVIDENCE_OPTIONAL_WEIGHTS, SCORE_WEIGHT_METADATA = _load_weight_config()


def compute_reliability_score(
    features: Dict[str, float],
    caps: Dict[str, Any],
    required_weights: Optional[Dict[str, float]] = None,
    optional_weights: Optional[Dict[str, float]] = None,
) -> Tuple[int, List[str]]:
    weights = (
        (required_weights or EVIDENCE_REQUIRED_WEIGHTS)
        if features.get("evidence_required", 1.0) >= 0.5
        else (optional_weights or EVIDENCE_OPTIONAL_WEIGHTS)
    )
    raw = sum(weight * _feature(features, name) for name, weight in weights.items())
    score = int(round(max(0.0, min(1.0, raw)) * 100))
    applied: List[str] = []
    source_quality = features.get("source_quality_score", 0.0)
    retrieval_alignment = features.get("retrieval_alignment_score", source_quality)
    retrieval_peak = features.get(
        "retrieval_peak_score",
        retrieval_alignment,
    )
    high_trust_evidence = source_quality >= 0.50

    critical_contradictions = int(caps.get("critical_factual_contradictions", 0))
    if high_trust_evidence and critical_contradictions >= 2:
        score = min(score, 40)
        applied.append("multiple critical factual claims contradicted: score capped at 40")
    elif high_trust_evidence and critical_contradictions == 1:
        score = min(score, 60)
        applied.append("critical factual claim contradicted: score capped at 60")

    if caps.get("unsupported_high_impact_assumption") and (high_trust_evidence or retrieval_peak <= 0.0):
        score = min(score, 70)
        applied.append("unsupported high-impact assumption: score capped at 70")

    unsupported_high_claims = int(caps.get("unsupported_high_impact_claims", 0))
    if caps.get("evidence_required") and unsupported_high_claims >= 2:
        score = min(score, 55)
        applied.append("multiple high-impact claims lack source support: score capped at 55")
    elif caps.get("evidence_required") and unsupported_high_claims == 1:
        score = min(score, 65)
        applied.append("high-impact claim lacks source support: score capped at 65")

    if (
        caps.get("evidence_required")
        and int(caps.get("partial_support_claims", 0)) > 0
        and features.get("sample_overlap_stability", 1.0) <= 0.50
    ):
        score = min(score, 60)
        applied.append("partial source support without sample corroboration: score capped at 60")
    elif (
        caps.get("evidence_required")
        and int(caps.get("partial_support_claims", 0)) > 0
        and source_quality <= 0.30
    ):
        score = min(score, 50)
        applied.append("only partial support from low-provenance sources: score capped at 50")
    elif caps.get("evidence_required") and int(caps.get("partial_support_claims", 0)) > 0:
        score = min(score, 74)
        applied.append("some checkable claims only have partial source support: score capped at 74")

    if features.get("semantic_stability", 1.0) < 0.45:
        score = min(score, 75)
        applied.append("high semantic disagreement: score capped at 75")

    if features.get("sample_overlap_stability", 1.0) < 0.35:
        score = min(score, 55)
        applied.append("low sample evidence overlap: score capped at 55")

    if features.get("sample_conflict_rate", 0.0) >= 0.5:
        score = min(score, 60)
        applied.append("candidate answers conflict on numbers or recommendation polarity: score capped at 60")

    if (
        features.get("source_quality_score", 0.0) <= 0.30
        and features.get("sample_overlap_stability", 1.0) <= 0.50
        and features.get("retrieval_alignment_score", 0.0) < 0.80
    ):
        score = min(score, 70)
        applied.append("low-provenance single-sample evidence: score capped at 70")

    if caps.get("no_evidence_for_factual_current_question"):
        score = min(score, 45)
        applied.append("no evidence retrieval for source-required question: score capped at 45")

    return score, applied


def _feature(features: Dict[str, float], name: str) -> float:
    if name == "retrieval_alignment_score":
        return features.get("retrieval_alignment_score", features.get("source_quality_score", 0.0))
    if name == "retrieval_peak_score":
        return features.get(
            "retrieval_peak_score",
            features.get("retrieval_alignment_score", features.get("source_quality_score", 0.0)),
        )
    if name == "sample_overlap_stability":
        return features.get("sample_overlap_stability", features.get("semantic_stability", 0.0))
    return features.get(name, 0.0)
