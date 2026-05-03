import csv
import json
import math
import random
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Tuple

from .pipeline import ReliabilityPipeline
from .pipeline.scoring import compute_reliability_score
from .retrieval import build_chunks

ProviderKeyResolver = Callable[[str], Awaitable[Optional[str]]]

RAGTRUTH_RESPONSE_URL = "https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/dataset/response.jsonl"
RAGTRUTH_SOURCE_URL = "https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/dataset/source_info.jsonl"
SELFCHECK_ROWS_URL = (
    "https://datasets-server.huggingface.co/rows?"
    "dataset=potsawee%2Fwiki_bio_gpt3_hallucination&config=default&split=evaluation"
)
SIMPLEQA_URL = "https://openaipublic.blob.core.windows.net/simple-evals/simple_qa_test_set.csv"

MAX_DOWNLOAD_BYTES = 80_000_000
MAX_EVAL_SOURCE_CHARS = 160_000
MAX_EXAMPLE_ANSWER_CHARS = 5_000

SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"tml-[A-Za-z0-9_-]{12,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"AIza[A-Za-z0-9_-]{20,}"),
]

ABLATION_GROUPS = {
    "claim support": ["claim_support_rate"],
    "source quality": ["source_quality_score"],
    "sample consistency": ["semantic_stability"],
    "prompt robustness": ["prompt_flip_rate", "sycophancy_flip_rate"],
    "judge signals": ["judge_factuality_score", "judge_uncertainty_score"],
    "decision robustness": ["decision_robustness"],
}


@dataclass
class EvalExample:
    benchmark: str
    example_id: str
    question: str
    answer: Optional[str]
    source_texts: List[str]
    gold_labels: Dict[str, Any]
    metadata: Dict[str, Any]


@dataclass
class LoadedExamples:
    benchmark: str
    examples: List[EvalExample]
    notes: List[str]


def load_benchmark_examples(
    benchmark: str,
    cache_dir: Path,
    limit: Optional[int],
    seed: int,
    offline: bool = False,
) -> LoadedExamples:
    benchmark = benchmark.lower().strip()
    cache_dir.mkdir(parents=True, exist_ok=True)
    if benchmark == "ragtruth":
        loaded = _load_ragtruth(cache_dir, offline)
    elif benchmark == "selfcheck":
        loaded = _load_selfcheck(cache_dir, limit, offline)
    elif benchmark == "simpleqa":
        loaded = _load_simpleqa(cache_dir, offline)
    else:
        raise ValueError("unsupported benchmark: %s" % benchmark)
    return LoadedExamples(benchmark, _sample_examples(loaded.examples, limit, seed), loaded.notes)


def ragtruth_to_example(response: Dict[str, Any], source: Optional[Dict[str, Any]]) -> EvalExample:
    source = source or {}
    source_info = source.get("source_info")
    labels = response.get("labels") or []
    quality = str(response.get("quality") or "good")
    source_texts = _source_info_texts(source_info)
    question = _source_question(source_info) or str(source.get("prompt") or response.get("prompt") or "Evaluate the RAG answer.")
    label_types = sorted({str(label.get("label_type") or "hallucination") for label in labels if isinstance(label, dict)})
    return EvalExample(
        benchmark="ragtruth",
        example_id=str(response.get("id") or response.get("response_id") or "unknown"),
        question=question[:12000],
        answer=str(response.get("response") or "")[:MAX_EXAMPLE_ANSWER_CHARS],
        source_texts=source_texts,
        gold_labels={
            "has_hallucination": bool(labels),
            "bad_answer": bool(labels) or quality in {"incorrect_refusal", "truncated"},
            "label_count": len(labels),
            "label_types": label_types,
            "quality": quality,
        },
        metadata={
            "source_id": str(response.get("source_id") or source.get("source_id") or ""),
            "task_type": source.get("task_type"),
            "split": response.get("split"),
            "source": source.get("source"),
        },
    )


