import argparse
import json
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.reliability_graph.evals import auroc, average_precision, brier_score, expected_calibration_error, redact_value
from backend.reliability_graph.pipeline.scoring import (
    DEFAULT_EVIDENCE_OPTIONAL_WEIGHTS,
    DEFAULT_EVIDENCE_REQUIRED_WEIGHTS,
    compute_reliability_score,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fit ReliabilityGraph score weights from benchmark eval results.")
    parser.add_argument("--input", required=True, help="Dev results.jsonl used for fitting.")
    parser.add_argument("--validation-input", default=None, help="Optional held-out results.jsonl used only for reporting.")
    parser.add_argument("--output", default="configs/reliability_score_weights.json")
    parser.add_argument("--trials", type=int, default=2500)
    parser.add_argument("--seed", type=int, default=7)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    train_rows = _scored_rows(_read_jsonl(Path(args.input)))
    validation_rows = _scored_rows(_read_jsonl(Path(args.validation_input))) if args.validation_input else []
    if len(train_rows) < 20:
        raise SystemExit("Need at least 20 scored benchmark rows to fit weights.")

    fit = fit_weights(train_rows, args.trials, args.seed)
    tune_rows, guard_rows = _split_tune_guard(train_rows, args.seed)
    train_metrics = evaluate_weights(train_rows, fit["required"], fit["optional"])
    validation_metrics = evaluate_weights(validation_rows, fit["required"], fit["optional"]) if validation_rows else None
    config = redact_value(
        {
            "schema_version": 1,
            "source": "benchmark_tuned",
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "git_sha": _git_sha(),
            "benchmark_scope": "official-style fixed-answer dev evals",
            "objective": (
                "Maximize bad-answer risk ranking AUROC/AUPRC with a false-safe penalty. "
                "Only linear signal weights are fitted; safety caps remain hand-audited policy."
            ),
            "input": str(args.input),
            "validation_input": str(args.validation_input) if args.validation_input else None,
            "evidence_required_weights": fit["required"],
            "evidence_optional_weights": fit["optional"],
            "metrics": {
                "train": train_metrics,
                "tune": evaluate_weights(tune_rows, fit["required"], fit["optional"]),
                "guard": evaluate_weights(guard_rows, fit["required"], fit["optional"]) if guard_rows else None,
                "validation": validation_metrics,
                "default_train": evaluate_weights(
                    train_rows,
                    DEFAULT_EVIDENCE_REQUIRED_WEIGHTS,
                    DEFAULT_EVIDENCE_OPTIONAL_WEIGHTS,
                ),
                "default_guard": evaluate_weights(
                    guard_rows,
                    DEFAULT_EVIDENCE_REQUIRED_WEIGHTS,
                    DEFAULT_EVIDENCE_OPTIONAL_WEIGHTS,
                )
                if guard_rows
                else None,
            },
            "rerun_when": [
                "scoring features or caps change",
                "provider, verifier, retrieval, or search behavior changes materially",
                "benchmark mix changes",
                "enough real user labels are collected for local calibration",
            ],
            "limitations": (
                "These weights are benchmark-tuned diagnostics, not a probability calibration. "
                "Held-out evals and real user labels remain required before making stronger calibration claims."
            ),
        }
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote %s" % output)
    print("train AUROC %.4f AUPRC %.4f false-safe %.4f" % (
        train_metrics["auroc"] or 0.0,
        train_metrics["auprc"] or 0.0,
        train_metrics["false_safe_rate"],
    ))
    return 0


def fit_weights(rows: List[Dict[str, Any]], trials: int, seed: int) -> Dict[str, Dict[str, float]]:
    rng = random.Random(seed)
    tune_rows, guard_rows = _split_tune_guard(rows, seed)
    best_required = dict(DEFAULT_EVIDENCE_REQUIRED_WEIGHTS)
    best_optional = dict(DEFAULT_EVIDENCE_OPTIONAL_WEIGHTS)
    default_guard = evaluate_weights(guard_rows, best_required, best_optional) if guard_rows else None
    best_objective = _combined_objective(tune_rows, guard_rows, best_required, best_optional)
    for _ in range(max(0, trials)):
        required = _candidate_weights(DEFAULT_EVIDENCE_REQUIRED_WEIGHTS, rng)
        optional = _candidate_weights(DEFAULT_EVIDENCE_OPTIONAL_WEIGHTS, rng)
        if not _passes_weight_constraints(required, optional):
            continue
        if _guard_regresses(guard_rows, default_guard, required, optional):
            continue
        objective = _combined_objective(tune_rows, guard_rows, required, optional)
        if objective > best_objective:
            best_objective = objective
            best_required = required
            best_optional = optional
    return {"required": best_required, "optional": best_optional}


def evaluate_weights(rows: List[Dict[str, Any]], required: Dict[str, float], optional: Dict[str, float]) -> Dict[str, Any]:
    labels = []
    risks = []
    scores = []
    correctness = []
    bad_count = 0
    false_safe = 0
    for row in rows:
        score, _caps = _score_row(row, required, optional)
        risk = 1.0 - (score / 100.0)
        bad = bool(row["metrics"].get("bad_answer"))
        labels.append(1 if bad else 0)
        risks.append(risk)
        scores.append(score / 100.0)
        correctness.append(float(row["metrics"]["correctness"]))
        if bad:
            bad_count += 1
            if score >= 75:
                false_safe += 1
    return {
        "count": len(rows),
        "bad_count": bad_count,
        "auroc": _rounded(auroc(labels, risks)),
        "auprc": _rounded(average_precision(labels, risks)),
        "ece": _rounded(expected_calibration_error(scores, correctness)),
        "brier": _rounded(brier_score(scores, correctness)),
        "false_safe_rate": _rounded(false_safe / float(bad_count or 1)),
        "mean_score": _rounded(sum(scores) / float(len(scores) or 1)),
    }


def _objective(rows: List[Dict[str, Any]], required: Dict[str, float], optional: Dict[str, float]) -> float:
    metrics = evaluate_weights(rows, required, optional)
    auroc_value = metrics["auroc"] or 0.0
    auprc_value = metrics["auprc"] or 0.0
    false_safe = metrics["false_safe_rate"]
    regularization = _weight_distance(required, DEFAULT_EVIDENCE_REQUIRED_WEIGHTS) + _weight_distance(
        optional,
        DEFAULT_EVIDENCE_OPTIONAL_WEIGHTS,
    )
    return auprc_value + (0.25 * auroc_value) - (3.0 * false_safe) - (0.015 * regularization)


def _combined_objective(
    tune_rows: List[Dict[str, Any]],
    guard_rows: List[Dict[str, Any]],
    required: Dict[str, float],
    optional: Dict[str, float],
) -> float:
    if not guard_rows:
        return _objective(tune_rows, required, optional)
    return _objective(tune_rows, required, optional) + (0.50 * _objective(guard_rows, required, optional))


def _guard_regresses(
    guard_rows: List[Dict[str, Any]],
    default_guard: Optional[Dict[str, Any]],
    required: Dict[str, float],
    optional: Dict[str, float],
) -> bool:
    if not guard_rows or not default_guard:
        return False
    metrics = evaluate_weights(guard_rows, required, optional)
    for name in ("auroc", "auprc"):
        candidate = metrics.get(name)
        default = default_guard.get(name)
        if candidate is not None and default is not None and candidate + 0.005 < default:
            return True
    return metrics["false_safe_rate"] > default_guard["false_safe_rate"] + 0.001


def _split_tune_guard(rows: List[Dict[str, Any]], seed: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rng = random.Random(seed)
    by_benchmark: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_benchmark.setdefault(str(row.get("benchmark") or "unknown"), []).append(row)
    tune_rows: List[Dict[str, Any]] = []
    guard_rows: List[Dict[str, Any]] = []
    for group in by_benchmark.values():
        group = list(group)
        rng.shuffle(group)
        guard_count = max(1, int(round(len(group) * 0.20))) if len(group) >= 10 else 0
        guard_rows.extend(group[:guard_count])
        tune_rows.extend(group[guard_count:])
    return tune_rows or rows, guard_rows


def _score_row(row: Dict[str, Any], required: Dict[str, float], optional: Dict[str, float]) -> Tuple[int, List[str]]:
    return compute_reliability_score(row.get("features") or {}, _derive_caps(row), required, optional)


def _derive_caps(row: Dict[str, Any]) -> Dict[str, Any]:
    graph = row.get("graph") or {}
    features = row.get("features") or {}
    assessments = [item for item in graph.get("claim_assessments", []) if item.get("status") != "not_checkable"]
    claims_by_id = {claim.get("claim_id"): claim for claim in graph.get("claims", [])}
    evidence_required = float(features.get("evidence_required", 1.0)) >= 0.5
    high_unsupported = [
        assessment
        for assessment in assessments
        if assessment.get("status") in {"insufficient_evidence", "not_found"}
        and claims_by_id.get(assessment.get("claim_id"), {}).get("importance") == "high"
    ]
    return {
        "evidence_required": evidence_required,
        "source_grounded_summary": _is_source_grounded_summary_question(str((graph.get("run") or {}).get("question") or "")),
        "partial_support_claims": len([item for item in assessments if item.get("status") == "partially_supported"]),
        "critical_factual_contradictions": len(
            [
                item
                for item in assessments
                if item.get("status") == "contradicted"
                and claims_by_id.get(item.get("claim_id"), {}).get("importance") == "high"
            ]
        ),
        "unsupported_high_impact_claims": len(high_unsupported),
        "unsupported_high_impact_assumption": (
            evidence_required or bool((graph.get("decision_analysis") or {}).get("applicable"))
        )
        and any(
            item.get("importance") == "high" and item.get("evidence_status") != "supported"
            for item in graph.get("assumptions", [])
        ),
        "no_evidence_for_factual_current_question": evidence_required and not _has_external_evidence(graph.get("evidence") or []),
    }


def _has_external_evidence(evidence: List[Dict[str, Any]]) -> bool:
    return any(item.get("source_type") not in {"system_trace", "model_output", "internal_policy"} for item in evidence)


def _is_source_grounded_summary_question(question: str) -> bool:
    lowered = question.strip().lower()
    return lowered.startswith(("summarize ", "summarise ", "summary of ", "write a summary", "provide a summary"))


def _candidate_weights(base: Dict[str, float], rng: random.Random) -> Dict[str, float]:
    keys = list(base.keys())
    random_weights = _random_simplex(keys, rng)
    blend = rng.uniform(0.20, 0.85)
    candidate = {key: (blend * base[key]) + ((1.0 - blend) * random_weights[key]) for key in keys}
    return _normalize(candidate)


def _random_simplex(keys: List[str], rng: random.Random) -> Dict[str, float]:
    values = {key: rng.expovariate(1.0) for key in keys}
    return _normalize(values)


def _normalize(weights: Dict[str, float]) -> Dict[str, float]:
    total = sum(max(0.0, value) for value in weights.values()) or 1.0
    return {key: round(max(0.0, value) / total, 6) for key, value in weights.items()}


def _passes_weight_constraints(required: Dict[str, float], optional: Dict[str, float]) -> bool:
    source_group = (
        required["claim_support_rate"]
        + required["retrieval_alignment_score"]
        + required["source_quality_score"]
        + required["retrieval_peak_score"]
    )
    sample_group = optional["sample_overlap_stability"] + optional["semantic_stability"]
    return max(required.values()) <= 0.45 and max(optional.values()) <= 0.55 and source_group >= 0.55 and sample_group >= 0.55


def _weight_distance(left: Dict[str, float], right: Dict[str, float]) -> float:
    return sum(abs(left.get(key, 0.0) - right.get(key, 0.0)) for key in set(left) | set(right))


def _scored_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        row
        for row in rows
        if row.get("metrics", {}).get("correctness") is not None
        and row.get("features")
        and row.get("graph")
    ]


def _read_jsonl(path: Optional[Path]) -> List[Dict[str, Any]]:
    if path is None:
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _rounded(value: Optional[float]) -> Optional[float]:
    return round(value, 4) if value is not None else None


def _git_sha() -> Optional[str]:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
