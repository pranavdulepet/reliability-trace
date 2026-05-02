# ReliabilityGraph

ReliabilityGraph is a BYOK answer-reliability workspace for serious questions and decisions. It builds an observable Evidence Graph for a single answer: claims, evidence, assumptions, disagreement, robustness tests, scoring features, trace spans, calibration status, and optional Tinker causal-probe metadata.

## Local Run

```bash
cp .env.example .env
python3 -m uvicorn backend.reliability_graph.api:app --reload --port 8000
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

Provider keys are sent only to the backend. Saved keys are encrypted before they are written to the local SQLite database, and plaintext keys are never returned to the browser.

Docker is optional:

```bash
docker compose up --build
```

## Checks

```bash
python3 -m pytest
cd frontend && npm run build
```

## Current Shape

- `backend/reliability_graph`: FastAPI API, SQLite storage, encrypted key vault, provider adapters, reliability graph pipeline.
- `frontend/src`: React + TypeScript workbench for key management, chat/run creation, SSE trace streaming, report tabs, and JSON export.
- `docs`: short architecture and operating docs written for both engineers and AI coding assistants.
- `tests`: direct tests for scoring, encryption, provider safety, and graph generation.

## Safety Defaults

- The frontend never calls model providers.
- Live provider calls are opt-in per run.
- Runs have sample limits and user-visible cost caps.
- The score is a diagnostic `X / 100`, not a calibrated correctness probability.
- Closed-provider output is treated as observable behavior only; Tinker causal-probe mode is clearly labeled separately.
