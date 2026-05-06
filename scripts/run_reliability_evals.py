import argparse
import asyncio
import json
import os
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.reliability_graph.config import ENV_KEY_BY_PROVIDER, settings
from backend.reliability_graph.evals import (
    BENCHMARKS,
    EvalExample,
    MODES,
    OFFICIAL_SOURCES,
    auroc,
    average_precision,
    baseline_risk_score,
    filter_examples_for_mode,
    load_benchmark_examples,
    redact_value,
    run_eval_example,
    summarize_eval_results,
    write_eval_outputs,
)
from backend.reliability_graph.secrets import KeyVault
from backend.reliability_graph.storage import Storage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ReliabilityGraph official-style reliability evals.")
    parser.add_argument("--benchmark", choices=BENCHMARKS + ["all"], default="all")
    parser.add_argument("--mode", choices=MODES, default="dev")
    parser.add_argument("--limit", type=int, default=50, help="Max examples per benchmark. Use 0 for no cap.")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--offline", action="store_true", help="Use cached data or tiny fixtures only.")
    parser.add_argument("--live-provider", choices=["openai", "anthropic", "gemini", "openrouter", "tinker"])
    parser.add_argument("--max-live", type=int, default=0, help="Max SimpleQA live examples to run.")
    parser.add_argument("--live-limit", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--model", default=None)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--baseline",
        action="append",
        choices=["all", "full_score", "random_prior", "claim_support_only", "retrieval_lexical", "sample_consistency_only", "selfcheck_ngram"],
    )
    parser.add_argument("--fail-on-regression", action="store_true")
    parser.add_argument("--cache-dir", default="data/evals/cache")
    parser.add_argument("--output-dir", default=None)
    return parser.parse_args()


async def main_async() -> int:
    args = parse_args()
    if args.live_limit is not None:
        args.max_live = args.live_limit
    if args.resume and not args.output_dir:
        raise SystemExit("--resume requires --output-dir")
    selected = BENCHMARKS if args.benchmark == "all" else [args.benchmark]
    cache_dir = Path(args.cache_dir)
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir()
    notes = []
    examples = []
    limit = None if args.limit is not None and args.limit <= 0 else args.limit

    for benchmark in selected:
        loaded = load_benchmark_examples(benchmark, cache_dir, None, args.seed, args.offline)
        notes.extend(loaded.notes)
        mode_examples = filter_examples_for_mode(loaded.examples, args.mode, args.seed)
        if limit is not None:
            mode_examples = _sample_examples(mode_examples, limit, args.seed)
        examples.extend(mode_examples)

    resolver = _stored_key_resolver() if args.live_provider else None
    if args.live_provider and args.max_live > 0:
        if not _provider_has_key(args.live_provider):
            notes.append("Live %s slice skipped because no provider key is configured." % args.live_provider)
        else:
            live_loaded = load_benchmark_examples("simpleqa", cache_dir, None, args.seed, args.offline)
            notes.extend(["live_simpleqa: " + note for note in live_loaded.notes])
            live_examples = filter_examples_for_mode(live_loaded.examples, args.mode, args.seed)[: args.max_live]
            for example in live_examples:
                live_example = EvalExample(
                    benchmark="simpleqa_live_%s" % args.live_provider,
                    example_id=example.example_id,
                    question=example.question,
                    answer=None,
                    source_texts=example.source_texts,
                    gold_labels=example.gold_labels,
                    metadata={**example.metadata, "live_provider": args.live_provider},
                )
                examples.append(live_example)

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = _manifest(args, cache_dir, output_dir, selected, examples)
    _write_json(output_dir / "manifest.json", manifest)
    results = await _run_examples(args, examples, output_dir, resolver)
    summary = summarize_eval_results(results, notes)
    _filter_baselines(summary, args.baseline)
    paths = write_eval_outputs(output_dir, results, summary)
    print("ReliabilityGraph evals complete")
    print("results: %s" % paths["results"])
    print("summary: %s" % paths["summary"])
    print("report: %s" % paths["report"])
    print("manifest: %s" % str(output_dir / "manifest.json"))
    regressions = _internal_regressions(results) if args.fail_on_regression else []
    if regressions:
        print("regression gate failed:")
        for regression in regressions:
            print("- %s" % regression)
        return 2
    return 0


