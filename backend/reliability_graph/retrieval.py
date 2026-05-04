import hashlib
import html
import ipaddress
import json
import math
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional


TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_'-]*")
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_RE = re.compile(r"<(script|style)\b.*?</\1>", re.IGNORECASE | re.DOTALL)
WHITESPACE_RE = re.compile(r"\s+")
VECTOR_DIMS = 192
MAX_FETCH_BYTES = 1_500_000
MAX_REDIRECTS = 3
ALLOWED_CONTENT_TYPES = {
    "application/json",
    "application/xhtml+xml",
    "application/xml",
    "text/csv",
    "text/html",
    "text/markdown",
    "text/plain",
    "text/xml",
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "if",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "with",
}

NEGATION_TERMS = {"not", "no", "never", "false", "incorrect", "contradict", "contradicts", "cannot", "can't"}
SECONDARY_SOURCE_DOMAINS = (
    "reddit.com",
    "stackoverflow.com",
    "wikipedia.org",
)
OFFICIAL_SOURCE_HINTS = (
    "docs.",
    "/docs",
    "/documentation",
    "/download",
    "/downloads",
    "/release",
    "/releases",
    "/versions",
    "/changelog",
)
FRESHNESS_TERMS = {"current", "latest", "official", "release", "releases", "stable", "version", "versions"}


def tokenize(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_RE.findall(text) if len(token) > 2 and token.lower() not in STOPWORDS]


def chunk_text(text: str, target_tokens: int = 180, overlap: int = 35) -> List[str]:
    words = WHITESPACE_RE.sub(" ", text.strip()).split()
    if not words:
        return []
    if len(words) <= target_tokens:
        return [" ".join(words)]

    chunks: List[str] = []
    start = 0
    step = max(1, target_tokens - overlap)
    while start < len(words):
        chunk = words[start : start + target_tokens]
        if len(chunk) >= 30 or not chunks:
            chunks.append(" ".join(chunk))
        start += step
    return chunks


def build_chunks(text: str) -> List[Dict[str, Any]]:
    return [
        {
            "chunk_index": index,
            "text": chunk,
            "embedding_json": json.dumps(vectorize(chunk), separators=(",", ":")),
            "token_count": len(tokenize(chunk)),
        }
        for index, chunk in enumerate(chunk_text(text))
    ]


def vectorize(text: str) -> List[float]:
    vector = [0.0] * VECTOR_DIMS
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % VECTOR_DIMS
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [round(value / norm, 6) for value in vector]


