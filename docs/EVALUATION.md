# Evaluation

ReliabilityGraph has two evaluation paths:

- Local calibration: `/api/benchmarks/report` uses user-labeled completed runs from the app.
- External pilot evals: `scripts/run_reliability_evals.py` runs fixed benchmark answers through the Reliability Evidence Graph and writes ignored artifacts under `data/evals`.

## Run

```bash
python3 scripts/run_reliability_evals.py --benchmark all --limit 6 --seed 7 --offline
```

Use a live provider slice only when you want end-to-end behavior:

```bash
python3 scripts/run_reliability_evals.py --benchmark all --limit 6 --live-provider tinker --live-limit 2
```

The script never prints API keys. Outputs are written to:

- `results.jsonl`: one graph-backed row per example.
- `summary.json`: aggregate metrics for machines.
- `report.md`: concise human-readable report.

## Benchmarks

- RAGTruth: checks whether source-grounded hallucinations are reflected in claim/source assessments and false-safe rate.
- SelfCheckGPT WikiBio: checks whether sample disagreement and semantic stability track sentence-level factuality labels.
- SimpleQA: checks short factual answers with strict normalized matching first; ambiguous answers are marked `needs_review`.

If public data is unavailable, offline mode uses tiny fixtures and the report says so. Fixture runs are smoke checks, not benchmark evidence.

## Metrics

- AUROC/AUPRC use `1 - reliability_score` as the bad-answer risk score.
- ECE and Brier treat the score as an eval signal only, not a user-facing probability.
- Risk coverage reports how many answers remain above score thresholds and their empirical correctness.
- False-safe rate counts bad labeled examples that receive `rely` or score `>= 75`.
- Ablations recompute the scoring formula with signal groups removed to show directional score sensitivity.

## Limits

This pilot evaluates reliability methodology, not model leadership. Fixed benchmark answers isolate scoring behavior; the optional live provider slice validates the product path but mixes provider quality with ReliabilityGraph scoring.
