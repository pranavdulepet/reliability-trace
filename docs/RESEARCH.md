# Research Basis

ReliabilityGraph uses research signals as diagnostics, not as proof that an answer is true.

## Signals

| Signal | Status | What It Means | Main Limitation |
| --- | --- | --- | --- |
| `atomic_claim_support` | Strongest current signal | Inspired by FActScore and SAFE / LongFact. The pipeline decomposes the answer into checkable claims and matches each claim to attached, fetched, or web source chunks. | Current matching is lexical and local; it is not a full NLI verifier and can miss paraphrase, context, and source-authority nuance. |
| `source_quality_score` | Useful diagnostic | Separates higher-provenance source matches from weak snippets before the score can rise. | Source quality is heuristic; it needs benchmark calibration and better domain/source reputation models. |
| `sample_consistency` | Directional signal | Inspired by SelfCheckGPT. Multiple samples are compared for answer stability. | Models can agree on the same false claim, so agreement cannot replace external evidence for factual/current answers. |
| `semantic_entropy` | Directional signal | Inspired by semantic entropy work. The system tracks answer-meaning disagreement instead of treating every wording difference as important. | Current clustering is a lightweight approximation, not a full entailment-based semantic entropy implementation. |
| `perturbation_check` | Directional live robustness signal | Behavioral pressure prompts test whether the answer flips under paraphrase, false-premise, or authority pressure. | This is observable provider behavior only; it is not hidden reasoning access and is not exhaustive. |
| `calibration` | Valid only after labels | Inspired by reliability diagrams, ECE, and Brier score. User-labeled runs produce local calibration reports. | Until enough local labels exist, the score is an uncalibrated diagnostic, not a probability. |
| `observable_activity` | Auditability signal, not a truth signal | Inspired by unfaithful chain-of-thought findings. The UI shows observable steps, calls, outputs, checks, and scores. | Activity completeness does not make an answer true and is not part of the reliability score. |

## Removed Or Demoted

- Hard-coded rubric dimensions are no longer score inputs. The pipeline now exposes deterministic signal summaries only when useful for inspection.
- Fake decision utilities and criterion weights were removed. Decision analysis now shows qualitative options, evidence status, basis, and risk.
- Trace completeness is no longer a score feature. It is useful for debugging and transparency, not factual reliability.
- A single high-scoring retrieved chunk no longer dominates the score. Claim support, retrieval alignment, source quality, and sample consistency share the score.

## Benchmark Direction

Use `scripts/smoke_usecases.py` for fast product smoke coverage. Larger benchmark work should compare the full graph against baselines:

- single answer
- single answer with citations
- verbal confidence
- LLM judge only
- model agreement only
- semantic entropy only
- claim support only

Metrics to preserve: answer accuracy, claim support precision, contradiction detection, unsupported-claim detection, ECE, Brier score, risk coverage, false-premise acceptance, and decision usefulness.
