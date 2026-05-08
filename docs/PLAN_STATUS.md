# Plan Status

Read this with `plan.md`. The plan is a strong product specification, but the implementation is not the complete final product yet.

## Implemented

- Chat-first React UI with multi-turn threads, composer attachments, streamed generated answers, inline/source citations, one post-audit Reliability Score summary, question-specific score reason, why-it-matters copy, repair prompt chips, an Elicit-like full-analysis drawer, About, Settings, and JSON export.
- FastAPI backend with SQLite persistence, conversation/message storage, encrypted provider key storage, provider preferences, run streaming, run export, labels, and health checks.
- Provider adapters for Tinker, OpenAI, Claude, Gemini, and OpenRouter behind one backend-only boundary.
- Provider-strict v2 Reliability Evidence Graph pipeline with provider answer generation, evidence packet building, structured claim extraction, structured assumptions, structured evidence assessment, attachment/web scoped retrieval, claim-to-source matching, disagreement, static risk checks, scoring features, score caps, calibration metadata, and provider-neutral perturbation metadata.
- Local persistence of completed v2 graphs in SQLite `runs.graph_json` and traces in `runs.trace_json`; exports return the stored graph.
- SSE contract where `answer_delta` streams the answer, `audit_progress` reports audit stages, and `completed` is the first event containing the final Reliability Score.
- Answer-specific verdicts, evidence status, uncertainty, next action, source limitations, claim relations, primary risk, reduced score breakdown, and concrete reliability-improvement prompts.
- Provider-backed structured claim extraction, assumption extraction, decision framing, and evidence assessment with strict JSON validation, retry on invalid JSON, redaction, and stage-specific failure when required provider work fails.
- Required NLI entailment-verifier boundary for claim/source relations, including setup health, Settings readiness, setup script, and graph fields for verifier scores.
- Source ingestion for chat file/URL attachments, chunking, local hashed retrieval vectors, and chunk search.
- Always-on chat web retrieval with Tavily-backed source discovery, missing-search-key degradation, source dedupe, search activity, citations, inline citation annotations, and graph fields for search mode/search use.
- Graph validation before completion so required reliability fields, score metadata, citations, and claim/evidence references cannot silently render as invented frontend state.
- URL fetch hardening for private networks, credentials, redirects, content type, response size, and duplicate URL/content reuse.
- Local benchmark report with calibration buckets, ECE, Brier score, and leave-signal-out ablations from labeled completed runs.
- External eval harness plus benchmark-tuned linear score weights in `configs/reliability_score_weights.json`; source-required answers use evidence-first weighting and safety caps remain explicit product policy. `docs/REVIEW_READINESS.md` states the current scientific claim boundary and validation gaps for research review.
- RAG/source-grounding hardening for meta-claim filtering, wider per-claim evidence retrieval, structured negation, unit-aware numeric contradiction checks, source-grounded summary overreach checks, unresolved source-conflict surfacing, and web-result published-date preservation.
- Live provider perturbation checks for connected provider runs.
- Security defaults: provider keys never enter frontend code, saved keys are encrypted, exports exclude plaintext keys, and the main UI requires a connected provider plus ready entailment verifier before answer generation.
- Direct tests for graph shape, scoring behavior, provider payload safety, key storage, conversation storage, attachment-scoped retrieval, URL fetch hardening, API behavior, and provider-compatible request handling.
- Sample-usecase smoke harness for general chat, source/no-source cases, decision questions, high-stakes caution, prompt-injection attachments, provider unavailable, and malformed provider output.

## Not Complete

- Multi-provider search abstraction beyond Tavily, domain/source reputation classifiers, and richer freshness scoring.
- A downloaded production verifier model in every local environment; run `python scripts/setup_nli_verifier.py` after installing dependencies.
- Full benchmark calibration of the provider+NLI claim verifier on large held-out runs.
- Full logprob-based robustness measurements.
- Large full-dataset empirical calibration for score quality, risk coverage, and ablations beyond the current official-style dev/held-out gates.
- Hosted product capabilities: auth, workspaces, billing, rate limits, object storage, managed Postgres, audit logs, and admin controls.
- Binary/PDF document extraction and provider-backed embedding options.
- Provider-returned reasoning traces beyond observable prompts, outputs, tools, and run events.

## Highest-Leverage Strengthenings

- Strengthen web search next: source reputation, richer query planning, follow-up searches when first-pass evidence is weak, robots/rate-limit handling, and source-type classifiers.
- Expand the benchmark harness: labeled datasets, run manifests, calibration plots, risk coverage, and task-specific reports.
- Add full logprob robustness probes where provider APIs expose the needed measurements.
- Keep the UI progressive: stream the answer first, keep reliability summary focused on score/reason/matter/repair, keep evidence tables dense but calm, and move research-heavy detail behind tabs or About.
- Preserve the product promise: show observable evidence behind an answer; never imply hidden chain-of-thought access.
