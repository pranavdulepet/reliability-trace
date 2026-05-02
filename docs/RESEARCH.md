# ReliabilityGraph Benchmark Report

This is the research artifact skeleton. Keep product UI separate from benchmark claims.

## 1. Motivation

Measure whether the full Reliability Evidence Graph predicts answer correctness or decision usefulness better than any single signal.

## 2. System

Signals under test:

- claim support
- semantic stability
- source quality
- disagreement
- stress-test flips
- decision sensitivity
- judge rubric scores
- trace completeness

## 3. Benchmarks

- SimpleQA
- TruthfulQA
- FreshQA
- LongFact / SAFE-style tasks
- RAGTruth
- custom general-QA set
- custom decision-QA set
- user-labeled real runs

## 4. Baselines

- single model answer
- single model answer with citations
- verbalized confidence
- LLM judge only
- model agreement only
- semantic entropy only
- SelfCheck-style consistency only
- claim support only
- full ReliabilityGraph

## 5. Metrics

- answer accuracy
- claim-level support precision
- contradiction detection
- unsupported-claim detection
- ECE
- Brier score
- risk-coverage
- sycophancy flip rate
- false-premise acceptance rate
- assumption recall
- decision usefulness rating

## 6. Status

The current product marks scores as uncalibrated diagnostic values until this report has empirical calibration data.
