# Architecture

ReliabilityGraph is a local-first browser app with a separate backend.

```text
React UI
  -> FastAPI backend
    -> SQLite local database
    -> encrypted provider key vault
    -> document/source index
    -> provider adapters
    -> Reliability Evidence Graph pipeline
```

The frontend manages UI state and streams trace events. The backend owns all sensitive work: provider calls, key storage, persistence, source ingestion, graph generation, export, cancellation, and retrieval.

## Backend

The backend exposes REST endpoints for keys, runs, labels, export, and health. Run progress streams over Server-Sent Events from `/api/runs/{run_id}/events`.

SQLite is the local storage target because it keeps setup small. The storage layer is deliberately isolated so hosted mode can move to Postgres without changing the frontend contract. Documents and fetched pages are chunked and embedded with local hashed vectors for retrieval.

## Frontend

The frontend is a React + TypeScript app. It presents:

- Chat-first question flow with provider-backed answer generation.
- Provider vault and readiness controls.
- Source upload, URL fetch, source search, and run evidence review.
- A live observable trace panel for provider calls, retrieval, checks, probes, and scoring.
- About page with the research basis and trace limits.
- Report tabs for Summary, Claims, Sources, Assumptions, Decision, Disagreement, Checks, Calibration, Tinker Probe, and Export.

## Provider Boundary

Providers implement one internal interface: `generate`, `stream_generate`, `generate_structured`, and optional `embed`, `logprobs`, `tool_call`. Provider SDKs are not required; adapters use backend-side HTTP calls so the browser never sees keys.
