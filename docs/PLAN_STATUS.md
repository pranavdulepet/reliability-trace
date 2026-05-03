# Plan Status

Read this with `plan.md`. The plan is a strong product specification, but the implementation is not the complete final product yet.

## Implemented

- Chat-first React UI with multi-turn threads, composer attachments, generated answers, reliability cards, collapsible activity, About, Settings, and JSON export.
- FastAPI backend with SQLite persistence, conversation/message storage, encrypted provider key storage, provider preferences, run streaming, run export, labels, and health checks.
- Provider adapters for Tinker, OpenAI, Claude, Gemini, and OpenRouter behind one backend-only boundary.
- Reliability Evidence Graph pipeline with candidate generation, claim extraction, attachment-scoped retrieval, claim-to-source matching, assumptions, disagreement, stress checks, scoring features, score caps, calibration status, and provider-neutral perturbation metadata.
- Source ingestion for chat file/URL attachments, chunking, local hashed retrieval vectors, and chunk search.
- Local benchmark report with calibration buckets, ECE, Brier score, and leave-signal-out ablations from labeled completed runs.
- Live provider perturbation checks for connected provider runs.
- Security defaults: provider keys never enter frontend code, saved keys are encrypted, exports exclude plaintext keys, and the main UI requires a connected provider before answer generation.
- Direct tests for graph shape, scoring behavior, provider payload safety, key storage, conversation storage, attachment-scoped retrieval, API behavior, and provider-compatible request handling.

## Not Complete

- Broad web search with source discovery, dedupe, freshness handling, and hostile-document defenses beyond source-bound snippets.
- Robust LLM-structured claim extraction, evidence assessment, assumption extraction, and judge rubrics across providers.
- Full logprob-based causal measurements.
- Large empirical benchmark calibration for score quality, risk coverage, and ablations.
- Hosted product capabilities: auth, workspaces, billing, rate limits, object storage, managed Postgres, audit logs, and admin controls.
- Binary/PDF document extraction and provider-backed embedding options.
- Provider-returned reasoning traces beyond observable prompts, outputs, tools, and run events.

## Highest-Leverage Strengthenings

- Add broad web search next: source discovery, dedupe, freshness scoring, robots/rate-limit handling, and source-type classifiers.
- Expand the benchmark harness: labeled datasets, run manifests, calibration plots, risk coverage, and task-specific reports.
- Add full logprob causal probes where provider APIs expose the needed measurements.
- Keep the UI progressive: ask first, reveal provider/options only when useful, keep evidence tables dense but calm, and move research-heavy detail behind tabs or About.
- Preserve the product promise: show observable evidence behind an answer; never imply hidden chain-of-thought access.
