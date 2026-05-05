import asyncio
import hashlib
import json
import os
import re
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from .benchmarks import build_benchmark_report
from .config import ENV_KEY_BY_PROVIDER, ENV_KEY_BY_SEARCH_PROVIDER, settings
from .pipeline import PipelineStageError, ReliabilityPipeline
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
    SearchKeyCreate,
    SearchPreferenceUpdate,
    SourceFetchCreate,
)
from .secrets import KeyVault
from .storage import Storage
from .verifier import build_entailment_verifier
from .web_search import choose_research_route, route_to_dict, search_tavily

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
entailment_verifier = build_entailment_verifier()


@app.on_event("startup")
def startup() -> None:
    storage.init_db()


@app.get("/health")
def health():
    storage.init_db()
    verifier = entailment_verifier.status()
    return {
        "status": "ok" if verifier["ready"] else "setup_required",
        "version": "0.1.0",
        "db_path": str(settings.db_path),
        "user_scope": settings.user_id,
        "verifier": verifier,
    }


@app.get("/api/providers")
def providers():
    saved = [row["provider"] for row in storage.list_provider_keys(settings.user_id)]
    env_keys = [provider for provider, env_var in ENV_KEY_BY_PROVIDER.items() if os.getenv(env_var)]
    return {"providers": list_provider_metadata(saved, env_keys)}


@app.get("/api/verifier")
def verifier_status():
    return entailment_verifier.status()


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


@app.get("/api/search-preferences")
def get_search_preferences():
    return {
        "preference": storage.get_search_preference(settings.user_id),
        "key": _search_key_view(),
    }


@app.put("/api/search-preferences")
def save_search_preferences(payload: SearchPreferenceUpdate):
    return {
        "preference": storage.save_search_preference(settings.user_id, payload.search_mode, payload.max_results),
        "key": _search_key_view(),
    }


@app.post("/api/search-key", status_code=201)
def save_search_key(payload: SearchKeyCreate):
    ciphertext = vault.encrypt(payload.api_key)
    fingerprint = vault.fingerprint(payload.api_key)
    storage.save_search_key(settings.user_id, "tavily", ciphertext, fingerprint)
    return _search_key_view()


