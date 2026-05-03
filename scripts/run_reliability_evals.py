import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.reliability_graph.config import ENV_KEY_BY_PROVIDER, settings
from backend.reliability_graph.evals import (
    EvalExample,
    load_benchmark_examples,
    run_eval_example,
    summarize_eval_results,
    write_eval_outputs,
)
from backend.reliability_graph.secrets import KeyVault
from backend.reliability_graph.storage import Storage


BENCHMARKS = ["ragtruth", "selfcheck", "simpleqa"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ReliabilityGraph benchmark pilot evals.")
    parser.add_argument("--benchmark", choices=BENCHMARKS + ["all"], default="all")
    parser.add_argument("--limit", type=int, default=6, help="Max examples per benchmark.")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--offline", action="store_true", help="Use cached data or tiny fixtures only.")
    parser.add_argument("--live-provider", choices=["openai", "anthropic", "gemini", "openrouter", "tinker"])
    parser.add_argument("--live-limit", type=int, default=0, help="SimpleQA live examples to run.")
    parser.add_argument("--model", default=None)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--cache-dir", default="data/evals/cache")
    parser.add_argument("--output-dir", default=None)
    return parser.parse_args()


async def main_async() -> int:
    args = parse_args()
    selected = BENCHMARKS if args.benchmark == "all" else [args.benchmark]
    cache_dir = Path(args.cache_dir)
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir()
    notes = []
    results = []

    for benchmark in selected:
        loaded = load_benchmark_examples(benchmark, cache_dir, args.limit, args.seed, args.offline)
        notes.extend(loaded.notes)
        for example in loaded.examples:
            results.append(
                await run_eval_example(
                    example,
                    samples=args.samples,
                )
            )

    if args.live_provider and args.live_limit > 0:
        resolver = _stored_key_resolver()
        if not _provider_has_key(args.live_provider):
            notes.append("Live %s slice skipped because no provider key is configured." % args.live_provider)
        else:
            live_loaded = load_benchmark_examples("simpleqa", cache_dir, args.live_limit, args.seed, args.offline)
            notes.extend(["live_simpleqa: " + note for note in live_loaded.notes])
            for example in live_loaded.examples:
                live_example = EvalExample(
                    benchmark="simpleqa_live_%s" % args.live_provider,
                    example_id=example.example_id,
                    question=example.question,
                    answer=None,
                    source_texts=example.source_texts,
                    gold_labels=example.gold_labels,
                    metadata={**example.metadata, "live_provider": args.live_provider},
                )
                results.append(
                    await run_eval_example(
                        live_example,
                        resolve_key=resolver,
                        live_provider=args.live_provider,
                        model=args.model,
                        samples=max(1, min(args.samples, 2)),
                    )
                )

    summary = summarize_eval_results(results, notes)
    paths = write_eval_outputs(output_dir, results, summary)
    print("ReliabilityGraph evals complete")
    print("results: %s" % paths["results"])
    print("summary: %s" % paths["summary"])
    print("report: %s" % paths["report"])
    return 0


def _default_output_dir() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return Path("data/evals/runs") / stamp


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
