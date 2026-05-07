# Research Basis

ReliabilityGraph uses research signals as diagnostics, not as proof that an answer is true.

## Signals

The product UI reduces the research machinery to three user-facing signals:

- Evidence check: atomic claims are checked against gathered web, URL, and file evidence. This is the main driver for factual, current, and source-required answers.
- Stability check: sample and meaning agreement warn when the model does not converge. Stability can lower trust, but it does not prove unsupported claims.
- Reliability repair: the app generates concrete follow-up prompts that help the user add evidence, resolve contradictions, narrow claims, or expose missing assumptions.

The deeper signals below remain in the stored graph, export, and details.

| Signal | Status | What It Means | Main Limitation |
| --- | --- | --- | --- |
| `atomic_claim_support` | Strongest current signal | Inspired by FActScore and SAFE / LongFact. Production chat uses provider-backed structured claim extraction and evidence assessment, then gates claim/source relations through a required NLI entailment verifier. | This is still not proof of truth. Provider extraction and NLI can be wrong, miss context, or over-trust weak sources; results must be benchmarked against labeled data. |
| `source_quality_score` | Useful diagnostic | Separates higher-provenance source matches from weak snippets before the score can rise. | Source quality uses source metadata; it needs benchmark calibration and better domain/source reputation models. |
| `numeric_unit_contradiction` | Useful guardrail | Claim/source matching treats incompatible numeric units as conflicts, such as a claim saying `26.2 hours` when the source says `26.2 miles`. | This is a targeted contradiction detector, not a full symbolic verifier. |
| `sample_consistency` | Warning signal | Inspired by SelfCheckGPT. Multiple samples are compared for answer stability. | Models can agree on the same false claim, so agreement cannot replace external evidence for factual/current answers. |
| `semantic_entropy` | Warning signal | Inspired by semantic entropy work. The system tracks answer-meaning disagreement instead of treating every wording difference as important. | Current clustering is a lightweight approximation and is shown only when it changes the reliability decision. |
| `sample_conflict_rate` | Useful guardrail | Candidate answers are checked for obvious numeric changes and recommendation-polarity flips before they can be treated as stable. | This catches simple conflicts only; it is not a general contradiction detector or substitute for source evidence. |
| `perturbation_check` | Directional live robustness signal | Behavioral pressure prompts test whether the answer flips under paraphrase, false-premise, or authority pressure. | This is observable provider behavior only; it is not hidden reasoning access and is not exhaustive. |
| `score_weight_calibration` | Valid as a benchmark-tuned ranking diagnostic | Linear signal weights are fitted from official-style fixed-answer eval rows with AUROC/AUPRC and false-safe penalties, then source-required answers use an evidence-first product weighting. This makes the score less arbitrary than hand-picked weights while preserving explicit safety caps. | The fitted score is still not a probability or universal calibration claim. Re-run calibration when features, caps, verifier, retrieval/search behavior, provider behavior, benchmark mix, or enough user labels change. |
| `calibration` | Valid only after labels | Inspired by reliability diagrams, ECE, and Brier score. User-labeled runs and external evals produce calibration reports. | ECE/Brier describe empirical score behavior on a labeled dataset; they do not prove that a single new answer is true. |
| `observable_activity` | Auditability signal, not a truth signal | Inspired by unfaithful chain-of-thought findings. The UI shows observable steps, calls, outputs, checks, and scores. | Activity completeness does not make an answer true and is not part of the reliability score. |
| `inline_citations` | Evidence navigation, not a score | Supported claim spans can receive citation markers only when they map to real evidence IDs. | A citation means the cited snippet was used by the audit; it does not prove the broader source or answer is fully correct. |
| `reliability_repair` | User action signal | Generated follow-up prompts target the concrete weakness found in the answer: missing sources, contradictions, partial support, unstable samples, or missing decision constraints. | Prompts improve the next check only if the user runs them and stronger evidence is available. |

## Removed Or Demoted

- Hard-coded rubric dimensions are no longer score inputs. The pipeline exposes computed signal summaries only when useful for inspection.
- Fake decision utilities and criterion weights were removed. Decision analysis now shows qualitative options, evidence status, basis, and risk.
- Trace completeness is no longer a score feature. It is useful for debugging and transparency, not factual reliability.
- A single high-scoring retrieved chunk no longer dominates the score. Claim support, retrieval alignment, source quality, and sample consistency share the score, with tracked weights in `configs/reliability_score_weights.json`.
- Source-grounded checks ignore answer-format meta claims like "here is a summary" and focus scoring on factual content claims.
- Missing sources are handled differently by question type: they block current, high-stakes, and source-required factual answers, but only mark general explanations as not source-grounded.
- Partial source support is capped more aggressively when retrieval alignment is weak, because a nearby snippet is not enough for RAG/source-grounded reliability if the exact claim is only partly established.
- Production chat no longer substitutes local synthetic answers, fallback claim extraction, or heuristic claim/source relations when provider or verifier work fails. Eval-only fixed-answer runs still use controlled fixtures so benchmark scoring can run offline.
- Frontend fallback verdicts and evidence summaries were removed. Missing graph fields now render as incomplete analysis instead of invented reliability output.

## Benchmark Direction

Use `scripts/smoke_usecases.py` for fast product smoke coverage. Larger benchmark work should compare the full graph against baselines:

- single answer
- single answer with citations
- verbal confidence
- LLM judge only
- model agreement only
- semantic entropy only
- claim support only

Metrics to preserve: answer accuracy, claim support precision, contradiction detection, unsupported-claim detection, ECE, Brier score, risk coverage, false-safe rate, false-premise acceptance, and decision usefulness.

Use `scripts/calibrate_reliability_weights.py` after a dev eval run to fit a new score-weight config. Tune only on dev. Report held-out test/full metrics before claiming an improvement.

For research review, read `docs/REVIEW_READINESS.md` before presenting the score. It separates research-derived signals from product policy and lists the validation still needed for stronger calibration claims.
