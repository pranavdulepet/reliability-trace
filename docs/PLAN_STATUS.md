# Plan Status

Read this with `plan.md`. The plan is a strong product specification, but the implementation is not the complete final product yet.

## Implemented

- React workbench with provider vault, run creation, streamed audit timeline, run history, source view, benchmark view, settings, report tabs, and JSON export.
- FastAPI backend with SQLite persistence, encrypted provider key storage, provider metadata, run streaming, run export, labels, and health checks.
- Provider adapters for Tinker, OpenAI, Claude, Gemini, and OpenRouter behind one backend-only boundary.
- Reliability Evidence Graph pipeline with candidate generation, claim extraction, document/source retrieval, claim-to-source matching, assumptions, disagreement, stress checks, scoring features, score caps, calibration status, and Tinker perturbation metadata.
- Source library with pasted document indexing, local text-file ingestion in the browser, URL fetch, chunking, local hashed retrieval vectors, and chunk search.
- Local benchmark report with calibration buckets, ECE, Brier score, and leave-signal-out ablations from labeled completed runs.
- Live Tinker perturbation probe for Tinker runs that checks answer stability under neutral paraphrase, false-premise pressure, and authority pressure.
- Security defaults: provider keys never enter frontend code, saved keys are encrypted, exports exclude plaintext keys, and live provider calls are opt-in per run.
- Direct tests for graph shape, scoring behavior, provider payload safety, key storage, API behavior, and Tinker-compatible request handling.

## Not Complete

- Broad web search with source discovery, dedupe, freshness handling, and hostile-document defenses beyond source-bound snippets.
- Robust LLM-structured claim extraction, evidence assessment, assumption extraction, and judge rubrics across providers.
- Full Tinker True-Thinking-style logprob causal measurements.
- Large empirical benchmark calibration for score quality, risk coverage, and ablations.
- Hosted product capabilities: auth, workspaces, billing, rate limits, object storage, managed Postgres, audit logs, and admin controls.
- Binary/PDF document extraction and provider-backed embedding options.

## Highest-Leverage Strengthenings

- Add broad web search next: source discovery, dedupe, freshness scoring, robots/rate-limit handling, and source-type classifiers.
- Expand the benchmark harness: labeled datasets, run manifests, calibration plots, risk coverage, and task-specific reports.
- Add full Tinker logprob causal probes if the Tinker SDK/cookbook path is installed.
- Keep the UI progressive: ask first, reveal provider/options only when useful, keep evidence tables dense but calm, and move research-heavy detail behind tabs.
- Preserve the product promise: show observable evidence behind an answer; never imply hidden chain-of-thought access.