@app.delete("/api/search-key")
def delete_search_key():
    deleted = storage.delete_search_key(settings.user_id, "tavily")
    if not deleted:
        raise HTTPException(status_code=404, detail="search key not found")
    return {"deleted": True}


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
    _require_verifier_ready()
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
    _resolve_provider_defaults(payload.provider)
    _require_verifier_ready()
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
            search_mode=payload.search_mode or storage.get_search_preference(settings.user_id)["search_mode"],
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
    initial_run = _get_run_or_404(run_id)

    async def resolve_key(provider: str) -> Optional[str]:
        ciphertext = storage.get_provider_key_ciphertext(settings.user_id, provider)
        if ciphertext:
            storage.mark_provider_key_used(settings.user_id, provider)
            return vault.decrypt(ciphertext)
        env_var = ENV_KEY_BY_PROVIDER.get(provider)
        return os.getenv(env_var) if env_var else None

    async def generate():
        if initial_run["status"] == "completed" and initial_run.get("graph"):
            if initial_run.get("conversation_id") and not storage.assistant_message_exists_for_run(settings.user_id, run_id):
                storage.add_message(
                    settings.user_id,
                    initial_run["conversation_id"],
                    "assistant",
                    initial_run["graph"]["answer"]["final_answer"],
                    run_id=run_id,
                )
            yield _sse({"type": "completed", "progress": 1.0, "message": "Run already completed", "graph": initial_run["graph"]})
            return

        storage.set_run_status(settings.user_id, run_id, "running")
        attachment_document_ids = initial_run.get("attachment_document_ids", [])
        pre_trace, retrieval_document_ids, web_search = await _prepare_retrieval_for_run(initial_run, attachment_document_ids)
        for index, span in enumerate(pre_trace, start=1):
            yield _sse({"type": "progress", "span": span, "progress": min(0.08, index * 0.04), "message": span["input_summary"]})
        run_context = {
            **initial_run,
            "web_search": web_search,
            "web_search_document_ids": [document_id for document_id in retrieval_document_ids if document_id not in attachment_document_ids],
            "search_used": any(call.get("result_count", 0) > 0 for call in web_search.get("calls", [])),
        }
        pipeline = ReliabilityPipeline(
            retrieval_chunks=storage.list_document_chunks(settings.user_id, retrieval_document_ids),
            calibration_report=build_benchmark_report(storage.list_labeled_runs(settings.user_id)),
            entailment_verifier=entailment_verifier,
        )
        trace = list(pre_trace)
        try:
            async for event in pipeline.run(run_context, resolve_key):
                if event["type"] == "progress":
                    event = {**event, "progress": min(0.99, 0.10 + float(event.get("progress", 0.0)) * 0.88)}
                if event["type"] == "completed":
                    trace = pre_trace + event["trace"]
                    event["graph"]["trace"] = trace
                    storage.complete_run(settings.user_id, run_id, event["graph"], trace)
                    if run_context.get("conversation_id") and not storage.assistant_message_exists_for_run(settings.user_id, run_id):
                        storage.add_message(
                            settings.user_id,
                            run_context["conversation_id"],
                            "assistant",
                            event["graph"]["answer"]["final_answer"],
                            run_id=run_id,
                        )
                yield _sse(event)
        except PipelineStageError as exc:
            message = _sanitize_error(exc.message)
            storage.fail_run(settings.user_id, run_id, message, trace)
            yield _sse({**exc.to_event(), "message": message})
        except Exception as exc:
            message = _sanitize_error(str(exc))
            storage.fail_run(settings.user_id, run_id, message, trace)
            yield _sse({"type": "error", "code": "unexpected_error", "stage": "runtime", "retryable": True, "message": message})

    return StreamingResponse(generate(), media_type="text/event-stream")


async def _prepare_retrieval_for_run(run: Dict[str, object], attachment_document_ids: List[str]):
    preference = storage.get_search_preference(settings.user_id)
    route = choose_research_route(
        run["question"],
        attachment_document_ids,
        run.get("search_mode") or preference["search_mode"],
    )
    route_dict = route_to_dict(route)
    web_search = {"route": route_dict, "calls": [], "documents": []}
    pre_trace = [
        _span(
            run["run_id"],
            "research_router",
            "completed",
            "Decided retrieval plan: %s" % route.route.replace("_", " "),
            {"route": route_dict},
        )
    ]
    retrieval_document_ids = list(attachment_document_ids)

    if route.route not in {"web_search", "hybrid"}:
        return pre_trace, retrieval_document_ids, web_search

    api_key = _resolve_search_key()
    if not api_key:
        call = {
            "query": route.query,
            "result_count": 0,
            "selected_urls": [],
            "error": "No web search key is configured in Settings.",
            "response_time": 0,
        }
        web_search["calls"].append(call)
        pre_trace.append(
            _span(
                run["run_id"],
                "web_search",
                "completed",
                "Skipped web search because no web search key is configured.",
                {"calls": web_search["calls"]},
            )
        )
        return pre_trace, retrieval_document_ids, web_search

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: search_tavily(api_key, route.query or run["question"], preference["max_results"], route.recency),
        )
        documents = _index_web_search_results(result["results"])
        retrieval_document_ids.extend([document["document_id"] for document in documents])
        call = {
            "query": result["query"],
            "result_count": len(result["results"]),
            "selected_urls": [item["url"] for item in result["results"][: preference["max_results"]]],
            "error": None,
            "response_time": result["response_time"],
            "request_id": result.get("request_id"),
        }
        web_search["calls"].append(call)
        web_search["documents"] = documents
        pre_trace.append(
            _span(
                run["run_id"],
                "web_search",
                "completed",
                "Searched the web for source evidence.",
                {
                    "query": call["query"],
                    "result_count": call["result_count"],
                    "indexed_sources": len(documents),
                },
            )
        )
    except Exception as exc:
        call = {
            "query": route.query,
            "result_count": 0,
            "selected_urls": [],
            "error": _sanitize_error(str(exc)),
            "response_time": 0,
        }
        web_search["calls"].append(call)
        pre_trace.append(
            _span(
                run["run_id"],
                "web_search",
                "completed",
                "Web search failed cleanly.",
                {"calls": web_search["calls"]},
            )
        )
    return pre_trace, retrieval_document_ids, web_search


