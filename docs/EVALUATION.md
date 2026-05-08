# Evaluation

ReliabilityGraph has two evaluation paths:

- Local calibration: `/api/benchmarks/report` uses user-labeled completed runs from the app.
- External official-style evals: `scripts/run_reliability_evals.py` runs fixed benchmark answers through the Reliability Evidence Graph and writes ignored artifacts under `data/evals`.

## Run

```bash
python scripts/run_reliability_evals.py --benchmark all --mode dev --limit 50 --seed 7 --offline
```

Use a live provider slice only when you want end-to-end behavior:

```bash
python scripts/run_reliability_evals.py --benchmark simpleqa --mode dev --max-live 10 --live-provider tinker
```

Fit score weights from a dev eval run:

```bash
python scripts/calibrate_reliability_weights.py --input data/evals/runs/<dev-run>/results.jsonl --trials 4000 --seed 7
```

This writes `configs/reliability_score_weights.json`. The script fits only the linear signal weights. It does not learn or weaken safety caps, because caps encode product risk policy for false-safe failures.

The script never prints API keys. Outputs are written to:

- `results.jsonl`: one graph-backed row per example.
- `summary.json`: aggregate metrics for machines.
- `report.md`: concise human-readable report.
- `manifest.json`: args, git SHA, cache files, dataset source URLs, and provider metadata without keys.

Use `--resume --output-dir data/evals/runs/<run>` to continue an interrupted run. Completed `benchmark:example_id` rows are skipped.

## Benchmarks

- RAGTruth: checks whether source-grounded hallucinations are reflected in claim/source assessments and false-safe rate.
- SelfCheckGPT WikiBio: checks whether sample disagreement and semantic stability track sentence-level factuality labels.
- SimpleQA: checks short factual answers with strict normalized matching first; ambiguous answers are marked `needs_review`.

If public data is unavailable, offline mode uses tiny fixtures and the report says so. Fixture runs are smoke checks, not benchmark evidence.

## Splits

- `--mode dev`: RAGTruth official `train`; SelfCheck and SimpleQA stable seeded 70% dev split.
- `--mode test`: RAGTruth official `test`; SelfCheck and SimpleQA stable seeded 30% held-out split.
- `--mode full`: all loaded examples.

Use dev for tuning. Use test/full only after fixes pass dev gates.

## Metrics

- AUROC/AUPRC use `1 - reliability_score` as the bad-answer risk score.
- F1 is the best threshold F1 on the run, not a fixed product threshold.
- ECE and Brier treat the score as an eval signal only, not a user-facing probability.
- Risk coverage reports how many answers remain above score thresholds and their empirical correctness.
- False-safe rate counts bad labeled examples that receive `rely` or score `>= 75`.
- Ablations recompute the scoring formula with signal groups removed to show directional score sensitivity, including average and peak retrieval support.
- RAGTruth adds task/model/label-type breakdowns.
- SelfCheckGPT adds sentence NonFact AUC-PR, sentence Factual AUC-PR, and passage Pearson/Spearman.
- SimpleQA uses deterministic grading first; live provider grading is used only for ambiguous live answers when configured.

## Score Weight Calibration

The tracked score-weight config is a versioned benchmark-tuned diagnostic. You do not need to refit it on every app launch. Refit when scoring features or caps change, provider/verifier/retrieval/search behavior changes materially, the benchmark mix changes, or enough local user labels exist to justify a new local calibration. Always tune on dev and then report held-out test/full results.

Current RAGTruth strengthening focuses on source-grounded hallucination risk: meta-claim filtering, wider per-claim evidence retrieval, structured negation handling, unit-aware numeric contradiction detection, source-grounded summary overreach checks, and preserving web-result published dates for freshness-sensitive retrieval. These changes are evaluated with RAGTruth response-level AUROC/AUPRC, claim-relation recall on bad answers, bad examples above the medium-score threshold, and false-safe rate.

## Baselines

Reports include same-data baselines: random/prior, claim-support-only, retrieval lexical support, sample-consistency-only, SelfCheck n-gram, and the full ReliabilityGraph score. Use `--fail-on-regression` to fail the command when the full score loses AUROC/AUPRC by more than 0.02 to the internal non-random general baselines with comparable false-safe rate, or when the full score has materially worse false-safe rate. SelfCheck n-gram is reported as a benchmark-specific reference; it can beat the general score on SelfCheck ranking without failing the gate, but false-safe regressions still fail.

## Limits

This harness evaluates reliability methodology, not model leadership. Fixed benchmark answers isolate scoring behavior; the optional live provider slice validates the product path but mixes provider quality with ReliabilityGraph scoring.

Published benchmark numbers are context unless the same split, target, and grader are reproduced exactly. This harness is practical official: official data and comparable metrics, with lightweight local grading unless a configured provider is explicitly used.