async def _run_examples(args: argparse.Namespace, examples, output_dir: Path, resolver):
    results_path = output_dir / "results.jsonl"
    if not args.resume and results_path.exists():
        results_path.unlink()
    existing = _read_results(results_path) if args.resume else []
    completed = {_result_key(result) for result in existing}
    pending = [example for example in examples if _example_key(example) not in completed]
    results = list(existing)
    semaphore = asyncio.Semaphore(max(1, args.workers))

    async def run_one(example):
        async with semaphore:
            is_live = example.benchmark.startswith("simpleqa_live_")
            return await run_eval_example(
                example,
                resolve_key=resolver,
                live_provider=args.live_provider if is_live else None,
                model=args.model,
                samples=max(1, min(args.samples, 2)) if is_live else args.samples,
                allow_simpleqa_judge=is_live,
            )

    tasks = [asyncio.create_task(run_one(example)) for example in pending]
    for task in asyncio.as_completed(tasks):
        result = await task
        if _result_key(result) in completed:
            continue
        _append_result(results_path, result)
        completed.add(_result_key(result))
        results.append(result)
    return results


def _default_output_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path("data/evals/runs") / stamp


def _manifest(args: argparse.Namespace, cache_dir: Path, output_dir: Path, selected, examples) -> dict:
    return redact_value(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "git_sha": _git_sha(),
            "args": vars(args),
            "benchmarks": selected,
            "mode": args.mode,
            "example_count": len(examples),
            "output_dir": str(output_dir),
            "official_sources": OFFICIAL_SOURCES,
            "cache": _cache_manifest(cache_dir),
            "providers": {
                "live_provider": args.live_provider,
                "live_key_configured": bool(args.live_provider and _provider_has_key(args.live_provider)),
                "model": args.model,
            },
        }
    )


def _git_sha() -> Optional[str]:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _cache_manifest(cache_dir: Path) -> dict:
    rows = {}
    for path in sorted(cache_dir.glob("*")):
        if not path.is_file():
            continue
        rows[path.name] = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "line_count": _line_count(path),
            "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        }
    return rows


def _line_count(path: Path) -> int:
    try:
        with path.open("rb") as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def _read_results(path: Path) -> list:
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    deduped = {}
    for row in rows:
        deduped[_result_key(row)] = row
    return list(deduped.values())


