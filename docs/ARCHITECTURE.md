# Architecture

ReliabilityGraph is a local-first browser app with a separate backend.

```text
React UI
  -> FastAPI backend
    -> SQLite local database
    -> encrypted provider key vault
    -> encrypted web search key vault
    -> conversation and message store
    -> document/source index
    -> research router and web retrieval
    -> provider adapters
    -> local NLI entailment verifier
    -> Reliability Evidence Graph pipeline
```

The frontend manages chat UI state and streams trace events. The backend owns all sensitive work: provider calls, key storage, provider defaults, conversation persistence, source ingestion, graph generation, export, cancellation, retrieval, and entailment verification.

## Backend

The backend exposes REST endpoints for keys, provider preferences, verifier health, conversations, messages, runs, labels, export, and health. Run progress streams over Server-Sent Events from `/api/runs/{run_id}/events`.

Production chat is provider-strict. The API rejects chat runs unless a real LLM provider is resolved and the local NLI verifier is ready. If answer generation, structured claim extraction, structured assumptions, structured decision support, structured evidence assessment, or the verifier fails after retry, the run fails with a stage-specific error instead of producing a synthetic substitute answer or audit.

SQLite is the local storage target because it keeps setup small. The storage layer is deliberately isolated so hosted mode can move to Postgres without changing the frontend contract. Documents, fetched pages, and web search results are chunked and embedded with local hashed vectors. Chat retrieval is scoped to the files, URLs, and web results selected for the triggering message.

URL fetch rejects credentials, loopback/private/link-local hosts, unsafe redirects, unsupported content types, and oversized responses. Duplicate documents are reused by URL or content hash.

Before answer generation, a provider-neutral research router records the retrieval plan. Normal chat attempts web evidence on every message when a search key is available:

- `no_search` for stable explanations, creative work, coding help, math, brainstorming, or explicit no-web requests.
- `attachments_only` when the user asks about uploaded files or attached URLs.
- `web_search` for current, recent, local, high-stakes factual, recommendation, policy, price, news, or explicit search questions.
- `hybrid` when attachments are present but the user asks beyond them.

Web retrieval uses Tavily first, with `include_answer=false`; search results are source evidence, not instructions, and the configured LLM still writes the answer. This follows the public tool-use pattern used by ChatGPT Search, Claude web search, Gemini grounding, and agent-search APIs: rewrite the user need into a targeted query, retrieve sources, then answer with citations and visible tool activity. If no search key is configured, current and factual answers are visibly degraded and capped rather than treated as source-grounded.

The pipeline writes a completed v2 reliability graph to SQLite `runs.graph_json` and the observable trace to `runs.trace_json`. Exports return that stored graph. Production SSE streams the answer first, then `audit_progress`; the `Reliability Score` is only present in the final `completed` graph after evidence building, claim audit, scoring, calibration lookup, and robustness checks finish.

Completed v2 graphs include:

- `graph_version: "v2"`
- `audit_status`
- `audit_completed_at`
- `score_model_version`
- `score_inputs`
- `score_caps`
- `claim_audit[]`
- `evidence_sources[]`
- `source_quality[]`
- `consistency_checks`
- `robustness_checks`
- `analysis_explanation`
- `calibration_metadata`
- `answer.verdict`: `rely`, `use_with_caution`, or `do_not_rely`
- `answer.reliability_score`
- `answer.reliability_explanation`
- `answer.reliability_reason`
- `answer.why_it_matters`
- `answer.primary_risk`
- `answer.improvement_prompts[]`
- `answer.score_breakdown`
- `answer.score_ready`
- `answer.evidence_status`
- `answer.main_uncertainty`
- `answer.next_best_action`
- `answer.citations[]`
- `answer.citation_annotations[]`
- `answer.final_decision`
- `claim_assessments[].relation`
- `analysis_basis[]`
- `run.search_mode`
- `run.search_used`
- `web_search.calls[]`

Reliability scoring is a 0-100 audit score for ranking answer risk under gathered evidence. It is not a provider confidence score or a calibrated probability unless the target distribution has been validated separately. Source-required questions are evidence-first: claim support, contradiction severity, retrieval alignment, and source quality dominate; stability can lower trust but cannot rescue unsupported factual claims. Open-ended explanations still use stability as a warning signal. Linear signal weights load from `configs/reliability_score_weights.json` when present; otherwise the built-in research-prior weights are used. The current tracked config is benchmark-tuned from official-style fixed-answer dev evals with an evidence-first product adjustment for source-required answers. Safety caps are not learned: they remain explicit policy for contradictions, missing required evidence, low-provenance partial support, sample conflict, and similar false-safe risks. The score does not use trace completeness, hard-coded judge dimensions, or fabricated decision utilities. Factual/current answers with no source evidence are capped and returned as `do_not_rely`. General answers without sources are marked not source-grounded instead of treated as failed factual retrieval.

Claim checking has two layers. The selected provider extracts claims and assesses only the retrieved evidence snippets. A required NLI verifier then checks each claim/snippet pair and combines with the provider judgment conservatively: contradiction wins, missing evidence remains `not_found`, and provider/verifier disagreement becomes partial support unless the verifier finds contradiction. Source text is always treated as untrusted evidence, never instructions; provider output is schema-validated, retried once on invalid JSON, and redacted. Claims marked `not_checkable` remain unscored even if a provider returns a supported relation.

## Frontend

The frontend is a React + TypeScript app. It presents:

- Chat-first question flow with provider-backed streaming answer generation.
- Conversation history and multi-turn message threads.
- Composer attachments for local text files and URLs.
- Provider keys and default model controls in Settings.
- Entailment verifier readiness in Settings.
- Search key and max-result controls in Settings. Chat does not expose a search off switch; web evidence is attempted automatically when configured.
- One compact Reliability Score summary after the audit finishes.
- A usefulness-first reliability block: score, reason for score, why it matters, and prompt chips that insert concrete follow-up requests into the composer.
- One full reliability analysis drawer with Elicit-like sections: Evidence, Uncertainty, Score, Activity, and Export.
- About page with the research basis and trace limits.

The primary answer view is progressive: streamed answer first, inline/source citations when evidence exists, then the final Reliability Score, concise reason, question-specific consequence, and improvement prompts after the audit completes. Detailed evidence tables stay inside the analysis drawer. The frontend must not invent fallback verdicts or evidence states; incomplete graphs show an incomplete-analysis state.

## Provider Boundary

Providers implement one internal interface: `generate`, `stream_generate`, `generate_structured`, and optional `embed`, `logprobs`, `tool_call`. Provider SDKs are not required; adapters use backend-side HTTP calls so the browser never sees keys. Provider failures are surfaced as structured run errors, not hidden fallbacks.

Search is a separate provider boundary from LLM generation. Search providers return URLs, snippets, and raw content for evidence indexing. They do not author final answers.
