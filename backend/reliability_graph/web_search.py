import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

TAVILY_SEARCH_URL = "https://api.tavily.com/search"
SEARCH_MODES = {"auto", "always", "off"}

CURRENT_TERMS = {
    "today",
    "latest",
    "current",
    "recent",
    "now",
    "news",
    "this week",
    "this month",
    "2026",
}
FACTUAL_TERMS = {
    "who is",
    "what is",
    "when did",
    "where is",
    "which",
    "price",
    "prices",
    "stock",
    "weather",
    "law",
    "legal",
    "policy",
    "regulation",
    "api",
    "version",
    "benchmark",
    "paper",
    "study",
    "medical",
    "medicine",
    "tax",
    "best",
    "recommend",
    "near me",
}
NO_SEARCH_TERMS = {
    "don't search",
    "do not search",
    "without web",
    "no web",
    "don't browse",
    "do not browse",
}
EXPLICIT_SEARCH_TERMS = {
    "search",
    "look up",
    "browse",
    "find sources",
    "cite sources",
    "use the web",
}
ATTACHMENT_TERMS = {
    "attachment",
    "attached",
    "file",
    "document",
    "source i uploaded",
    "this url",
    "this source",
}
CREATIVE_NO_SEARCH_TERMS = {
    "brainstorm",
    "write a poem",
    "write a story",
    "draft an email",
    "rewrite",
    "summarize this conversation",
    "explain like",
}


@dataclass
class ResearchRoute:
    route: str
    search_mode: str
    reason: str
    query: Optional[str] = None
    recency: Optional[str] = None


def choose_research_route(question: str, attachment_document_ids: List[str], search_mode: str = "auto") -> ResearchRoute:
    mode = search_mode if search_mode in SEARCH_MODES else "auto"
    lowered = question.lower()
    has_attachments = bool(attachment_document_ids)

    if any(term in lowered for term in NO_SEARCH_TERMS) or mode == "off":
        route = "attachments_only" if has_attachments else "no_search"
        return ResearchRoute(route, mode, "Search disabled for this turn.")

    needs_search = mode == "always" or _needs_web_search(lowered)
    refers_to_attachment = has_attachments and any(term in lowered for term in ATTACHMENT_TERMS)

    if needs_search and has_attachments:
        return ResearchRoute("hybrid", mode, "Question needs web evidence in addition to attached sources.", _search_query(question), _recency(lowered))
    if needs_search:
        return ResearchRoute("web_search", mode, "Question may benefit from current or source-grounded web evidence.", _search_query(question), _recency(lowered))
    if refers_to_attachment or has_attachments:
        return ResearchRoute("attachments_only", mode, "Question can be grounded in the attached sources.")
    return ResearchRoute("no_search", mode, "Question can be answered without retrieval.")


def search_tavily(api_key: str, query: str, max_results: int = 6, recency: Optional[str] = None, timeout: int = 20) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "query": query[:500],
        "max_results": max(1, min(max_results, 10)),
        "include_answer": False,
        "include_raw_content": "text",
        "search_depth": "basic",
    }
    if recency:
        payload["time_range"] = recency
    request = urllib.request.Request(
        TAVILY_SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer %s" % api_key,
            "Content-Type": "application/json",
            "User-Agent": "ReliabilityGraph/1.0 web retrieval",
        },
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(3_000_000)
            data = json.loads(raw.decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        raise ValueError("Web search returned HTTP %s" % exc.code) from exc
    except urllib.error.URLError as exc:
        raise ValueError("Web search is unavailable") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("Web search returned invalid JSON") from exc

    return {
        "query": data.get("query") or query,
        "results": normalize_tavily_results(data.get("results") or []),
        "response_time": round(float(data.get("response_time") or (time.monotonic() - started)), 3),
        "request_id": data.get("request_id"),
    }


def normalize_tavily_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    seen = set()
    for item in results:
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        title = re.sub(r"\s+", " ", str(item.get("title") or url)).strip()[:300]
        snippet = re.sub(r"\s+", " ", str(item.get("content") or item.get("snippet") or "")).strip()
        raw_content = re.sub(r"\s+", " ", str(item.get("raw_content") or "")).strip()
        content = (raw_content or snippet)[:120_000]
        if len(content) < 20:
            continue
        seen.add(url)
        normalized.append(
            {
                "title": title or url,
                "url": url,
                "content": content,
                "snippet": snippet[:1000],
                "score": float(item.get("score") or 0.0),
                "published_date": item.get("published_date") or item.get("date"),
            }
        )
    return normalized


def route_to_dict(route: ResearchRoute) -> Dict[str, Any]:
    return asdict(route)


def _needs_web_search(lowered: str) -> bool:
    if any(term in lowered for term in EXPLICIT_SEARCH_TERMS):
        return True
    if any(term in lowered for term in CURRENT_TERMS):
        return True
    if any(term in lowered for term in FACTUAL_TERMS) and not any(term in lowered for term in CREATIVE_NO_SEARCH_TERMS):
        return True
    return False


def _search_query(question: str) -> str:
    query = re.sub(r"\s+", " ", question.strip())
    query = re.sub(r"^(please\s+)?(search|look up|browse|find)\s+", "", query, flags=re.IGNORECASE)
    return query[:500]


def _recency(lowered: str) -> Optional[str]:
    if any(term in lowered for term in ["today", "now"]):
        return "day"
    if "this week" in lowered or "latest" in lowered or "news" in lowered:
        return "week"
    if "recent" in lowered or "this month" in lowered:
        return "month"
    return None
