# ReliabilityGraph

ReliabilityGraph is a BYOK chat app for serious questions and decisions. Each assistant answer includes an observable Reliability Evidence Graph: extracted claims, attached-source evidence, assumptions, disagreement, robustness checks, scoring features, activity trace, calibration status, and exportable metadata.

## Local Run

Use Python 3.14. Python.org lists Python 3.14 as the current stable bugfix line; this repo targets that line and includes `.python-version` for version managers.

```bash
cp .env.example .env
python -m pip install -e ".[dev]"
python scripts/setup_nli_verifier.py
python -m uvicorn backend.reliability_graph.api:app --reload --port 8000
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

Provider keys are sent only to the backend. Saved keys are encrypted before they are written to the local SQLite database, and plaintext keys are never returned to the browser. Chat runs require a connected LLM provider and a ready NLI verifier; if either is missing, the app shows a setup error instead of producing a synthetic answer.

Docker is optional:

```bash
docker compose up --build
```

For a public demo on Render, see `docs/DEPLOYMENT.md`. The Render deployment serves the frontend and backend from one web service so SSE streaming, cookies, and API calls stay same-origin.

## Checks

```bash
python -m pytest
cd frontend && npm run build
```

## Current Shape

- `backend/reliability_graph`: FastAPI API, SQLite storage, encrypted key vault, source retrieval, benchmark reporting, provider adapters, reliability graph pipeline.
- `scripts/run_reliability_evals.py`: external official-style benchmark harness for RAGTruth, SelfCheckGPT WikiBio, and SimpleQA.
- `frontend/src`: React + TypeScript chat UI for provider settings, message attachments, SSE activity streaming, answer-integrated reliability cards, details, and JSON export.
- `docs`: short architecture and operating docs written for both engineers and AI coding assistants.
- `tests`: direct tests for scoring, encryption, provider safety, retrieval, benchmark reporting, and graph generation.

## Safety Defaults

- The frontend never calls model providers.
- Production chat never falls back to local synthetic answers or fake audit outputs.
- Runs have sample limits and user-visible cost caps.
- The score is a diagnostic `X / 100`, not a calibrated correctness probability.
- Provider output is treated as observable behavior only. Robustness checks do not reveal hidden reasoning.
