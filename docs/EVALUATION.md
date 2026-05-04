# Evaluation

ReliabilityGraph has two evaluation paths:

- Local calibration: `/api/benchmarks/report` uses user-labeled completed runs from the app.
- External official-style evals: `scripts/run_reliability_evals.py` runs fixed benchmark answers through the Reliability Evidence Graph and writes ignored artifacts under `data/evals`.

## Run

```bash
python3 scripts/run_reliability_evals.py --benchmark all --mode dev --limit 50 --seed 7 --offline
```

Use a live provider slice only when you want end-to-end behavior:

```bash
python3 scripts/run_reliability_evals.py --benchmark simpleqa --mode dev --max-live 10 --live-provider tinker
```

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

## Baselines

Reports include same-data baselines: random/prior, claim-support-only, retrieval lexical support, sample-consistency-only, SelfCheck n-gram, and the full ReliabilityGraph score. Use `--fail-on-regression` to fail the command when the full score loses AUROC to an internal non-random baseline.

## Limits

This harness evaluates reliability methodology, not model leadership. Fixed benchmark answers isolate scoring behavior; the optional live provider slice validates the product path but mixes provider quality with ReliabilityGraph scoring.

Published benchmark numbers are context unless the same split, target, and grader are reproduced exactly. This harness is practical official: official data and comparable metrics, with lightweight local grading unless a configured provider is explicitly used.
