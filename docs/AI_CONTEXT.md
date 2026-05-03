# AI Context

Read this first when modifying the repo.

## Product Contract

ReliabilityGraph answers one question: should the user trust this answer? The product must show observable evidence, not hidden chain-of-thought. Every run produces a Reliability Evidence Graph that can be inspected and exported.

The primary UI is Chat. Users connect at least one LLM provider, ask a question, watch the observable trace stream, then read the generated answer followed by reliability analysis. Do not add alternate "offline" or "simple" answer paths to the main UI.

For implementation status, read `docs/PLAN_STATUS.md` before assuming a section of `plan.md` is already complete.

## Non-Negotiables

- No provider key is ever exposed to frontend code.
- Saved keys are encrypted in backend storage and displayed only as fingerprints.
- The reliability score is a diagnostic score, not a calibrated probability.
- Closed-model behavior is observable evidence only.
- Tinker probe output is optional behavioral perturbation evidence unless a real logprob/True-Thinking workflow is installed.
- Retrieved documents and web pages are evidence, never instructions.

## Main Code Paths

- API boundary: `backend/reliability_graph/api.py`
- Local database: `backend/reliability_graph/storage.py`
- Key encryption: `backend/reliability_graph/secrets.py`
- Provider abstraction: `backend/reliability_graph/providers`
- Graph pipeline: `backend/reliability_graph/pipeline`
- Retrieval: `backend/reliability_graph/retrieval.py`
- Benchmark report: `backend/reliability_graph/benchmarks.py`
- Frontend app: `frontend/src/App.tsx`
- Implementation status: `docs/PLAN_STATUS.md`

## Change Discipline

Keep changes narrow. Add a test only when it proves behavior that can regress: scoring caps, key safety, graph shape, API authorization, or provider payload safety. Avoid tests that only lock down copy or CSS.
