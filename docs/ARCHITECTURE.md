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
    -> Reliability Evidence Graph pipeline
```

The frontend manages chat UI state and streams trace events. The backend owns all sensitive work: provider calls, key storage, provider defaults, conversation persistence, source ingestion, graph generation, export, cancellation, and retrieval.

## Backend

The backend exposes REST endpoints for keys, provider preferences, conversations, messages, runs, labels, export, and health. Run progress streams over Server-Sent Events from `/api/runs/{run_id}/events`.

SQLite is the local storage target because it keeps setup small. The storage layer is deliberately isolated so hosted mode can move to Postgres without changing the frontend contract. Documents, fetched pages, and web search results are chunked and embedded with local hashed vectors. Chat retrieval is scoped to the files, URLs, and web results selected for the triggering message.

URL fetch rejects credentials, loopback/private/link-local hosts, unsafe redirects, unsupported content types, and oversized responses. Duplicate documents are reused by URL or content hash.

Before answer generation, a provider-neutral research router chooses:

- `no_search` for stable explanations, creative work, coding help, math, brainstorming, or explicit no-web requests.
- `attachments_only` when the user asks about uploaded files or attached URLs.
- `web_search` for current, recent, local, high-stakes factual, recommendation, policy, price, news, or explicit search questions.
- `hybrid` when attachments are present but the user asks beyond them.

Web retrieval uses Tavily first, with `include_answer=false`; search results are source evidence, not instructions, and the configured LLM still writes the answer. This follows the public tool-use pattern used by ChatGPT Search, Claude web search, Gemini grounding, and agent-search APIs: choose whether search is needed, rewrite the user need into a targeted query, retrieve sources, then answer with citations and visible tool activity.

The pipeline emits provider-neutral verdict fields on every completed graph:

- `answer.verdict`: `rely`, `use_with_caution`, or `do_not_rely`
- `answer.evidence_status`
- `answer.main_uncertainty`
- `answer.next_best_action`
- `answer.citations[]`
- `answer.final_decision`
- `claim_assessments[].relation`
- `analysis_basis[]`
- `run.search_mode`
- `run.search_used`
- `web_search.calls[]`

Reliability scoring is diagnostic. Source-required questions are weighted toward claim support, retrieval alignment, and source quality; open-ended explanations weight sample consistency more heavily. The score does not use trace completeness, hard-coded judge dimensions, or fabricated decision utilities. Factual/current answers with no source evidence are capped and returned as `do_not_rely`. General answers without sources are marked not source-grounded instead of treated as failed factual retrieval.

## Frontend

The frontend is a React + TypeScript app. It presents:

- Chat-first question flow with provider-backed answer generation.
- Conversation history and multi-turn message threads.
- Composer attachments for local text files and URLs.
- Provider keys and default model controls in Settings.
- Search key and default search controls in Settings, plus a small composer tools menu for Auto/On/Off per message.
- Collapsible activity for provider calls, retrieval, checks, probes, and scoring.
- About page with the research basis and trace limits.
- Answer-integrated reliability cards and expandable details for claims, sources, disagreement, checks, calibration, perturbation, and export.

The primary answer view is progressive: answer first, compact trust row second, detailed evidence tables only inside expandable sections.

## Provider Boundary

Providers implement one internal interface: `generate`, `stream_generate`, `generate_structured`, and optional `embed`, `logprobs`, `tool_call`. Provider SDKs are not required; adapters use backend-side HTTP calls so the browser never sees keys.

Search is a separate provider boundary from LLM generation. Search providers return URLs, snippets, and raw content for evidence indexing. They do not author final answers.