def selfcheck_to_example(record: Dict[str, Any]) -> EvalExample:
    annotations = _annotation_labels(record.get("annotation"))
    bad_sentence_count = sum(1 for label in annotations if _selfcheck_label_is_bad(label))
    sentence_count = len(annotations)
    samples = _string_list(record.get("gpt3_text_samples"))[:20]
    return EvalExample(
        benchmark="selfcheck",
        example_id=str(record.get("wiki_bio_test_idx") or record.get("id") or "unknown"),
        question="Is this Wikipedia-style passage factually supported by the reference passage?",
        answer=str(record.get("gpt3_text") or "")[:MAX_EXAMPLE_ANSWER_CHARS],
        source_texts=[str(record.get("wiki_bio_text") or "")[:MAX_EVAL_SOURCE_CHARS]],
        gold_labels={
            "bad_answer": bad_sentence_count > 0,
            "bad_sentence_count": bad_sentence_count,
            "sentence_count": sentence_count,
            "bad_sentence_rate": bad_sentence_count / float(sentence_count or 1),
            "sentence_labels": annotations,
        },
        metadata={
            "sample_answers": samples,
            "dataset": "potsawee/wiki_bio_gpt3_hallucination",
        },
    )


def simpleqa_to_example(row: Dict[str, Any], oracle_answer: bool = True) -> EvalExample:
    question = str(row.get("problem") or row.get("question") or "")
    target = str(row.get("answer") or row.get("target") or "")
    return EvalExample(
        benchmark="simpleqa",
        example_id=str(row.get("id") or _stable_id(question)),
        question=question[:12000],
        answer=target[:MAX_EXAMPLE_ANSWER_CHARS] if oracle_answer else None,
        source_texts=[],
        gold_labels={
            "target": target,
            "bad_answer": False,
            "simpleqa_grade": "correct" if oracle_answer else "ungraded",
            "is_correct": True if oracle_answer else None,
            "grading_mode": "strict_normalized_first",
        },
        metadata={"dataset": "openai/simple-evals/simpleqa"},
    )


async def run_eval_example(
    example: EvalExample,
    resolve_key: Optional[ProviderKeyResolver] = None,
    live_provider: Optional[str] = None,
    model: Optional[str] = None,
    samples: int = 3,
) -> Dict[str, Any]:
    fixed_answer = example.answer is not None
    run_samples = max(1, min(5, samples))
    candidate_samples = _string_list(example.metadata.get("sample_answers"))
    if fixed_answer and candidate_samples:
        run_samples = max(run_samples, min(5, 1 + len(candidate_samples)))
    run = {
        "run_id": "eval_%s_%s" % (example.benchmark, _stable_id(example.example_id)),
        "question": example.question,
        "provider": live_provider if live_provider and not fixed_answer else "local",
        "model": model,
        "samples": run_samples,
        "max_cost_usd": 1.0,
        "use_live_provider": bool(live_provider and not fixed_answer),
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "graph": None,
        "error": None,
        "attachment_document_ids": ["eval_source_%d" % index for index, _ in enumerate(example.source_texts, start=1)],
        "prior_context": [],
    }
    if fixed_answer:
        run["answer_override"] = example.answer
        run["candidate_answer_overrides"] = candidate_samples
    resolver = resolve_key or _empty_key_resolver
    pipeline = ReliabilityPipeline(retrieval_chunks=_eval_chunks(example))
    events = []
    async for event in pipeline.run(run, resolver):
        events.append(event)
    graph = events[-1]["graph"]
    labels = _labels_for_graph(example, graph)
    metrics = _example_metrics(graph, labels)
    return redact_value(
        {
            "benchmark": example.benchmark,
            "example_id": example.example_id,
            "question": example.question,
            "answer": graph["answer"]["final_answer"],
            "graph": graph,
            "score": graph["answer"]["reliability_score"],
            "verdict": graph["answer"]["verdict"],
            "evidence_status": graph["answer"]["evidence_status"],
            "claim_assessments": graph["claim_assessments"],
            "features": graph["features"],
            "labels": labels,
            "metrics": metrics,
            "metadata": example.metadata,
        }
    )