def _index_web_search_results(results: List[Dict[str, object]]) -> List[Dict[str, object]]:
    documents = []
    for result in results:
        content = result["content"]
        content_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = storage.find_document_by_signature(settings.user_id, content_sha, result["url"])
        if existing:
            documents.append(existing)
            continue
        chunks = build_chunks(content)
        if not chunks:
            continue
        documents.append(
            storage.save_document(
                settings.user_id,
                result["title"],
                content,
                result["url"],
                "web_search_result",
                chunks,
            )
        )
    return documents


def _get_run_or_404(run_id: str):
    try:
        return storage.get_run(settings.user_id, run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


def _connected_providers():
    saved = [row["provider"] for row in storage.list_provider_keys(settings.user_id)]
    env_keys = [provider for provider, env_var in ENV_KEY_BY_PROVIDER.items() if os.getenv(env_var)]
    return sorted(set(saved + env_keys))


def _search_key_view():
    try:
        saved = storage.get_search_key_view(settings.user_id, "tavily")
        return {**saved, "key_state": "saved", "key_env_var": ENV_KEY_BY_SEARCH_PROVIDER["tavily"]}
    except KeyError:
        if os.getenv(ENV_KEY_BY_SEARCH_PROVIDER["tavily"]):
            return {
                "provider": "tavily",
                "fingerprint": "env",
                "status": "active",
                "created_at": None,
                "last_used_at": None,
                "key_state": "env",
                "key_env_var": ENV_KEY_BY_SEARCH_PROVIDER["tavily"],
            }
        return {
            "provider": "tavily",
            "fingerprint": None,
            "status": "missing",
            "created_at": None,
            "last_used_at": None,
            "key_state": "missing",
            "key_env_var": ENV_KEY_BY_SEARCH_PROVIDER["tavily"],
        }


def _resolve_search_key() -> Optional[str]:
    ciphertext = storage.get_search_key_ciphertext(settings.user_id, "tavily")
    if ciphertext:
        storage.mark_search_key_used(settings.user_id, "tavily")
        return vault.decrypt(ciphertext)
    return os.getenv(ENV_KEY_BY_SEARCH_PROVIDER["tavily"])


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


def _require_verifier_ready() -> None:
    status = entailment_verifier.status()
    if not status.get("ready"):
        raise HTTPException(
            status_code=503,
            detail={
                "code": "verifier_not_ready",
                "stage": "setup",
                "retryable": False,
                "message": status.get("message") or "The entailment verifier is not ready.",
            },
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


def _span(run_id: str, span_type: str, status: str, message: str, output: dict):
    return {
        "span_id": "span_pre_%s" % span_type,
        "run_id": run_id,
        "type": span_type,
        "status": status,
        "input_summary": message,
        "output_summary": json.dumps(output, sort_keys=True),
        "tool": span_type,
        "cost_usd": 0.0,
        "risk_flags": [],
    }


SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"tml-[A-Za-z0-9_-]{12,}"),
    re.compile(r"tvly-[A-Za-z0-9_-]{12,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"AIza[A-Za-z0-9_-]{20,}"),
]


def _sanitize_error(message: str) -> str:
    cleaned = message
    for pattern in SECRET_PATTERNS:
        cleaned = pattern.sub(lambda match: (match.group(1) if match.lastindex else "") + "[redacted]", cleaned)
    return cleaned[:500]
