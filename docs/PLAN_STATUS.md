# Plan Status

Read this with `plan.md`. The plan is a strong product specification, but the implementation is not the complete final product yet.

## Implemented

- Chat-first React UI with multi-turn threads, composer attachments, generated answers, reliability cards, collapsible activity, About, Settings, and JSON export.
- FastAPI backend with SQLite persistence, conversation/message storage, encrypted provider key storage, provider preferences, run streaming, run export, labels, and health checks.
- Provider adapters for Tinker, OpenAI, Claude, Gemini, and OpenRouter behind one backend-only boundary.
- Reliability Evidence Graph pipeline with candidate generation, claim extraction, attachment-scoped retrieval, claim-to-source matching, assumptions, disagreement, stress checks, scoring features, score caps, calibration status, and provider-neutral perturbation metadata.
- Answer-specific verdicts, evidence status, uncertainty, next action, source limitations, and claim relations.
- Provider-backed structured claim extraction with strict JSON validation and retry on invalid JSON, with deterministic fallback.
- Source ingestion for chat file/URL attachments, chunking, local hashed retrieval vectors, and chunk search.
- Research router with quiet Auto search, manual On/Off override, Tavily-backed web retrieval, source dedupe, search activity, citations, and graph fields for search mode/search use.
- URL fetch hardening for private networks, credentials, redirects, content type, response size, and duplicate URL/content reuse.
- Local benchmark report with calibration buckets, ECE, Brier score, and leave-signal-out ablations from labeled completed runs.
- Live provider perturbation checks for connected provider runs.
- Security defaults: provider keys never enter frontend code, saved keys are encrypted, exports exclude plaintext keys, and the main UI requires a connected provider before answer generation.
- Direct tests for graph shape, scoring behavior, provider payload safety, key storage, conversation storage, attachment-scoped retrieval, URL fetch hardening, API behavior, and provider-compatible request handling.
- Sample-usecase smoke harness for general chat, source/no-source cases, decision questions, high-stakes caution, prompt-injection attachments, provider unavailable, and malformed provider output.

## Not Complete

- Multi-provider search abstraction beyond Tavily, domain/source reputation classifiers, and richer freshness scoring.
- Provider-backed structured evidence assessment, assumption extraction, and judge rubrics across providers.
- Full logprob-based robustness measurements.
- Large empirical benchmark calibration for score quality, risk coverage, and ablations.
- Hosted product capabilities: auth, workspaces, billing, rate limits, object storage, managed Postgres, audit logs, and admin controls.
- Binary/PDF document extraction and provider-backed embedding options.
- Provider-returned reasoning traces beyond observable prompts, outputs, tools, and run events.

## Highest-Leverage Strengthenings

- Strengthen web search next: source reputation, richer query planning, follow-up searches when first-pass evidence is weak, robots/rate-limit handling, and source-type classifiers.
- Expand the benchmark harness: labeled datasets, run manifests, calibration plots, risk coverage, and task-specific reports.
- Add full logprob robustness probes where provider APIs expose the needed measurements.
- Keep the UI progressive: ask first, reveal provider/options only when useful, keep evidence tables dense but calm, and move research-heavy detail behind tabs or About.
- Preserve the product promise: show observable evidence behind an answer; never imply hidden chain-of-thought access.
