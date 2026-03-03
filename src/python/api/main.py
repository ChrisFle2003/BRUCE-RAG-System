from __future__ import annotations

import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

import httpx
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from common.db import (
    check_database,
    fetch_active_routes,
    get_conn,
    get_job_status,
    insert_calc_result,
    insert_pipeline_job,
    insert_trace,
    is_query_whitelisted,
    list_libraries,
    new_trace_id,
)
from embedding.service import get_embedder


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    language: str = "de"
    max_tokens: int = 512


class QueryAccepted(BaseModel):
    query_id: str
    trace_id: str
    status: str


class RetrievalDebugRequest(BaseModel):
    query: str = Field(min_length=1)
    language: str = "de"
    limit: int = 6


app = FastAPI(title="BRUCE RAG API", version="1.1")

INTENT_KEYWORDS: dict[str, set[str]] = {
    "code": {"code", "python", "cpp", "c++", "funktion", "class", "api", "script"},
    "docs_de": {"doku", "dokumentation", "beschreibung", "anleitung", "wie"},
    "docs_en": {"documentation", "guide", "how", "explain", "manual"},
    "math": {"math", "mathe", "gleichung", "beweis", "algebra", "integral"},
    "bruce": {"bruce", "router", "routing", "state", "guard", "assembler", "pipeline"},
}

STOPWORDS = {
    "und",
    "oder",
    "der",
    "die",
    "das",
    "den",
    "dem",
    "ein",
    "eine",
    "einer",
    "eines",
    "ist",
    "sind",
    "wie",
    "was",
    "welche",
    "welcher",
    "welches",
    "gibt",
    "role",
    "what",
    "how",
    "the",
    "for",
    "mit",
    "von",
    "auf",
    "in",
    "zu",
}

_HEALTH_CACHE: dict[str, tuple[float, bool]] = {}
_HEALTH_TTL_SECONDS = 2.0


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z0-9äöüÄÖÜß]+", text.lower())
        if len(token) >= 3 and token not in STOPWORDS
    }


def _route_bib_range(route: dict[str, Any]) -> tuple[int, int]:
    values = route.get("bibliothek_id_range") or [2000, 2999]
    if not isinstance(values, list) or len(values) != 2:
        return (2000, 2999)
    try:
        return (int(values[0]), int(values[1]))
    except Exception:
        return (2000, 2999)


def _route_anchor_tokens(route: dict[str, Any], query_tokens: set[str]) -> set[str]:
    route_name_tokens = _tokenize(str(route.get("name", "")))
    route_tags = route.get("tags") or []
    tag_tokens: set[str] = set()
    for tag in route_tags:
        tag_tokens.update(_tokenize(str(tag)))
    anchors = query_tokens.intersection(route_name_tokens.union(tag_tokens))
    if not anchors and route_name_tokens:
        anchors = route_name_tokens
    return anchors


def _soft_overlap_ratio(query_tokens: set[str], chunk_tokens: set[str]) -> float:
    if not query_tokens:
        return 0.0
    matched = 0
    for token in query_tokens:
        for candidate in chunk_tokens:
            if len(token) >= 4 and len(candidate) >= 4 and (token in candidate or candidate in token):
                matched += 1
                break
    denom = float(min(len(query_tokens), 4))
    return min(matched / denom, 1.0)


def _score_route_intent(route: dict[str, Any], query_tokens: set[str]) -> float:
    route_name = str(route.get("name", "")).lower()
    route_tags = route.get("tags") or []
    route_terms = {term for term in re.findall(r"[a-zA-Z0-9_]+", route_name) if term}
    route_terms.update(str(tag).lower() for tag in route_tags if str(tag).strip())

    score = 0.05
    score += _soft_overlap_ratio(query_tokens, route_terms) * 0.6

    for domain, keywords in INTENT_KEYWORDS.items():
        if domain in route_name:
            overlap = _soft_overlap_ratio(query_tokens, keywords)
            score += overlap * 0.15

    if route_name == "bruce":
        score += 0.05

    return score


