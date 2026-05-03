# Research Basis

ReliabilityGraph uses research signals as diagnostics, not as proof that an answer is true.

## Signals

- `atomic_claim_support`: Inspired by FActScore and SAFE / LongFact. The pipeline decomposes the answer into checkable claims and matches each claim to attached or fetched source chunks. Limitation: local retrieval can miss paraphrases, context, and source quality nuance.
- `sample_consistency`: Inspired by SelfCheckGPT. Multiple samples are compared for answer stability. Limitation: models can agree on the same false claim.
- `semantic_entropy`: Inspired by semantic entropy work. The system tracks meaning-level disagreement instead of treating every wording difference as important. Limitation: the current local clustering is lightweight and should be calibrated with labels.
- `perturbation_check`: Behavioral pressure prompts test whether the answer flips under paraphrase, false-premise, or authority pressure. Limitation: this is observable behavior only, not access to hidden reasoning.
- `calibration`: Inspired by reliability diagrams, ECE, and Brier score. User-labeled runs produce a local calibration report. Limitation: scores remain diagnostic until labels cover the actual workload.
- `unfaithful_cot_guardrail`: Inspired by work showing chain-of-thought can be unfaithful. The UI shows observable steps, calls, outputs, checks, and scores; it does not promise hidden model reasoning traces.

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
