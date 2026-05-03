import hashlib
import json
import os
import re
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .benchmarks import build_benchmark_report
from .config import ENV_KEY_BY_PROVIDER, settings
from .pipeline import ReliabilityPipeline
from .providers import list_provider_metadata
from .retrieval import build_chunks, fetch_url_text, search_chunks
from .schemas import (
    ConversationCreate,
    ConversationMessageCreate,
    DocumentCreate,
    ProviderKeyCreate,
    ProviderPreferenceUpdate,
    RunCreate,
    RunLabelCreate,
    SourceFetchCreate,
)
from .secrets import KeyVault
from .storage import Storage

app = FastAPI(title="ReliabilityGraph", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
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


@app.get("/api/provider-preferences")
def get_provider_preferences():
    preference = storage.get_provider_preference(settings.user_id)
    return {"preference": preference, "resolved": _resolve_provider_defaults(None, strict=False)}


@app.put("/api/provider-preferences")
def save_provider_preferences(payload: ProviderPreferenceUpdate):
    if payload.provider and payload.provider not in _connected_providers():
        raise HTTPException(status_code=400, detail="provider is not connected")
    preference = storage.save_provider_preference(
        settings.user_id,
        payload.provider,
        payload.model.strip() if payload.model else None,
        payload.samples,
        payload.max_cost_usd,
    )
    return {"preference": preference, "resolved": _resolve_provider_defaults(None, strict=False)}


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
    payload = _run_with_provider_defaults(payload)
    return storage.create_run(settings.user_id, payload)


@app.get("/api/runs")
def list_runs():
    return {"runs": storage.list_runs(settings.user_id)}


@app.get("/api/conversations")
def list_conversations():
    return {"conversations": storage.list_conversations(settings.user_id)}


@app.post("/api/conversations", status_code=201)
def create_conversation(payload: ConversationCreate):
    return storage.create_conversation(settings.user_id, payload.title)


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    try:
        return storage.get_conversation(settings.user_id, conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="conversation not found") from exc


@app.post("/api/conversations/{conversation_id}/messages", status_code=201)
def create_conversation_message(conversation_id: str, payload: ConversationMessageCreate):
    try:
        conversation = storage.get_conversation(settings.user_id, conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="conversation not found") from exc

    attachment_document_ids = _validate_attachment_document_ids(payload.attachment_document_ids)
    prior_context = [
        {"role": message["role"], "content": message["content"][:1800]}
        for message in conversation["messages"][-10:]
        if message["role"] in {"user", "assistant"}
    ]
    user_message = storage.add_message(
        settings.user_id,
        conversation_id,
        "user",
        payload.content.strip(),
        attachment_document_ids=attachment_document_ids,
    )
    if len(conversation["messages"]) == 0:
        storage.update_conversation_title(settings.user_id, conversation_id, _conversation_title(payload.content))

    run_payload = _run_with_provider_defaults(
        RunCreate(
            question=payload.content.strip(),
            provider=payload.provider,
            model=payload.model,
            samples=payload.samples or storage.get_provider_preference(settings.user_id)["samples"],
            max_cost_usd=payload.max_cost_usd
            if payload.max_cost_usd is not None
            else storage.get_provider_preference(settings.user_id)["max_cost_usd"],
            use_live_provider=True,
            conversation_id=conversation_id,
            user_message_id=user_message["message_id"],
            prior_context=prior_context,
            attachment_document_ids=attachment_document_ids,
        )
    )
    run = storage.create_run(settings.user_id, run_payload)
    return {"message": user_message, "run": run}


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


@app.get("/api/documents")
def list_documents():
    return {"documents": storage.list_documents(settings.user_id)}


@app.post("/api/documents", status_code=201)
def save_document(payload: DocumentCreate):
    content_sha = hashlib.sha256(payload.text.encode("utf-8")).hexdigest()
    existing = storage.find_document_by_signature(settings.user_id, content_sha, payload.source_url)
    if existing:
        return existing
    chunks = build_chunks(payload.text)
    if not chunks:
        raise HTTPException(status_code=400, detail="document did not contain indexable text")
    return storage.save_document(
        settings.user_id,
        payload.title.strip(),
        payload.text,
        payload.source_url,
        payload.source_type.strip() or "uploaded_document",
        chunks,
    )


@app.post("/api/documents/fetch", status_code=201)
def fetch_document(payload: SourceFetchCreate):
    try:
        fetched = fetch_url_text(payload.url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=_sanitize_error(str(exc))) from exc
    content_sha = hashlib.sha256(fetched["text"].encode("utf-8")).hexdigest()
    existing = storage.find_document_by_signature(settings.user_id, content_sha, fetched["source_url"])
    if existing:
        return existing
    chunks = build_chunks(fetched["text"])
    if not chunks:
        raise HTTPException(status_code=400, detail="source did not contain indexable text")
    return storage.save_document(
        settings.user_id,
        fetched["title"][:300],
        fetched["text"],
        fetched["source_url"],
        "web_page",
        chunks,
    )


@app.get("/api/documents/search")
def search_documents(q: str = Query(min_length=1, max_length=1000), limit: int = Query(default=8, ge=1, le=30)):
    return {"matches": search_chunks(q, storage.list_document_chunks(settings.user_id), limit=limit)}


@app.get("/api/benchmarks/report")
def benchmark_report():
    return build_benchmark_report(storage.list_labeled_runs(settings.user_id))


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
            if run.get("conversation_id") and not storage.assistant_message_exists_for_run(settings.user_id, run_id):
                storage.add_message(
                    settings.user_id,
                    run["conversation_id"],
                    "assistant",
                    run["graph"]["answer"]["final_answer"],
                    run_id=run_id,
                )
            yield _sse({"type": "completed", "progress": 1.0, "message": "Run already completed", "graph": run["graph"]})
            return

        storage.set_run_status(settings.user_id, run_id, "running")
        attachment_document_ids = run.get("attachment_document_ids", [])
        pipeline = ReliabilityPipeline(
            retrieval_chunks=storage.list_document_chunks(settings.user_id, attachment_document_ids),
            calibration_report=build_benchmark_report(storage.list_labeled_runs(settings.user_id)),
        )
        trace = []
        try:
            async for event in pipeline.run(run, resolve_key):
                if event["type"] == "completed":
                    trace = event["trace"]
                    storage.complete_run(settings.user_id, run_id, event["graph"], trace)
                    if run.get("conversation_id") and not storage.assistant_message_exists_for_run(settings.user_id, run_id):
                        storage.add_message(
                            settings.user_id,
                            run["conversation_id"],
                            "assistant",
                            event["graph"]["answer"]["final_answer"],
                            run_id=run_id,
                        )
                yield _sse(event)
        except Exception as exc:
            message = _sanitize_error(str(exc))
            storage.fail_run(settings.user_id, run_id, message, trace)
            yield _sse({"type": "error", "message": message})

    return StreamingResponse(generate(), media_type="text/event-stream")


def _get_run_or_404(run_id: str):
    try:
        return storage.get_run(settings.user_id, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


def _connected_providers():
    saved = [row["provider"] for row in storage.list_provider_keys(settings.user_id)]
    env_keys = [provider for provider, env_var in ENV_KEY_BY_PROVIDER.items() if os.getenv(env_var)]
    return sorted(set(saved + env_keys))


def _resolve_provider_defaults(provider: Optional[str], strict: bool = True):
    connected = _connected_providers()
    preference = storage.get_provider_preference(settings.user_id)
    selected = provider or preference.get("provider")
    if selected:
        if selected not in connected:
            if not strict:
                return None
            raise HTTPException(status_code=400, detail="selected provider is not connected")
        return {
            "provider": selected,
            "model": preference.get("model"),
            "samples": preference.get("samples", 3),
            "max_cost_usd": preference.get("max_cost_usd", 1.0),
        }
    if len(connected) == 1:
        return {
            "provider": connected[0],
            "model": None,
            "samples": preference.get("samples", 3),
            "max_cost_usd": preference.get("max_cost_usd", 1.0),
        }
    if len(connected) == 0:
        if not strict:
            return None
        raise HTTPException(status_code=400, detail="connect an LLM provider in Settings before asking a question")
    if not strict:
        return None
    raise HTTPException(status_code=400, detail="choose a default provider in Settings")


def _run_with_provider_defaults(payload: RunCreate) -> RunCreate:
    defaults = _resolve_provider_defaults(payload.provider)
    preference = storage.get_provider_preference(settings.user_id)
    return payload.model_copy(
        update={
            "provider": defaults["provider"],
            "model": payload.model or preference.get("model") or defaults.get("model"),
            "samples": payload.samples or defaults["samples"],
            "max_cost_usd": payload.max_cost_usd if payload.max_cost_usd is not None else defaults["max_cost_usd"],
            "use_live_provider": True,
        }
    )


def _validate_attachment_document_ids(document_ids):
    if not document_ids:
        return []
    available = {document["document_id"] for document in storage.list_documents(settings.user_id)}
    missing = [document_id for document_id in document_ids if document_id not in available]
    if missing:
        raise HTTPException(status_code=400, detail="attachment document not found")
    return document_ids


def _conversation_title(content: str) -> str:
    title = " ".join(content.strip().split())
    return title[:56] + ("..." if len(title) > 56 else "")


def _sse(event):
    return "event: %s\ndata: %s\n\n" % (event.get("type", "message"), json.dumps(event))


SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"tml-[A-Za-z0-9_-]{12,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"AIza[A-Za-z0-9_-]{20,}"),
]


def _sanitize_error(message: str) -> str:
    cleaned = message
    for pattern in SECRET_PATTERNS:
        cleaned = pattern.sub(lambda match: (match.group(1) if match.lastindex else "") + "[redacted]", cleaned)
    return cleaned[:500]