def _append_result(path: Path, result: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(redact_value(result), sort_keys=True) + "\n")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(redact_value(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _example_key(example: EvalExample) -> str:
    return "%s:%s" % (example.benchmark, example.example_id)


def _result_key(result: dict) -> str:
    return "%s:%s" % (result.get("benchmark"), result.get("example_id"))


def _filter_baselines(summary: dict, requested) -> None:
    if not requested or "all" in requested:
        return
    baselines = summary.get("baselines") or {}
    summary["baselines"] = {name: baselines[name] for name in requested if name in baselines}


def _sample_examples(examples: list, limit: Optional[int], seed: int) -> list:
    if limit is None or limit >= len(examples):
        return examples
    rng = random.Random(seed)
    return rng.sample(examples, limit)


def _internal_regressions(results: list) -> list[str]:
    regressions = []
    ranking_gate_baselines = {
        "claim_support_only",
        "retrieval_lexical",
        "sample_consistency_only",
    }
    safety_gate_baselines = ranking_gate_baselines | {"selfcheck_ngram"}
    for baseline_name in sorted(safety_gate_baselines):
        comparison = _paired_baseline_comparison(results, baseline_name)
        if not comparison:
            continue
        comparable_safety = comparison["baseline_false_safe"] <= comparison["full_false_safe"] + 0.02
        if (
            baseline_name in ranking_gate_baselines
            and comparable_safety
            and _metric_beats(comparison["baseline_auroc"], comparison["full_auroc"])
        ):
            regressions.append(
                "%s AUROC %.4f beat full score AUROC %.4f on the same %d rows"
                % (
                    baseline_name,
                    comparison["baseline_auroc"],
                    comparison["full_auroc"],
                    comparison["count"],
                )
            )
        if (
            baseline_name in ranking_gate_baselines
            and comparable_safety
            and _metric_beats(comparison["baseline_auprc"], comparison["full_auprc"])
        ):
            regressions.append(
                "%s AUPRC %.4f beat full score AUPRC %.4f on the same %d rows"
                % (
                    baseline_name,
                    comparison["baseline_auprc"],
                    comparison["full_auprc"],
                    comparison["count"],
                )
            )
        if comparison["full_false_safe"] > comparison["baseline_false_safe"] + 0.02:
            regressions.append(
                "full score false-safe %.4f exceeded %s false-safe %.4f on the same %d bad rows"
                % (
                    comparison["full_false_safe"],
                    baseline_name,
                    comparison["baseline_false_safe"],
                    comparison["bad_count"],
                )
            )
    return regressions


def _paired_baseline_comparison(results: list, baseline_name: str) -> Optional[dict]:
    labels = []
    full_risks = []
    baseline_risks = []
    full_false_safe = []
    baseline_false_safe = []
    for result in results:
        metrics = result.get("metrics") or {}
        correctness = metrics.get("correctness")
        full_risk = baseline_risk_score(result, "full_score")
        baseline_risk = baseline_risk_score(result, baseline_name)
        if correctness is None or full_risk is None or baseline_risk is None:
            continue
        bad_answer = bool(metrics.get("bad_answer"))
        labels.append(1 if bad_answer else 0)
        full_risks.append(float(full_risk))
        baseline_risks.append(float(baseline_risk))
        if bad_answer:
            full_false_safe.append(1.0 if float(full_risk) <= 0.25 else 0.0)
            baseline_false_safe.append(1.0 if float(baseline_risk) <= 0.25 else 0.0)
    if len(labels) < 2 or len(set(labels)) < 2:
        return None
    return {
        "baseline": baseline_name,
        "count": len(labels),
        "bad_count": sum(labels),
        "full_auroc": auroc(labels, full_risks),
        "baseline_auroc": auroc(labels, baseline_risks),
        "full_auprc": average_precision(labels, full_risks),
        "baseline_auprc": average_precision(labels, baseline_risks),
        "full_false_safe": _mean(full_false_safe),
        "baseline_false_safe": _mean(baseline_false_safe),
    }


def _metric_beats(left: Optional[float], right: Optional[float]) -> bool:
    return left is not None and right is not None and left > right + 0.02


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / float(len(values))


def _stored_key_resolver():
    storage = Storage(settings.db_path)
    storage.init_db()
    vault = KeyVault(settings.db_path.parent, settings.secret)

    async def resolve(provider: str) -> Optional[str]:
        ciphertext = storage.get_provider_key_ciphertext(settings.user_id, provider)
        if ciphertext:
            storage.mark_provider_key_used(settings.user_id, provider)
            return vault.decrypt(ciphertext)
        env_var = ENV_KEY_BY_PROVIDER.get(provider)
        return os.getenv(env_var) if env_var else None

    return resolve


def _provider_has_key(provider: str) -> bool:
    storage = Storage(settings.db_path)
    storage.init_db()
    if storage.get_provider_key_ciphertext(settings.user_id, provider):
        return True
    env_var = ENV_KEY_BY_PROVIDER.get(provider)
    return bool(os.getenv(env_var)) if env_var else False


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
