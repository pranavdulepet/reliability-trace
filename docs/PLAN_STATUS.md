# Plan Status

Read this with `plan.md`. The plan is a strong product specification, but the implementation is not the complete final product yet.

## Implemented

- React workbench with provider vault, run creation, streamed audit timeline, run history, source view, benchmark view, settings, report tabs, and JSON export.
- FastAPI backend with SQLite persistence, encrypted provider key storage, provider metadata, run streaming, run export, labels, and health checks.
- Provider adapters for Tinker, OpenAI, Claude, Gemini, and OpenRouter behind one backend-only boundary.
- Reliability Evidence Graph pipeline with candidate generation, claim extraction, evidence-shaped records, assumptions, disagreement, stress checks, scoring features, score caps, calibration status, and causal-probe metadata.
- Security defaults: provider keys never enter frontend code, saved keys are encrypted, exports exclude plaintext keys, and live provider calls are opt-in per run.
- Direct tests for graph shape, scoring behavior, provider payload safety, key storage, API behavior, and Tinker-compatible request handling.

## Not Complete

- Real web/document retrieval with source ranking, dedupe, freshness handling, and hostile-document defenses.
- Robust LLM-structured claim extraction, evidence assessment, assumption extraction, and judge rubrics across providers.
- Tinker perturbation probes and True-Thinking-style causal measurements beyond current metadata plumbing.
- Empirical benchmark calibration for score quality, risk coverage, and ablations.
- Hosted product capabilities: auth, workspaces, billing, rate limits, object storage, managed Postgres, audit logs, and admin controls.
- User-uploaded document ingestion, chunking, embedding, and retrieval.

## Highest-Leverage Strengthenings

- Add a retrieval layer first: source ingestion, URL/document provenance, claim-to-source matching, and evidence quality scoring.
- Build a benchmark harness second: labeled datasets, run manifests, calibration plots, ablations, and score reliability reports.
- Make Tinker causal probes real third: logprob-aware variants, perturbation operations, and visible probe confidence.
- Keep the UI progressive: ask first, reveal provider/options only when useful, keep evidence tables dense but calm, and move research-heavy detail behind tabs.
- Preserve the product promise: show observable evidence behind an answer; never imply hidden chain-of-thought access.
