FROM python:3.14-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY backend ./backend
COPY configs ./configs
COPY scripts/setup_nli_verifier.py ./scripts/setup_nli_verifier.py

RUN pip install --no-cache-dir -e .
RUN python scripts/setup_nli_verifier.py --output-dir /app/model-cache/nli-deberta-base

ENV RG_NLI_MODEL_DIR=/app/model-cache/nli-deberta-base

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn backend.reliability_graph.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
