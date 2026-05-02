FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY backend ./backend

RUN pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "backend.reliability_graph.api:app", "--host", "0.0.0.0", "--port", "8000"]