def _select_routes(query_text: str, routes: list[dict[str, Any]], max_routes: int = 2) -> list[dict[str, Any]]:
    if len(routes) <= 1:
        return routes

    query_tokens = _tokenize(query_text)
    ranked = sorted(routes, key=lambda route: _score_route_intent(route, query_tokens), reverse=True)
    top = ranked[0]
    selected = [top]

    if len(ranked) > 1:
        top_score = _score_route_intent(top, query_tokens)
        second = ranked[1]
        second_score = _score_route_intent(second, query_tokens)

        # Keep a second route when intent looks mixed or close.
        if second_score >= 0.15 and ((top_score - second_score) <= 0.25 or len(query_tokens) >= 6):
            selected.append(second)

    return selected[:max_routes]


def _domain_balanced_merge(
    route_chunks: dict[int, list[dict[str, Any]]],
    max_total: int = 10,
) -> list[dict[str, Any]]:
    ordered_route_ids = sorted(
        route_chunks.keys(),
        key=lambda route_id: (route_chunks.get(route_id) or [{}])[0].get("similarity", 0.0),
        reverse=True,
    )
    if not ordered_route_ids:
        return []

    pointers = {route_id: 0 for route_id in ordered_route_ids}
    merged: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()

    while len(merged) < max_total:
        progressed = False
        for route_id in ordered_route_ids:
            chunks = route_chunks.get(route_id, [])
            idx = pointers[route_id]
            while idx < len(chunks):
                candidate = chunks[idx]
                key = (int(candidate.get("seite_id", 0)), str(candidate.get("content", ""))[:80])
                idx += 1
                if key in seen:
                    continue
                pointers[route_id] = idx
                seen.add(key)
                merged.append(candidate)
                progressed = True
                break
            pointers[route_id] = idx
            if len(merged) >= max_total:
                break
        if not progressed:
            break

    return merged


def _route_health(endpoint: str, timeout_s: float) -> bool:
    now = time.time()
    cached = _HEALTH_CACHE.get(endpoint)
    if cached and (now - cached[0]) < _HEALTH_TTL_SECONDS:
        return cached[1]

    healthy = False
    def _check() -> bool:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.get(f"{endpoint}/health")
            return response.status_code == 200

    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(_check)
        healthy = bool(future.result(timeout=timeout_s))
    except (FuturesTimeout, Exception):
        healthy = False
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    _HEALTH_CACHE[endpoint] = (now, healthy)
    return healthy


def _record_route_failure(payload: dict[str, Any], route: dict[str, Any], error: str, duration_ms: int) -> None:
    route_id = int(route.get("route_id", 3))
    route_name = str(route.get("name", "BRUCE"))
    trace_id = str(payload.get("trace_id", "trace_unknown"))
    job_id = str(payload.get("job_id", ""))

    if not job_id:
        return

    insert_calc_result(
        job_id=job_id,
        route_id=route_id,
        route_name=route_name,
        bausteine=[
            {
                "type": "fact",
                "content": f"Route {route_name} unavailable: {error}",
                "confidence": 0.45,
                "entity_id": f"route_fail:{route_name.lower()}",
            }
        ],
        source_seite_ids=[],
        duration_ms=max(duration_ms, 1),
        model_version=f"{route_name.lower()}-route-fallback",
    )
    insert_trace(
        trace_id=trace_id,
        stage="inference",
        duration_ms=max(duration_ms, 1),
        gpu_device=None,
        model=f"{route_name.lower()}-route-fallback",
    )


def _cosine_similarity(query_embedding: list[int], chunk_embedding: list[int]) -> float:
    q = np.asarray(query_embedding[:64], dtype=np.float32)
    c = np.asarray((chunk_embedding or [])[:64], dtype=np.float32)
    if c.size != 64 or np.linalg.norm(q) == 0.0 or np.linalg.norm(c) == 0.0:
        return 0.0
    return float(np.dot(q, c) / (np.linalg.norm(q) * np.linalg.norm(c)))