async def _empty_key_resolver(_provider: str) -> Optional[str]:
    return None


def summarize_eval_results(results: List[Dict[str, Any]], notes: Optional[List[str]] = None) -> Dict[str, Any]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for result in results:
        groups.setdefault(str(result["benchmark"]), []).append(result)
    by_benchmark = {name: _summarize_group(items) for name, items in sorted(groups.items())}
    return redact_value(
        {
            "status": "ok" if results else "no_results",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "result_count": len(results),
            "benchmarks": by_benchmark,
            "overall": _summarize_group(results),
            "ablations": ablation_report(results),
            "notes": notes or [],
        }
    )


def ablation_report(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for label, feature_names in ABLATION_GROUPS.items():
        deltas = []
        for result in results:
            features = dict(result.get("features") or {})
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
                "avg_score_delta": _rounded(_mean(deltas)),
                "run_count": len(deltas),
            }
        )
    rows.sort(key=lambda item: abs(item["avg_score_delta"]), reverse=True)
    return rows


def build_markdown_report(summary: Dict[str, Any], results: List[Dict[str, Any]]) -> str:
    lines = [
        "# ReliabilityGraph Eval Report",
        "",
        "This report is a pilot benchmark audit, not a leaderboard claim. Scores are diagnostic.",
        "",
        "## Setup",
        "",
        "- Benchmarks: RAGTruth, SelfCheckGPT WikiBio, SimpleQA.",
        "- Metrics: AUROC, AUPRC, Spearman, ECE, Brier, risk coverage, false-safe rate.",
        "- Calibration metrics treat the ReliabilityGraph score as an eval signal only.",
        "",
    ]
    notes = summary.get("notes") or []
    if notes:
        lines.extend(["## Notes", ""])
        lines.extend(["- %s" % _escape_md(str(note)) for note in notes])
        lines.append("")
    lines.extend(["## Aggregate Metrics", ""])
    lines.append("| Benchmark | N | AUROC | AUPRC | Spearman | ECE | Brier | False-safe |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for benchmark, metrics in sorted((summary.get("benchmarks") or {}).items()):
        lines.append(
            "| %s | %d | %s | %s | %s | %s | %s | %s |"
            % (
                _escape_md(benchmark),
                metrics.get("count", 0),
                _fmt(metrics.get("auroc")),
                _fmt(metrics.get("auprc")),
                _fmt(metrics.get("spearman_score_correctness")),
                _fmt(metrics.get("ece")),
                _fmt(metrics.get("brier")),
                _fmt(metrics.get("false_safe_rate")),
            )
        )
    lines.extend(["", "## Ablations", ""])
    lines.append("| Signal removed | Avg score delta | Runs |")
    lines.append("| --- | ---: | ---: |")
    for row in summary.get("ablations") or []:
        lines.append("| %s | %s | %d |" % (_escape_md(row["signal"]), _fmt(row["avg_score_delta"]), row["run_count"]))
    lines.extend(["", "## Failure Cases", ""])
    lines.append("| Benchmark | Example | Score | Verdict | Label | Why it matters |")
    lines.append("| --- | --- | ---: | --- | --- | --- |")
    failures = _failure_cases(results)
    if not failures:
        lines.append("| none | none | - | - | - | No false-safe cases in this run. |")
    for result in failures:
        labels = result.get("labels") or {}
        lines.append(
            "| %s | %s | %s | %s | %s | %s |"
            % (
                _escape_md(result["benchmark"]),
                _escape_md(result["example_id"]),
                _fmt(result.get("score")),
                _escape_md(result.get("verdict")),
                _escape_md(_label_summary(labels)),
                _escape_md((result.get("evidence_status") or "")[:160]),
            )
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- RAGTruth evaluates source-grounded hallucination behavior, not broad open-web truth.",
            "- SelfCheckGPT evaluates consistency against sampled passages and WikiBio annotations; agreement can still be wrong.",
            "- SimpleQA strict matching is intentionally conservative; ambiguous answers are marked `needs_review`.",
            "- Live provider slices measure end-to-end behavior and can vary across time, model, and provider settings.",
            "",
        ]
    )
    return "\n".join(lines)