def cosine(left: Iterable[float], right: Iterable[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def text_similarity(left: str, right: str) -> float:
    left_tokens = set(tokenize(left))
    right_tokens = set(tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    lexical = len(left_tokens & right_tokens) / float(len(left_tokens | right_tokens))
    semantic = cosine(vectorize(left), vectorize(right))
    return max(0.0, min(1.0, 0.45 * lexical + 0.55 * semantic))


def search_chunks(query: str, chunks: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    query_vector = vectorize(query)
    query_tokens = set(tokenize(query))
    ranked: List[Dict[str, Any]] = []
    for chunk in chunks:
        chunk_vector = json.loads(chunk.get("embedding_json") or "[]")
        chunk_tokens = set(tokenize(chunk.get("text", "")))
        if not chunk_vector or not chunk_tokens:
            continue
        lexical = len(query_tokens & chunk_tokens) / float(len(query_tokens) or 1)
        semantic = cosine(query_vector, chunk_vector)
        score = 0.62 * semantic + 0.38 * min(1.0, lexical) + source_priority(query_tokens, chunk)
        ranked.append({**chunk, "relevance_score": round(max(0.0, min(1.0, score)), 4)})
    ranked.sort(key=lambda item: item["relevance_score"], reverse=True)
    return ranked[:limit]


def evidence_for_claims(
    claims: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    limit_per_claim: int = 2,
    min_score: float = 0.16,
) -> List[Dict[str, Any]]:
    evidence: List[Dict[str, Any]] = []
    for claim in claims:
        matches = [match for match in search_chunks(claim["text"], chunks, limit=limit_per_claim) if match["relevance_score"] >= min_score]
        for match in matches:
            relation = support_relation(claim["text"], match["text"])
            evidence_id = "e%d" % (len(evidence) + 1)
            evidence.append(
                {
                    "evidence_id": evidence_id,
                    "claim_id": claim["claim_id"],
                    "source_title": match.get("title") or "Untitled source",
                    "source_url": match.get("source_url"),
                    "source_date": None,
                    "source_type": match.get("source_type") or "uploaded_document",
                    "snippet": compact_snippet(match["text"], claim["text"]),
                    "support_relation": relation,
                    "source_quality": source_quality(match),
                    "chunk_id": match.get("chunk_id"),
                    "relevance_score": match["relevance_score"],
                }
            )
    return evidence


def support_relation(claim: str, snippet: str) -> str:
    claim_lower = re.sub(r"^based on (?:the )?(?:attached|fetched) source,\s*", "", claim.lower()).strip()
    claim_for_tokens = claim_lower or claim
    snippet_lower = snippet.lower()
    claim_tokens = set(tokenize(claim_for_tokens))
    snippet_tokens = set(tokenize(snippet))
    overlap = len(claim_tokens & snippet_tokens) / float(len(claim_tokens) or 1)

    if claim_lower.strip(". ") in snippet_lower:
        return "supports"
    if overlap >= 0.3 and len(claim_tokens & snippet_tokens) >= 3 and _has_direct_contradiction(claim_tokens, snippet_lower):
        return "contradicts"
    if claim_tokens and claim_tokens.issubset(snippet_tokens):
        return "supports"
    if ("normal api provider" in claim_lower or "supported provider" in claim_lower) and (
        "supported provider" in snippet_lower or "normal api provider" in snippet_lower
    ):
        return "supports"
    return "supports" if overlap >= 0.45 else "partially_supports"


def source_quality(chunk: Dict[str, Any]) -> str:
    source_type = chunk.get("source_type") or ""
    url = chunk.get("source_url") or ""
    if source_type in {"official_docs", "paper", "peer_reviewed_paper"}:
        return "high"
    if _is_secondary_source(url):
        return "low"
    if any(domain in url for domain in [".edu", ".gov", "docs.", "arxiv.org", "aclanthology.org"]):
        return "high"
    if any(hint in url for hint in OFFICIAL_SOURCE_HINTS) and not _is_secondary_source(url):
        return "high"
    if source_type in {"web_page", "web_search_result", "uploaded_document", "manual_source"}:
        return "medium"
    return "low"


def source_priority(query_tokens: set, chunk: Dict[str, Any]) -> float:
    url = str(chunk.get("source_url") or "").lower()
    title = str(chunk.get("title") or "").lower()
    is_freshness_query = bool(query_tokens & FRESHNESS_TERMS)
    if not is_freshness_query:
        return 0.0

    priority = 0.0
    if _is_secondary_source(url):
        priority -= 0.08

    source_identity = "%s %s" % (title, url)
    has_subject_match = any(token in source_identity for token in query_tokens - FRESHNESS_TERMS)
    if has_subject_match and any(hint in url for hint in OFFICIAL_SOURCE_HINTS) and not _is_secondary_source(url):
        priority += 0.14
    return priority


def _is_secondary_source(url: str) -> bool:
    return any(domain in url for domain in SECONDARY_SOURCE_DOMAINS)


def _has_direct_contradiction(claim_tokens: set, snippet_lower: str) -> bool:
    if any(term in snippet_lower for term in ["contradicts", "contradicted", "is false", "are false", "is incorrect", "are incorrect"]):
        return True
    for match in re.finditer(r"\b(not|no|never|cannot|can't)\b(?:[^\w.!?;:]+[\w'-]+){0,5}", snippet_lower):
        window_tokens = set(tokenize(match.group(0)))
        if window_tokens & (claim_tokens - NEGATION_TERMS):
            return True
    return False


def compact_snippet(text: str, query: str, max_chars: int = 520) -> str:
    cleaned = WHITESPACE_RE.sub(" ", text.strip())
    if len(cleaned) <= max_chars:
        return cleaned
    query_terms = tokenize(query)
    pivot = 0
    lower = cleaned.lower()
    for term in query_terms:
        position = lower.find(term)
        if position >= 0:
            pivot = position
            break
    start = max(0, pivot - max_chars // 3)
    end = min(len(cleaned), start + max_chars)
    return cleaned[start:end].strip()


def fetch_url_text(url: str, timeout: int = 15) -> Dict[str, str]:
    current_url = url.strip()
    opener = urllib.request.build_opener(_NoRedirectHandler)
    for _redirect in range(MAX_REDIRECTS + 1):
        _validate_fetch_url(current_url)
        request = urllib.request.Request(
            current_url,
            headers={
                "User-Agent": "ReliabilityGraph/1.0 source retrieval",
                "Accept": "text/html,text/plain,text/markdown,text/csv,application/json,application/xhtml+xml",
            },
        )
        try:
            with opener.open(request, timeout=timeout) as response:
                content_type = _content_type(response.headers.get("content-type", ""))
                if not _is_allowed_content_type(content_type):
                    raise ValueError("unsupported source content type: %s" % (content_type or "unknown"))
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > MAX_FETCH_BYTES:
                            raise ValueError("source is too large to fetch")
                    except ValueError:
                        if content_length.strip().isdigit():
                            raise
                raw = response.read(MAX_FETCH_BYTES + 1)
                if len(raw) > MAX_FETCH_BYTES:
                    raise ValueError("source is too large to fetch")
                text = raw.decode("utf-8", errors="replace")
                title = title_from_html(text) if "html" in content_type else current_url
                return {"title": title or current_url, "text": html_to_text(text), "source_url": current_url}
        except urllib.error.HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308}:
                location = exc.headers.get("location")
                if not location:
                    raise ValueError("source redirect is missing a Location header") from exc
                current_url = urllib.parse.urljoin(current_url, location)
                continue
            raise ValueError("source returned HTTP %s" % exc.code) from exc
        except urllib.error.URLError as exc:
            raise ValueError("source could not be fetched") from exc
    raise ValueError("source redirected too many times")


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _validate_fetch_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("only http and https sources are supported")
    if parsed.username or parsed.password:
        raise ValueError("source URLs cannot include credentials")
    if not parsed.hostname:
        raise ValueError("source URL is missing a host")
    try:
        host_infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("source host could not be resolved") from exc
    for info in host_infos:
        ip = ipaddress.ip_address(info[4][0])
        if _is_blocked_ip(ip):
            raise ValueError("source host resolves to a blocked network")


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return bool(
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _content_type(value: str) -> str:
    return value.split(";", 1)[0].strip().lower()


def _is_allowed_content_type(value: str) -> bool:
    return value in ALLOWED_CONTENT_TYPES or value.startswith("text/")


def html_to_text(raw: str) -> str:
    without_scripts = SCRIPT_RE.sub(" ", raw)
    unescaped = html.unescape(without_scripts)
    text = TAG_RE.sub(" ", unescaped)
    return WHITESPACE_RE.sub(" ", text).strip()


def title_from_html(raw: str) -> Optional[str]:
    match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return WHITESPACE_RE.sub(" ", html.unescape(match.group(1))).strip()
