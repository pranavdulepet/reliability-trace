# Architecture

ReliabilityGraph is a local-first browser app with a separate backend.

```text
React UI
  -> FastAPI backend
    -> SQLite local database
    -> encrypted provider key vault
    -> provider adapters
    -> Reliability Evidence Graph pipeline
```

The frontend manages UI state and streams trace events. The backend owns all sensitive work: provider calls, key storage, persistence, graph generation, export, cancellation, and future document retrieval.

## Backend

The backend exposes REST endpoints for keys, runs, labels, export, and health. Run progress streams over Server-Sent Events from `/api/runs/{run_id}/events`.

SQLite is the local storage target because it keeps setup small. The storage layer is deliberately isolated so hosted mode can move to Postgres without changing the frontend contract.

## Frontend

The frontend is a React + TypeScript app. It presents:

- Provider key status and add/rotate/delete controls.
- A question workbench with cost/sample controls.
- A live trace panel.
- Report tabs for Answer, Claims, Evidence, Assumptions, Decision Analysis, Disagreement, Stress Tests, Trace, Calibration, Causal Probe, and Export.

## Provider Boundary

Providers implement one internal interface: `generate`, `stream_generate`, `generate_structured`, and optional `embed`, `logprobs`, `tool_call`. Provider SDKs are not required; adapters use backend-side HTTP calls so the browser never sees keys.
