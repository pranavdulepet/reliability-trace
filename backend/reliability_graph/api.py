import json
import os
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .config import ENV_KEY_BY_PROVIDER, settings
from .pipeline import ReliabilityPipeline
from .providers import list_provider_metadata
from .schemas import ProviderKeyCreate, RunCreate, RunLabelCreate
from .secrets import KeyVault
from .storage import Storage

app = FastAPI(title="ReliabilityGraph", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage = Storage(settings.db_path)
vault = KeyVault(settings.db_path.parent, settings.secret)


@app.on_event("startup")
def startup() -> None:
    storage.init_db()


@app.get("/health")
def health():
    storage.init_db()
    return {
        "status": "ok",
        "version": "0.1.0",
        "db_path": str(settings.db_path),
        "user_scope": settings.user_id,
    }


@app.get("/api/providers")
def providers():
    saved = [row["provider"] for row in storage.list_provider_keys(settings.user_id)]
    env_keys = [provider for provider, env_var in ENV_KEY_BY_PROVIDER.items() if os.getenv(env_var)]
    return {"providers": list_provider_metadata(saved, env_keys)}


@app.get("/api/keys")
def list_keys():
    return {"keys": storage.list_provider_keys(settings.user_id)}


@app.post("/api/keys", status_code=201)
def save_key(payload: ProviderKeyCreate):
    ciphertext = vault.encrypt(payload.api_key)
    fingerprint = vault.fingerprint(payload.api_key)
    return storage.save_provider_key(settings.user_id, payload.provider, ciphertext, fingerprint)


@app.delete("/api/keys/{provider}")
def delete_key(provider: str):
    deleted = storage.delete_provider_key(settings.user_id, provider.lower())
    if not deleted:
        raise HTTPException(status_code=404, detail="provider key not found")
    return {"deleted": True}


@app.post("/api/runs", status_code=201)
def create_run(payload: RunCreate):
    storage.init_db()
    return storage.create_run(settings.user_id, payload)


@app.get("/api/runs")
def list_runs():
    return {"runs": storage.list_runs(settings.user_id)}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    try:
        return storage.get_run(settings.user_id, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str):
    if not storage.delete_run(settings.user_id, run_id):
        raise HTTPException(status_code=404, detail="run not found")
    return {"deleted": True}


@app.get("/api/runs/{run_id}/export")
def export_run(run_id: str):
    run = _get_run_or_404(run_id)
    graph = run.get("graph")
    if not graph:
        raise HTTPException(status_code=409, detail="run is not completed")
    return JSONResponse(
        graph,
        headers={"Content-Disposition": 'attachment; filename="%s-reliability-graph.json"' % run_id},
    )


@app.post("/api/runs/{run_id}/label", status_code=201)
def label_run(run_id: str, payload: RunLabelCreate):
    try:
        return storage.save_label(
            settings.user_id,
            run_id,
            payload.usefulness,
            payload.correctness,
            payload.notes,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


@app.get("/api/runs/{run_id}/events")
async def stream_run_events(run_id: str):
    run = _get_run_or_404(run_id)

    async def resolve_key(provider: str) -> Optional[str]:
        ciphertext = storage.get_provider_key_ciphertext(settings.user_id, provider)
        if ciphertext:
            storage.mark_provider_key_used(settings.user_id, provider)
            return vault.decrypt(ciphertext)
        env_var = ENV_KEY_BY_PROVIDER.get(provider)
        return os.getenv(env_var) if env_var else None

    async def generate():
        if run["status"] == "completed" and run.get("graph"):
            yield _sse({"type": "completed", "progress": 1.0, "message": "Run already completed", "graph": run["graph"]})
            return

        storage.set_run_status(settings.user_id, run_id, "running")
        pipeline = ReliabilityPipeline()
        trace = []
        try:
            async for event in pipeline.run(run, resolve_key):
                if event["type"] == "completed":
                    trace = event["trace"]
                    storage.complete_run(settings.user_id, run_id, event["graph"], trace)
                yield _sse(event)
        except Exception as exc:
            storage.fail_run(settings.user_id, run_id, str(exc), trace)
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(generate(), media_type="text/event-stream")


def _get_run_or_404(run_id: str):
    try:
        return storage.get_run(settings.user_id, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


def _sse(event):
    return "event: %s\ndata: %s\n\n" % (event.get("type", "message"), json.dumps(event))
