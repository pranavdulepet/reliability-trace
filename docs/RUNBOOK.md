# Runbook

## First Local Run

```bash
cp .env.example .env
python3 -m uvicorn backend.reliability_graph.api:app --reload --port 8000
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

The backend stores local SQLite data in `./data`, which is ignored by git.

## Provider Keys

Use the UI to save keys, or set provider env vars in `.env`.

```text
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
OPENROUTER_API_KEY=
TINKER_API_KEY=
TINKER_BASE_URL=
TINKER_MODEL=
```

For Tinker live runs, provide a compatible base URL and model/checkpoint. Causal-probe mode is shown only for live Tinker runs with a `tinker://` model identifier.

## Verification

```bash
python3 -m pytest
cd frontend && npm run build
```

Use local diagnostic runs for fast UI checks. Enable live provider calls only when you want to spend API credits.
