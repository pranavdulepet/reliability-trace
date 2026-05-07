FROM node:24-slim AS frontend-builder

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.14-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY backend ./backend
COPY configs ./configs
COPY scripts/setup_nli_verifier.py ./scripts/setup_nli_verifier.py
COPY --from=frontend-builder /frontend/dist ./frontend/dist

RUN pip install --no-cache-dir -e .
RUN python scripts/setup_nli_verifier.py --output-dir /app/model-cache/nli-deberta-base

ENV RG_NLI_MODEL_DIR=/app/model-cache/nli-deberta-base
ENV RELIABILITY_GRAPH_FRONTEND_DIST=/app/frontend/dist

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn backend.reliability_graph.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
