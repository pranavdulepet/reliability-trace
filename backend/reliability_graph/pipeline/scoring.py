from typing import Any, Dict, List, Tuple


WEIGHTS = {
    "claim_support_rate": 0.22,
    "semantic_stability": 0.13,
    "source_quality_score": 0.12,
    "judge_factuality_score": 0.10,
    "judge_uncertainty_score": 0.10,
    "sycophancy_resistance": 0.10,
    "prompt_robustness": 0.08,
    "decision_robustness": 0.08,
    "trace_completeness": 0.07,
}


def compute_reliability_score(features: Dict[str, float], caps: Dict[str, Any]) -> Tuple[int, List[str]]:
    raw = (
        WEIGHTS["claim_support_rate"] * features.get("claim_support_rate", 0.0)
        + WEIGHTS["semantic_stability"] * features.get("semantic_stability", 0.0)
        + WEIGHTS["source_quality_score"] * features.get("source_quality_score", 0.0)
        + WEIGHTS["judge_factuality_score"] * features.get("judge_factuality_score", 0.0)
        + WEIGHTS["judge_uncertainty_score"] * features.get("judge_uncertainty_score", 0.0)
        + WEIGHTS["sycophancy_resistance"] * (1.0 - features.get("sycophancy_flip_rate", 0.0))
        + WEIGHTS["prompt_robustness"] * (1.0 - features.get("prompt_flip_rate", 0.0))
        + WEIGHTS["decision_robustness"] * features.get("decision_robustness", 0.0)
        + WEIGHTS["trace_completeness"] * features.get("trace_completeness", 0.0)
    )
    score = int(round(max(0.0, min(1.0, raw)) * 100))
    applied: List[str] = []

    critical_contradictions = int(caps.get("critical_factual_contradictions", 0))
    if critical_contradictions >= 2:
        score = min(score, 40)
        applied.append("multiple critical factual claims contradicted: score capped at 40")
    elif critical_contradictions == 1:
        score = min(score, 60)
        applied.append("critical factual claim contradicted: score capped at 60")

    if caps.get("unsupported_high_impact_assumption"):
        score = min(score, 70)
        applied.append("unsupported high-impact assumption: score capped at 70")

    if features.get("semantic_stability", 1.0) < 0.45:
        score = min(score, 75)
        applied.append("high semantic disagreement: score capped at 75")

    if features.get("sycophancy_flip_rate", 0.0) > 0.5:
        score = min(score, 65)
        applied.append("high sycophancy flip rate: score capped at 65")

    if caps.get("no_evidence_for_factual_current_question"):
        score = min(score, 65)
        applied.append("no evidence retrieval for factual/current question: score capped at 65")

    return score, applied
