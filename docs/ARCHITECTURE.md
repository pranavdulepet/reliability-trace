# Architecture

ReliabilityGraph is a local-first browser app with a separate backend.

```text
React UI
  -> FastAPI backend
    -> SQLite local database
    -> encrypted provider key vault
    -> conversation and message store
    -> document/source index
    -> provider adapters
    -> Reliability Evidence Graph pipeline
```

The frontend manages chat UI state and streams trace events. The backend owns all sensitive work: provider calls, key storage, provider defaults, conversation persistence, source ingestion, graph generation, export, cancellation, and retrieval.

## Backend

The backend exposes REST endpoints for keys, provider preferences, conversations, messages, runs, labels, export, and health. Run progress streams over Server-Sent Events from `/api/runs/{run_id}/events`.

SQLite is the local storage target because it keeps setup small. The storage layer is deliberately isolated so hosted mode can move to Postgres without changing the frontend contract. Documents and fetched pages are chunked and embedded with local hashed vectors. Chat retrieval is scoped to the files and URLs attached to the triggering message.

URL fetch rejects credentials, loopback/private/link-local hosts, unsafe redirects, unsupported content types, and oversized responses. Duplicate documents are reused by URL or content hash.

The pipeline emits provider-neutral verdict fields on every completed graph:

- `answer.verdict`: `rely`, `use_with_caution`, or `do_not_rely`
- `answer.evidence_status`
- `answer.main_uncertainty`
- `answer.next_best_action`
- `claim_assessments[].relation`
- `analysis_basis[]`

## Frontend

The frontend is a React + TypeScript app. It presents:

- Chat-first question flow with provider-backed answer generation.
- Conversation history and multi-turn message threads.
- Composer attachments for local text files and URLs.
- Provider keys and default model controls in Settings.
- Collapsible activity for provider calls, retrieval, checks, probes, and scoring.
- About page with the research basis and trace limits.
- Answer-integrated reliability cards and expandable details for claims, sources, disagreement, checks, calibration, perturbation, and export.

The primary answer view is progressive: answer first, compact trust row second, detailed evidence tables only inside expandable sections.

## Provider Boundary

Providers implement one internal interface: `generate`, `stream_generate`, `generate_structured`, and optional `embed`, `logprobs`, `tool_call`. Provider SDKs are not required; adapters use backend-side HTTP calls so the browser never sees keys.
