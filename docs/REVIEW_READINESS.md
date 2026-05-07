# Review Readiness

This document is written for research review. It states what ReliabilityGraph can defensibly claim, what is product policy, and what still needs empirical validation.

## Core Claim

ReliabilityGraph is a reliability-audited chat system. It does not prove that an answer is true. It produces a structured, stored audit that helps a user decide whether an answer is usable under the evidence gathered for that run.

The user-facing score is a 0-100 Reliability Score. Interpret it as an audit-derived risk-ranking score for this answer, not as a calibrated probability of correctness. A score of 80 is stronger than 40 under the same methodology, but it does not mean "80% likely true" unless validated and calibrated on the target distribution.

## Defensible Methodology

The product uses three exposed signals:

- Evidence check: extract atomic claims, retrieve evidence, and classify each checkable claim as supported, partially supported, contradicted, not enough information, or not checkable.
- Stability check: sample multiple candidate answers and penalize large meaning-level disagreement or obvious recommendation/numeric flips.
- Reliability repair: generate concrete follow-up prompts that target missing evidence, contradictions, partial support, or unstable framing.

The strongest signal is evidence check. Stability is a warning signal only; it cannot rescue unsupported factual claims. Repair prompts are not a research metric, but they are important product behavior because the useful next step is often to improve the evidence rather than stare at a score.

## Research Lineage

- FActScore motivates decomposing long-form answers into atomic factual units and measuring source support.
- SAFE / LongFact motivates search-augmented long-form factuality checks over individual facts.
- FEVER motivates support/refute/not-enough-information claim verification labels.
- RAGTruth motivates evaluating unsupported or contradictory claims in retrieval-augmented answers.
- SelfCheckGPT motivates black-box sample consistency as evidence for hallucination risk.
- Semantic Entropy motivates meaning-level agreement instead of naive wording overlap.
- Calibration work motivates ECE, Brier, risk coverage, and explicit separation between score ranking and probability calibration.

## What Is Research-Derived

- Atomic claim decomposition as the factuality unit.
- Source-grounded claim support/refutation framing.
- The use of multiple samples as a hallucination-risk signal.
- Meaning-level grouping as a stronger signal than lexical variation alone.
- Evaluation metrics: AUROC/AUPRC for bad-answer ranking, false-safe rate, ECE, Brier, and risk coverage.

## What Is Product Policy

- The final decision labels: `rely`, `use_with_caution`, `do_not_rely`.
- Safety caps for contradictions, missing source-required evidence, low-provenance partial support, and unstable answers.
- The exact 0-100 score scale and thresholds.
- The text in "why it matters" and "improve reliability" prompts.

Those choices are intentionally conservative product policy. They should be evaluated, but they are not direct claims from a paper.

## Current Validation Status

The tracked score weights come from official-style fixed-answer development evals and are stored in `configs/reliability_score_weights.json`. The config records the input run, metrics, objective, and rerun triggers. Safety caps are not learned; they are explicit false-safe controls.

Current validation supports the score as a diagnostic ranking signal. It does not yet support claims of universal calibration across all domains, providers, users, or current-events queries.

The latest audit also records unresolved source conflicts: when a matched source snippet appears to conflict with a claim but the provider plus entailment verifier do not mark the claim as contradicted, the claim remains conservatively labeled by the verifier result while the conflict is surfaced for review. This improves failure visibility without pretending a lightweight source-match signal is a definitive contradiction detector.

Latest local review gate run:

```bash
UV_CACHE_DIR=.uv-cache uv run python scripts/run_reliability_evals.py --benchmark all --mode dev --limit 50 --offline --fail-on-regression
```

The May 7, 2026 run used cached official datasets and no live provider calls. It passed the regression gate with:

| Benchmark | N | AUROC | AUPRC | Claim relation recall on bad answers | False-safe |
| --- | ---: | ---: | ---: | ---: | ---: |
| RAGTruth | 50 | 0.6183 | 0.4810 | 0.7000 | 0.0000 |
| SelfCheckGPT WikiBio | 50 | 0.9894 | 1.0000 | 0.7447 | 0.0000 |
| SimpleQA oracle-answer slice | 50 | n/a | n/a | n/a | n/a |
| Overall fixed-answer gate | 150 | 0.8543 | 0.7077 | 0.7313 | 0.0000 |

This is good enough to show a conservative prototype with no false-safe cases in the small gate. It is not enough to claim state-of-the-art reliability detection. RAGTruth remains the main research weakness.

Before making a stronger research claim, run and report:

- held-out RAGTruth response-level AUROC/AUPRC/F1 and false-safe rate
- SelfCheckGPT WikiBio sentence/passage metrics
- SimpleQA live-provider factuality and risk-coverage slice
- FEVER-style claim verification fixtures for support/refute/not-enough-information behavior
- ablations for evidence-only, stability-only, and full ReliabilityGraph
- calibration plots with ECE/Brier on held-out labeled data

## Known Failure Modes

- Retrieval can miss the best source, retrieve stale pages, or retrieve a snippet that is misleading without the full page.
- Source quality is currently metadata-driven; it is not a full reputation model.
- Provider-based claim extraction can miss or merge claims.
- NLI models can fail on numeracy, temporal claims, domain-specific language, and multi-hop evidence.
- Multiple samples can agree on the same false answer.
- Web evidence can contain prompt-injection text; the system treats it as evidence only, but the provider can still make classification mistakes.
- The score is sensitive to benchmark mix and should be refit when retrieval, verifier, providers, features, or caps change materially.
- High-stakes medical, legal, financial, or safety answers require domain-specific validation beyond this general-chat audit.

## Review Checklist

A reviewer should be able to verify:

- Production chat requires a real provider and ready entailment verifier.
- No synthetic answer or fake audit substitutes are used when provider/verifier stages fail.
- Source text is never promoted to instructions.
- The score is emitted only after the full audit completes.
- Inline citations reference real evidence IDs.
- Exports contain the stored graph and no plaintext provider/search keys.
- The UI states reason, consequence, and concrete repair prompts, not only a number.
- Docs separate research-derived signals from product policy.

## Current Bottom Line

ReliabilityGraph is reviewable as a practical reliability-audited chat prototype and an engineering platform for LLM reliability experiments. It should not be presented as a solved reliability oracle. The strongest near-term research contribution is the product loop: answer, evidence-grounded audit, conservative score, and targeted reliability-repair prompts.
