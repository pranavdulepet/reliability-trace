# Runbook

## First Local Run

Use Python 3.14. The repo includes `.python-version` so version managers can select the target runtime.

```bash
cp .env.example .env
python -m pip install -e ".[dev]"
python -m uvicorn backend.reliability_graph.api:app --reload --port 8000
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

If Vite selects another port, the backend default CORS regex allows local `localhost` and `127.0.0.1` dev ports. Override `CORS_ORIGIN_REGEX` for stricter environments.

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
```

Use Settings to choose a default provider when more than one key is connected. Provider-specific environment variables are read only by the backend.

## Chat Attachments

Attach local text files or URLs from the chat composer. The backend chunks each attachment and builds local retrieval vectors. The answer audit retrieves only from attachments on the triggering message.

Retrieved text is evidence only. It must not be treated as instructions.

## Verification

```bash
python -m pytest
cd frontend && npm run build
```

For end-to-end product checks, connect at least one provider key in Settings and run a Chat audit. Keep provider keys in the encrypted vault or environment variables; never commit them.