def _retrieve_by_vector(
    query_embedding: list[int],
    bib_start: int,
    bib_end: int,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Uses pgvector <=> operator with HNSW index for fast ANN search.
    Returns top-N chunks by vector similarity.
    """
    # pgvector expects vector as string literal: '[1,2,3]'
    vec_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.seite_id,
                    c.text,
                    c.chunk_index,
                    v.cascade_level,
                    1 - (v.dims <=> %s::int2[]) AS cosine_similarity
                FROM chunks c
                JOIN vektoren v ON v.vektor_id = c.vektor_id
                WHERE c.bib_id BETWEEN %s AND %s
                ORDER BY v.dims <=> %s::int2[] ASC
                LIMIT %s
                """,
                (vec_str, bib_start, bib_end, vec_str, limit),
            )
            rows = cur.fetchall()

    return [
        {
            "seite_id": int(row[0]),
            "content": row[1],
            "chunk_index": int(row[2]),
            "cascade_level": int(row[3] or 0),
            "cosine_similarity": float(row[4] or 0.0),
        }
        for row in rows
    ]


def _retrieve_context_chunks(
    query_text: str,
    query_embedding: list[int],
    state_vec: list[int],
    bib_start: int,
    bib_end: int,
    anchor_tokens: set[str] | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    _ = state_vec
    candidates: dict[tuple[int, int], dict[str, Any]] = {}

    # FIX #1: Single query instead of 6 sequential round-trips.
    # Fetch all candidates from all cascade levels in one DB call
    # and filter/rank in Python.
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.seite_id,
                    c.text,
                    c.chunk_index,
                    v.dims,
                    v.cascade_level,
                    similarity(c.text, %s) AS trigram
                FROM chunks c
                JOIN vektoren v ON v.vektor_id = c.vektor_id
                WHERE c.bib_id BETWEEN %s AND %s
                ORDER BY trigram DESC, c.chunk_index ASC
                LIMIT 500
                """,
                (query_text, bib_start, bib_end),
            )
            rows = cur.fetchall()

    for seite_id, text, chunk_index, dims, cascade_level, trigram in rows:
        key = (int(seite_id), int(chunk_index))
        existing = candidates.get(key)
        if existing is None or float(trigram or 0.0) > existing["trigram"]:
            candidates[key] = {
                "seite_id": int(seite_id),
                "content": text,
                "chunk_index": int(chunk_index),
                "dims": dims or [],
                "cascade_level": int(cascade_level or 0),
                "trigram": float(trigram or 0.0),
            }

    # FIX #2: Merge ANN results with pgvector cosine similarity
    ann_results = _retrieve_by_vector(query_embedding, bib_start, bib_end, limit=50)
    for ann in ann_results:
        key = (ann["seite_id"], ann["chunk_index"])
        existing = candidates.get(key)
        if existing:
            # pgvector cosine is more precise than Python calculation
            existing["cosine_pgvec"] = ann["cosine_similarity"]

    query_tokens = _tokenize(query_text)
    anchor_tokens = anchor_tokens or set()
    scored: list[dict[str, Any]] = []
    for candidate in candidates.values():
        chunk_tokens = _tokenize(candidate["content"])
        overlap = _soft_overlap_ratio(query_tokens, chunk_tokens)
        anchor_overlap = _soft_overlap_ratio(anchor_tokens, chunk_tokens)

        # Use pgvector cosine if available, otherwise Python calculation
        cosine_val = candidate.get("cosine_pgvec")
        if cosine_val is None:
            cosine_val = _cosine_similarity(query_embedding, candidate["dims"])
        cosine_norm = (cosine_val + 1.0) / 2.0

        score = (
            (0.40 * overlap)
            + (0.20 * anchor_overlap)
            + (0.25 * cosine_norm)
            + (0.15 * candidate["trigram"])
        )
        if len(query_tokens) >= 4 and overlap < 0.40:
            score *= 0.55
        scored.append(
            {
                "seite_id": candidate["seite_id"],
                "content": candidate["content"],
                "similarity": round(min(max(score, 0.0), 0.99), 3),
                "full_path": (
                    f"bib:{bib_start}-to-{bib_end}/seite:{candidate['seite_id']}"
                    f"/chunk:{candidate['chunk_index']}/level:{candidate['cascade_level']}"
                ),
            }
        )

    scored.sort(key=lambda item: item["similarity"], reverse=True)
    chunks = [
        {
            "seite_id": item["seite_id"],
            "content": item["content"],
            "similarity": item["similarity"],
            "full_path": item["full_path"],
        }
        for item in scored[:limit]
    ]

    if not chunks:
        chunks.append(
            {
                "seite_id": 0,
                "content": query_text,
                "similarity": 0.78,
                "full_path": "synthetic/fallback",
            }
        )

    return chunks


def _dispatch_route(route: dict[str, Any], payload: dict[str, Any]) -> None:
    endpoint = route.get("endpoint")
    if not endpoint:
        return
    timeout_ms = int(route.get("timeout_ms", 5000))
    max_retries = int(route.get("max_retries", 2))
    retry_backoff_ms = int(route.get("retry_backoff_ms", 120))
    fail_fast_ms = int(route.get("fail_fast_ms", timeout_ms * max(1, max_retries + 1)))
    started = time.perf_counter()

    if not _route_health(endpoint, timeout_s=min(2.0, timeout_ms / 1000.0)):
        duration_ms = int((time.perf_counter() - started) * 1000)
        _record_route_failure(payload, route, "health-check failed", duration_ms)
        return

    with ThreadPoolExecutor(max_workers=1) as executor:
        for attempt in range(max_retries + 1):
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            if elapsed_ms >= fail_fast_ms:
                _record_route_failure(payload, route, "fail-fast deadline exceeded", elapsed_ms)
                return

            try:
                per_attempt_timeout = min(0.9, timeout_ms / 1000.0)

                def _post() -> int:
                    timeout = httpx.Timeout(
                        connect=min(0.35, per_attempt_timeout),
                        read=min(0.45, per_attempt_timeout),
                        write=min(0.35, per_attempt_timeout),
                        pool=min(0.35, per_attempt_timeout),
                    )
                    with httpx.Client(timeout=timeout) as client:
                        response = client.post(f"{endpoint}/calc", json=payload)
                    return response.status_code

                future = executor.submit(_post)
                status_code = int(future.result(timeout=per_attempt_timeout))
                response = type("Resp", (), {"status_code": status_code})()
                if response.status_code == 200:
                    return
                last_error = f"status {response.status_code}"
            except FuturesTimeout:
                last_error = "attempt timeout"
                future.cancel()
            except Exception as exc:
                last_error = str(exc)

            if attempt < max_retries:
                sleep_s = (retry_backoff_ms * (2**attempt)) / 1000.0
                time.sleep(min(sleep_s, 1.5))
                continue

            duration_ms = int((time.perf_counter() - started) * 1000)
            _record_route_failure(payload, route, last_error, duration_ms)
            return


@app.post("/api/v1/queries", response_model=QueryAccepted)
def submit_query(request: QueryRequest) -> QueryAccepted:
    if not is_query_whitelisted(request.query):
        raise HTTPException(status_code=403, detail="query is not whitelisted")

    trace_id = new_trace_id()

    embedding_started = time.perf_counter()
    embedder = get_embedder()
    embedding = embedder.embed_int16(request.query)
    state_vec = embedder.state_vec(embedding)
    insert_trace(trace_id, "embedding", int((time.perf_counter() - embedding_started) * 1000))

    routes = fetch_active_routes()
    if not routes:
        routes = [
            {
                "route_id": 3,
                "name": "BRUCE",
                "endpoint": "http://localhost:8003",
                "priority": 1,
                "bibliothek_id_range": [2000, 2999],
            }
        ]
    routes = _select_routes(request.query, routes, max_routes=2)

    expected_routes = [int(route.get("route_id", 3)) for route in routes]
    job_id = insert_pipeline_job(
        query_text=request.query,
        trace_id=trace_id,
        state_vec=state_vec,
        expected_routes=expected_routes,
    )

    cascade_started = time.perf_counter()
    route_chunks: dict[int, list[dict[str, Any]]] = {}
    query_tokens = _tokenize(request.query)
    for route in routes:
        bib_start, bib_end = _route_bib_range(route)
        anchor_tokens = _route_anchor_tokens(route, query_tokens)
        route_chunks[int(route.get("route_id", 3))] = _retrieve_context_chunks(
            query_text=request.query,
            query_embedding=embedding,
            state_vec=state_vec,
            bib_start=bib_start,
            bib_end=bib_end,
            anchor_tokens=anchor_tokens,
        )
    balanced_chunks = _domain_balanced_merge(route_chunks, max_total=10)
    insert_trace(trace_id, "cascade", int((time.perf_counter() - cascade_started) * 1000))

    route_started = time.perf_counter()
    for route in routes:
        route_id = int(route.get("route_id", 3))
        payload = {
            "request_id": str(uuid.uuid4()),
            "trace_id": trace_id,
            "job_id": job_id,
            "route_id": route_id,
            "route_name": route.get("name", "BRUCE"),
            "state_vec": state_vec,
            "context": {
                "query_text": request.query,
                "chunks": route_chunks.get(route_id, []),
                "balanced_chunks": balanced_chunks,
                "total_chunks": len(route_chunks.get(route_id, [])),
            },
            "task": {
                "type": "extract_facts",
                "language": request.language,
                "max_tokens": request.max_tokens,
            },
        }
        threading.Thread(
            target=_dispatch_route,
            args=(route, payload),
            daemon=True,
        ).start()

    insert_trace(trace_id, "routing", int((time.perf_counter() - route_started) * 1000))

    return QueryAccepted(query_id=job_id, trace_id=trace_id, status="queued")


@app.get("/api/v1/queries/{query_id}")
def query_status(query_id: str) -> dict[str, Any]:
    status = get_job_status(query_id)
    if not status:
        raise HTTPException(status_code=404, detail="query not found")
    status["query_id"] = status.pop("job_id")
    return status


@app.get("/api/v1/health")
def health() -> dict[str, Any]:
    db_ok = check_database()
    return {"status": "ready" if db_ok else "degraded", "database": db_ok}


@app.get("/api/v1/libraries")
def libraries() -> list[dict[str, Any]]:
    return list_libraries()


@app.post("/api/v1/debug/retrieval")
def debug_retrieval(request: RetrievalDebugRequest) -> dict[str, Any]:
    embedder = get_embedder()
    embedding = embedder.embed_int16(request.query)
    state_vec = embedder.state_vec(embedding)

    routes = fetch_active_routes()
    if not routes:
        routes = [
            {
                "route_id": 3,
                "name": "BRUCE",
                "endpoint": "http://localhost:8003",
                "priority": 1,
                "bibliothek_id_range": [2000, 2999],
            }
        ]
    routes = _select_routes(request.query, routes, max_routes=2)

    selected: list[dict[str, Any]] = []
    route_chunks: dict[int, list[dict[str, Any]]] = {}
    query_tokens = _tokenize(request.query)
    for route in routes:
        bib_start, bib_end = _route_bib_range(route)
        anchor_tokens = _route_anchor_tokens(route, query_tokens)
        chunks = _retrieve_context_chunks(
            query_text=request.query,
            query_embedding=embedding,
            state_vec=state_vec,
            bib_start=bib_start,
            bib_end=bib_end,
            anchor_tokens=anchor_tokens,
            limit=request.limit,
        )
        route_id = int(route.get("route_id", 3))
        route_chunks[route_id] = chunks
        selected.append(
            {
                "route_id": route_id,
                "route_name": route.get("name", "BRUCE"),
                "range": [bib_start, bib_end],
                "chunks": chunks,
            }
        )

    return {
        "query": request.query,
        "routes": selected,
        "merged_chunks": _domain_balanced_merge(route_chunks, max_total=request.limit),
    }