def write_eval_outputs(output_dir: Path, results: List[Dict[str, Any]], summary: Dict[str, Any]) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "results.jsonl"
    summary_path = output_dir / "summary.json"
    report_path = output_dir / "report.md"
    with results_path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(redact_value(result), sort_keys=True) + "\n")
    summary_path.write_text(json.dumps(redact_value(summary), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_path.write_text(build_markdown_report(summary, results), encoding="utf-8")
    return {"results": str(results_path), "summary": str(summary_path), "report": str(report_path)}


def grade_simpleqa_prediction(question: str, target: str, predicted: str) -> str:
    del question
    predicted = (predicted or "").strip()
    if not predicted:
        return "not_attempted"
    norm_target = normalize_answer(target)
    norm_predicted = normalize_answer(predicted)
    if not norm_target:
        return "needs_review"
    if _looks_like_refusal(norm_predicted) and norm_target not in norm_predicted:
        return "not_attempted"
    if _contains_normalized_answer(norm_predicted, norm_target):
        return "correct"
    target_tokens = set(norm_target.split())
    predicted_tokens = set(norm_predicted.split())
    if target_tokens and predicted_tokens and len(target_tokens & predicted_tokens) / float(len(target_tokens)) >= 0.5:
        return "needs_review"
    return "incorrect"


def normalize_answer(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"['`]", "", text)
    text = re.sub(r"[^a-z0-9.]+", " ", text)
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        cleaned = value
        for pattern in SECRET_PATTERNS:
            cleaned = pattern.sub(lambda match: (match.group(1) if match.lastindex else "") + "[redacted]", cleaned)
        return cleaned
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in {"api_key", "authorization", "auth_header", "secret"}:
                redacted[key] = "[redacted]"
            else:
                redacted[key] = redact_value(item)
        return redacted
    return value


def example_to_json(example: EvalExample) -> Dict[str, Any]:
    return asdict(example)


def _load_ragtruth(cache_dir: Path, offline: bool) -> LoadedExamples:
    notes: List[str] = []
    response_path = cache_dir / "ragtruth_response.jsonl"
    source_path = cache_dir / "ragtruth_source_info.jsonl"
    if not offline:
        _download_if_missing(RAGTRUTH_RESPONSE_URL, response_path, notes)
        _download_if_missing(RAGTRUTH_SOURCE_URL, source_path, notes)
    if response_path.exists() and source_path.exists():
        sources = {str(row.get("source_id")): row for row in _read_jsonl(source_path)}
        examples = [ragtruth_to_example(row, sources.get(str(row.get("source_id")))) for row in _read_jsonl(response_path)]
        examples = [example for example in examples if example.answer]
        return LoadedExamples("ragtruth", examples, notes)
    notes.append("RAGTruth cache missing; using tiny fixture examples.")
    return LoadedExamples("ragtruth", _ragtruth_fixtures(), notes)


def _load_selfcheck(cache_dir: Path, limit: Optional[int], offline: bool) -> LoadedExamples:
    notes: List[str] = []
    path = cache_dir / "selfcheck_rows.json"
    if not path.exists() and not offline:
        try:
            rows = _download_selfcheck_rows(max(limit or 238, 1))
            path.write_text(json.dumps(rows), encoding="utf-8")
            notes.append("Downloaded SelfCheckGPT WikiBio rows from Hugging Face datasets server.")
        except (OSError, urllib.error.URLError, ValueError) as exc:
            notes.append("SelfCheckGPT download failed: %s" % str(exc)[:180])
    if path.exists():
        rows = json.loads(path.read_text(encoding="utf-8"))
        return LoadedExamples("selfcheck", [selfcheck_to_example(row) for row in rows], notes)
    notes.append("SelfCheckGPT cache missing; using tiny fixture examples.")
    return LoadedExamples("selfcheck", _selfcheck_fixtures(), notes)


def _load_simpleqa(cache_dir: Path, offline: bool) -> LoadedExamples:
    notes: List[str] = []
    path = cache_dir / "simpleqa_test_set.csv"
    if not offline:
        _download_if_missing(SIMPLEQA_URL, path, notes)
    if path.exists():
        rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
        return LoadedExamples("simpleqa", [simpleqa_to_example(row, oracle_answer=True) for row in rows], notes)
    notes.append("SimpleQA cache missing; using tiny fixture examples.")
    return LoadedExamples("simpleqa", _simpleqa_fixtures(), notes)


def _download_if_missing(url: str, path: Path, notes: List[str]) -> None:
    if path.exists():
        return
    try:
        path.write_text(_download_text(url), encoding="utf-8")
        notes.append("Downloaded %s." % urllib.parse.urlparse(url).netloc)
    except (OSError, urllib.error.URLError, ValueError) as exc:
        notes.append("Download failed for %s: %s" % (url, str(exc)[:180]))


def _download_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "ReliabilityGraphEval/0.1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        body = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(body) > MAX_DOWNLOAD_BYTES:
        raise ValueError("download exceeded %d bytes" % MAX_DOWNLOAD_BYTES)
    return body.decode("utf-8")


def _download_selfcheck_rows(target_count: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0
    while len(rows) < target_count:
        length = min(100, target_count - len(rows))
        data = json.loads(_download_text("%s&offset=%d&length=%d" % (SELFCHECK_ROWS_URL, offset, length)))
        page = [item["row"] for item in data.get("rows", []) if "row" in item]
        if not page:
            break
        rows.extend(page)
        offset += len(page)
    return rows


def _read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _sample_examples(examples: List[EvalExample], limit: Optional[int], seed: int) -> List[EvalExample]:
    if limit is None or limit >= len(examples):
        return examples
    rng = random.Random(seed)
    return rng.sample(examples, limit)


def _eval_chunks(example: EvalExample) -> List[Dict[str, Any]]:
    chunks: List[Dict[str, Any]] = []
    for source_index, source_text in enumerate(example.source_texts, start=1):
        document_id = "eval_doc_%d" % source_index
        title = "Benchmark source %d" % source_index
        for chunk in build_chunks((source_text or "")[:MAX_EVAL_SOURCE_CHARS]):
            chunks.append(
                {
                    **chunk,
                    "chunk_id": "eval_chunk_%d" % (len(chunks) + 1),
                    "document_id": document_id,
                    "title": title,
                    "source_url": None,
                    "source_type": "benchmark_source",
                }
            )
    return chunks


def _labels_for_graph(example: EvalExample, graph: Dict[str, Any]) -> Dict[str, Any]:
    labels = dict(example.gold_labels)
    if example.benchmark.startswith("simpleqa"):
        grade = grade_simpleqa_prediction(example.question, str(labels.get("target") or ""), graph["answer"]["final_answer"])
        labels["simpleqa_grade"] = grade
        labels["bad_answer"] = grade == "incorrect"
        labels["is_correct"] = grade == "correct"
        labels["include_in_calibration"] = grade != "needs_review"
    else:
        labels["include_in_calibration"] = True
        labels["is_correct"] = not bool(labels.get("bad_answer"))
    return labels


def _example_metrics(graph: Dict[str, Any], labels: Dict[str, Any]) -> Dict[str, Any]:
    score = float(graph["answer"]["reliability_score"]) / 100.0
    correctness = labels.get("is_correct")
    if correctness is None or labels.get("include_in_calibration") is False:
        correctness_value = None
    else:
        correctness_value = 1.0 if correctness else 0.0
    relation_detected = any(
        item.get("relation") in {"not_found", "contradicted"} for item in graph.get("claim_assessments", [])
    )
    return {
        "score": score,
        "risk_score": 1.0 - score,
        "correctness": correctness_value,
        "bad_answer": bool(labels.get("bad_answer")),
        "relation_detected": relation_detected,
        "false_safe": bool(labels.get("bad_answer"))
        and (graph["answer"].get("verdict") == "rely" or graph["answer"]["reliability_score"] >= 75),
    }


def _summarize_group(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    scored = [item for item in items if item.get("metrics", {}).get("correctness") is not None]
    labels = [1 if item["metrics"]["bad_answer"] else 0 for item in scored]
    risk_scores = [float(item["metrics"]["risk_score"]) for item in scored]
    correctness = [float(item["metrics"]["correctness"]) for item in scored]
    scores = [float(item["metrics"]["score"]) for item in scored]
    bad_items = [item for item in scored if item["metrics"]["bad_answer"]]
    relation_hits = [
        item for item in bad_items if item.get("metrics", {}).get("relation_detected")
    ]
    return {
        "count": len(items),
        "scored_count": len(scored),
        "bad_count": sum(labels),
        "mean_score": _rounded(_mean(scores)),
        "mean_correctness": _rounded(_mean(correctness)),
        "auroc": _rounded(auroc(labels, risk_scores)),
        "auprc": _rounded(average_precision(labels, risk_scores)),
        "spearman_score_correctness": _rounded(spearman(scores, correctness)),
        "ece": _rounded(expected_calibration_error(scores, correctness)),
        "brier": _rounded(brier_score(scores, correctness)),
        "false_safe_rate": _rounded(_mean([1.0 if item["metrics"]["false_safe"] else 0.0 for item in bad_items])),
        "claim_relation_recall_on_bad": _rounded(len(relation_hits) / float(len(bad_items) or 1)) if bad_items else None,
        "coverage_score_ge_75": _risk_coverage(scored, 0.75),
        "coverage_score_ge_60": _risk_coverage(scored, 0.60),
    }


def auroc(labels: List[int], scores: List[float]) -> Optional[float]:
    positives = [score for label, score in zip(labels, scores) if label == 1]
    negatives = [score for label, score in zip(labels, scores) if label == 0]
    if not positives or not negatives:
        return None
    wins = 0.0
    for positive in positives:
        for negative in negatives:
            if positive > negative:
                wins += 1.0
            elif positive == negative:
                wins += 0.5
    return wins / float(len(positives) * len(negatives))


def average_precision(labels: List[int], scores: List[float]) -> Optional[float]:
    positives = sum(labels)
    if positives == 0:
        return None
    paired = sorted(zip(scores, labels), key=lambda item: item[0], reverse=True)
    hits = 0
    precision_sum = 0.0
    for index, (_score, label) in enumerate(paired, start=1):
        if label == 1:
            hits += 1
            precision_sum += hits / float(index)
    return precision_sum / float(positives)


def spearman(left: List[float], right: List[float]) -> Optional[float]:
    if len(left) < 2 or len(left) != len(right):
        return None
    return pearson(_ranks(left), _ranks(right))


def pearson(left: List[float], right: List[float]) -> Optional[float]:
    if len(left) < 2 or len(left) != len(right):
        return None
    mean_left = _mean(left)
    mean_right = _mean(right)
    numerator = sum((a - mean_left) * (b - mean_right) for a, b in zip(left, right))
    denom_left = math.sqrt(sum((a - mean_left) ** 2 for a in left))
    denom_right = math.sqrt(sum((b - mean_right) ** 2 for b in right))
    if denom_left == 0 or denom_right == 0:
        return None
    return numerator / (denom_left * denom_right)


def expected_calibration_error(confidences: List[float], correctness: List[float], bins: int = 10) -> Optional[float]:
    if not confidences or len(confidences) != len(correctness):
        return None
    total = float(len(confidences))
    ece = 0.0
    for index in range(bins):
        low = index / float(bins)
        high = (index + 1) / float(bins)
        selected = [
            (confidence, correct)
            for confidence, correct in zip(confidences, correctness)
            if (low <= confidence < high) or (index == bins - 1 and confidence == high)
        ]
        if not selected:
            continue
        avg_conf = _mean([item[0] for item in selected])
        avg_correct = _mean([item[1] for item in selected])
        ece += (len(selected) / total) * abs(avg_conf - avg_correct)
    return ece


def brier_score(confidences: List[float], correctness: List[float]) -> Optional[float]:
    if not confidences or len(confidences) != len(correctness):
        return None
    return _mean([(confidence - correct) ** 2 for confidence, correct in zip(confidences, correctness)])


def _risk_coverage(items: List[Dict[str, Any]], threshold: float) -> Dict[str, Optional[float]]:
    selected = [item for item in items if float(item["metrics"]["score"]) >= threshold]
    if not selected:
        return {"coverage": 0.0, "correctness": None}
    return {
        "coverage": _rounded(len(selected) / float(len(items) or 1)),
        "correctness": _rounded(_mean([float(item["metrics"]["correctness"]) for item in selected])),
    }


def _ranks(values: List[float]) -> List[float]:
    sorted_pairs = sorted((value, index) for index, value in enumerate(values))
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(sorted_pairs):
        end = cursor
        while end + 1 < len(sorted_pairs) and sorted_pairs[end + 1][0] == sorted_pairs[cursor][0]:
            end += 1
        rank = (cursor + end + 2) / 2.0
        for _, original_index in sorted_pairs[cursor : end + 1]:
            ranks[original_index] = rank
        cursor = end + 1
    return ranks


def _failure_cases(results: List[Dict[str, Any]], limit: int = 12) -> List[Dict[str, Any]]:
    failures = [result for result in results if result.get("metrics", {}).get("false_safe")]
    failures.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
    return failures[:limit]


def _source_info_texts(source_info: Any) -> List[str]:
    if isinstance(source_info, str):
        return [source_info[:MAX_EVAL_SOURCE_CHARS]]
    if isinstance(source_info, dict):
        if isinstance(source_info.get("passages"), str):
            return [source_info["passages"][:MAX_EVAL_SOURCE_CHARS]]
        texts = []
        for key in ["source", "context", "article", "document"]:
            if isinstance(source_info.get(key), str):
                texts.append(source_info[key][:MAX_EVAL_SOURCE_CHARS])
        if texts:
            return texts
        return [json.dumps(source_info, sort_keys=True)[:MAX_EVAL_SOURCE_CHARS]]
    if source_info is None:
        return []
    return [str(source_info)[:MAX_EVAL_SOURCE_CHARS]]


def _source_question(source_info: Any) -> Optional[str]:
    if isinstance(source_info, dict) and isinstance(source_info.get("question"), str):
        return source_info["question"]
    return None


def _annotation_labels(annotation: Any) -> List[str]:
    if isinstance(annotation, list):
        return [_annotation_label(item) for item in annotation]
    if isinstance(annotation, dict):
        return [_annotation_label(item) for item in annotation.values()]
    if annotation is None:
        return []
    return [_annotation_label(annotation)]


def _annotation_label(item: Any) -> str:
    if isinstance(item, dict):
        for key in ["label", "annotation", "factuality", "is_factual"]:
            if key in item:
                return str(item[key]).lower().strip()
    return str(item).lower().strip()


def _selfcheck_label_is_bad(label: str) -> bool:
    label = label.lower().strip()
    return any(term in label for term in ["inaccurate", "incorrect", "false", "hallucinated", "major", "minor"])


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _contains_normalized_answer(predicted: str, target: str) -> bool:
    if predicted == target:
        return True
    if target and target in predicted:
        return True
    target_tokens = target.split()
    predicted_tokens = predicted.split()
    if len(target_tokens) > 1 and all(token in predicted_tokens for token in target_tokens):
        return True
    return False


def _looks_like_refusal(normalized_text: str) -> bool:
    return any(
        phrase in normalized_text
        for phrase in [
            "i dont know",
            "cannot answer",
            "cant answer",
            "need more context",
            "without researching",
            "unable to answer",
            "cannot verify",
        ]
    )


def _mean(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / float(len(values))


def _rounded(value: Optional[float]) -> Optional[float]:
    return round(value, 4) if value is not None else None


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return "%.4f" % value
    return str(value)


def _escape_md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _label_summary(labels: Dict[str, Any]) -> str:
    if "simpleqa_grade" in labels:
        return str(labels["simpleqa_grade"])
    if labels.get("has_hallucination"):
        return "hallucination"
    if labels.get("bad_answer"):
        return "bad"
    return "clean"


def _stable_id(text: str) -> str:
    import hashlib

    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:12]


def _ragtruth_fixtures() -> List[EvalExample]:
    return [
        ragtruth_to_example(
            {
                "id": "fixture_ragtruth_bad",
                "source_id": "fixture_source",
                "response": "ExampleOS 9 was released on April 3, 2026 and supports the Delta chipset.",
                "labels": [{"label_type": "Evident Baseless Info", "text": "April 3, 2026"}],
                "split": "test",
                "quality": "good",
            },
            {
                "source_id": "fixture_source",
                "task_type": "QA",
                "source": "fixture",
                "source_info": {
                    "question": "When was ExampleOS 9 released?",
                    "passages": "ExampleOS 9 was released on April 2, 2026. The release notes do not mention a Delta chipset.",
                },
            },
        ),
        ragtruth_to_example(
            {
                "id": "fixture_ragtruth_good",
                "source_id": "fixture_source",
                "response": "ExampleOS 9 was released on April 2, 2026.",
                "labels": [],
                "split": "test",
                "quality": "good",
            },
            {
                "source_id": "fixture_source",
                "task_type": "QA",
                "source": "fixture",
                "source_info": {
                    "question": "When was ExampleOS 9 released?",
                    "passages": "ExampleOS 9 was released on April 2, 2026.",
                },
            },
        ),
    ]


def _selfcheck_fixtures() -> List[EvalExample]:
    return [
        selfcheck_to_example(
            {
                "wiki_bio_test_idx": "fixture_selfcheck_bad",
                "gpt3_text": "Ada Lovelace was an English mathematician. She won the Nobel Prize in Physics.",
                "wiki_bio_text": "Ada Lovelace was an English mathematician and writer. She died in 1852, before the Nobel Prizes existed.",
                "annotation": ["accurate", "major_inaccurate"],
                "gpt3_text_samples": [
                    "Ada Lovelace was an English mathematician and writer.",
                    "Ada Lovelace did not win a Nobel Prize.",
                ],
            }
        ),
        selfcheck_to_example(
            {
                "wiki_bio_test_idx": "fixture_selfcheck_good",
                "gpt3_text": "Ada Lovelace was an English mathematician and writer.",
                "wiki_bio_text": "Ada Lovelace was an English mathematician and writer.",
                "annotation": ["accurate"],
                "gpt3_text_samples": ["Ada Lovelace was an English mathematician and writer."],
            }
        ),
    ]


def _simpleqa_fixtures() -> List[EvalExample]:
    return [
        simpleqa_to_example(
            {
                "id": "fixture_simpleqa_openai_city",
                "problem": "What city is OpenAI headquartered in?",
                "answer": "San Francisco, California",
            },
            oracle_answer=True,
        )
    ]
