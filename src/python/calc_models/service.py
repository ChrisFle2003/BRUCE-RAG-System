from __future__ import annotations

import os
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from calc_models.backends import Chunk, ExtractiveBackend, HFInferenceAPIBackend, get_backend
from common.db import insert_calc_result, insert_trace


class ContextChunk(BaseModel):
    seite_id: int = 0
    content: str = ""
    similarity: float = 0.0
    full_path: str | None = None


class Task(BaseModel):
    type: str = "extract_facts"
    language: str = "de"
    max_tokens: int = 512


class CalcRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str
    job_id: str
    route_id: int = 3
    route_name: str = "BRUCE"
    state_vec: list[int] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    task: Task = Field(default_factory=Task)


class CalcResponse(BaseModel):
    request_id: str
    status: str
    route_name: str
    duration_ms: int


app = FastAPI(title="BRUCE Calc Model Service", version="1.1")
BACKEND = get_backend()
HF_FALLBACK_ENABLED = os.getenv("HF_FALLBACK_ENABLED", "1").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
HF_FALLBACK_MIN_CONF = float(os.getenv("HF_FALLBACK_MIN_CONF", "0.68"))
HF_FALLBACK: HFInferenceAPIBackend | None = None
if HF_FALLBACK_ENABLED:
    candidate = HFInferenceAPIBackend()
    if getattr(candidate, "api_token", "").strip():
        HF_FALLBACK = candidate


def _avg_confidence(bausteine: list[dict[str, Any]]) -> float:
    values: list[float] = []
    for baustein in bausteine:
        try:
            values.append(float(baustein.get("confidence", 0.0)))
        except Exception:
            continue
    if not values:
        return 0.0
    return sum(values) / len(values)


def _needs_hf_fallback(bausteine: list[dict[str, Any]], chunks: list[Chunk]) -> bool:
    if not chunks:
        return False
    if not bausteine:
        return True

    fact_scores: list[float] = []
    for baustein in bausteine:
        if str(baustein.get("type", "")).lower() != "fact":
            continue
        try:
            fact_scores.append(float(baustein.get("confidence", 0.0)))
        except Exception:
            continue
    if not fact_scores:
        return True

    avg_fact = sum(fact_scores) / len(fact_scores)
    top_fact = max(fact_scores)
    avg_all = _avg_confidence(bausteine)
    return (
        avg_fact < HF_FALLBACK_MIN_CONF
        or top_fact < (HF_FALLBACK_MIN_CONF + 0.06)
        or avg_all < (HF_FALLBACK_MIN_CONF - 0.04)
    )


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ready",
        "model": BACKEND.name,
        "hf_fallback": HF_FALLBACK.name if HF_FALLBACK else None,
    }


@app.post("/warmup")
def warmup() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/calc", response_model=CalcResponse)
def calc(request: CalcRequest) -> CalcResponse:
    started = time.perf_counter()
    query_text = str(request.context.get("query_text", "")).strip()

    chunks_payload = request.context.get("balanced_chunks") or request.context.get("chunks", [])
    chunks: list[Chunk] = []
    for row in chunks_payload:
        try:
            parsed = ContextChunk(**row)
            chunks.append(
                Chunk(
                    seite_id=parsed.seite_id,
                    content=parsed.content,
                    similarity=float(parsed.similarity),
                )
            )
        except Exception:
            continue

    if not request.job_id:
        raise HTTPException(status_code=400, detail="job_id is required")

    bausteine = BACKEND.infer(query_text=query_text, chunks=chunks, max_items=4, route_name=request.route_name)
    model_version = BACKEND.name
    if HF_FALLBACK and isinstance(BACKEND, ExtractiveBackend):
        if _needs_hf_fallback(bausteine, chunks):
            hf_bausteine = HF_FALLBACK.infer(query_text=query_text, chunks=chunks, max_items=2, route_name=request.route_name)
            if hf_bausteine:
                # Keep a small extractive tail for traceability to concrete snippets.
                bausteine = hf_bausteine[:2] + bausteine[:2]
                model_version = f"{BACKEND.name}+{HF_FALLBACK.name}"

    source_ids = [chunk.seite_id for chunk in chunks[:4] if chunk.seite_id > 0]

    duration_ms = int((time.perf_counter() - started) * 1000)
    insert_calc_result(
        job_id=request.job_id,
        route_id=request.route_id,
        route_name=request.route_name,
        bausteine=bausteine,
        source_seite_ids=source_ids,
        duration_ms=duration_ms,
        model_version=model_version,
    )
    insert_trace(
        trace_id=request.trace_id,
        stage="inference",
        duration_ms=duration_ms,
        gpu_device="cuda:1",
        model=model_version,
    )

    return CalcResponse(
        request_id=request.request_id,
        status="ok",
        route_name=request.route_name,
        duration_ms=duration_ms,
    )
