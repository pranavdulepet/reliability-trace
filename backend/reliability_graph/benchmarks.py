from typing import Any, Dict, List, Optional

from .pipeline.scoring import compute_reliability_score


BUCKETS = [(0, 59), (60, 79), (80, 100)]
ABLATION_GROUPS = {
    "claim support": ["claim_support_rate"],
    "source quality": ["source_quality_score"],
    "semantic stability": ["semantic_stability"],
    "prompt robustness": ["prompt_flip_rate", "sycophancy_flip_rate"],
    "judge signals": ["judge_factuality_score", "judge_uncertainty_score"],
    "decision robustness": ["decision_robustness"],
}


def build_benchmark_report(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    labeled = [_normalize_row(row) for row in rows if _normalize_row(row) is not None]
    if not labeled:
        return {
            "status": "needs_labels",
            "label_count": 0,
            "ece": None,
            "brier": None,
            "buckets": [],
            "ablations": [],
            "summary": "No labeled completed runs yet. Label runs to calibrate score quality.",
        }

    buckets = [_bucket_report(labeled, low, high) for low, high in BUCKETS]
    ece = sum(bucket["weight"] * abs(bucket["avg_score"] - bucket["avg_correctness"]) for bucket in buckets if bucket["count"])
    brier = sum((item["score"] - item["correctness"]) ** 2 for item in labeled) / len(labeled)
    ablations = _ablation_report(labeled)
    return {
        "status": "local_calibration",
        "label_count": len(labeled),
        "ece": round(ece, 4),
        "brier": round(brier, 4),
        "buckets": buckets,
        "ablations": ablations,
        "summary": "Calibration is based on locally labeled runs and should be treated as directional until labels cover the target workload.",
    }


def _normalize_row(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    graph = row.get("graph")
    correctness = row.get("correctness")
    if not graph or correctness is None:
        return None
    score = float(graph["answer"]["reliability_score"]) / 100.0
    return {
        "run_id": row["run_id"],
        "score": score,
        "correctness": (float(correctness) - 1.0) / 4.0,
        "features": graph.get("features") or {},
    }


def _bucket_report(items: List[Dict[str, Any]], low: int, high: int) -> Dict[str, Any]:
    selected = [item for item in items if low <= item["score"] * 100 <= high]
    if not selected:
        return {
            "range": "%d-%d" % (low, high),
            "count": 0,
            "weight": 0.0,
            "avg_score": 0.0,
            "avg_correctness": 0.0,
        }
    return {
        "range": "%d-%d" % (low, high),
        "count": len(selected),
        "weight": len(selected) / float(len(items)),
        "avg_score": round(sum(item["score"] for item in selected) / len(selected), 4),
        "avg_correctness": round(sum(item["correctness"] for item in selected) / len(selected), 4),
    }


def _ablation_report(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for label, feature_names in ABLATION_GROUPS.items():
        deltas = []
        for item in items:
            features = dict(item["features"])
            if not features:
                continue
            base_score, _ = compute_reliability_score(features, {})
            ablated = dict(features)
            for feature_name in feature_names:
                if feature_name in {"prompt_flip_rate", "sycophancy_flip_rate"}:
                    ablated[feature_name] = 1.0
                else:
                    ablated[feature_name] = 0.0
            ablated_score, _ = compute_reliability_score(ablated, {})
            deltas.append((base_score - ablated_score) / 100.0)
        rows.append(
            {
                "signal": label,
                "avg_score_delta": round(sum(deltas) / len(deltas), 4) if deltas else 0.0,
                "run_count": len(deltas),
            }
        )
    rows.sort(key=lambda item: abs(item["avg_score_delta"]), reverse=True)
    return rows
