from __future__ import annotations

import select
import threading
import time
import uuid
from collections import deque
from typing import Any

import psycopg2
from fastapi import FastAPI

from common.assembly import assemble
from common.db import (
    fetch_calc_results,
    insert_trace,
    write_final_answer,
)
from common.settings import SETTINGS


app = FastAPI(title="BRUCE Assembler Service", version="1.1")

_listener_thread: threading.Thread | None = None
_listener_stop = threading.Event()
_listener_state = {
    "listening": False,
    "last_payload": None,
    "last_error": None,
    "assembled_jobs": 0,
}
_recent_tokens: deque[str] = deque(maxlen=64)


def _assemble_job(job_id: str) -> None:
    started = time.perf_counter()
    calc_rows = fetch_calc_results(job_id)
    if not calc_rows:
        return

    assembled = assemble(calc_rows)
    duration_ms = int((time.perf_counter() - started) * 1000)

    write_final_answer(
        job_id=job_id,
        answer_text=assembled["answer_text"],
        low_confidence_sections=assembled["low_confidence_sections"],
        sources=assembled["sources"],
        quality=float(assembled["assembly_quality_score"]),
        timing={"assembly_ms": duration_ms},
    )

    trace_id = f"assembly_{job_id[:8]}"
    insert_trace(
        trace_id=trace_id,
        stage="assembly",
        duration_ms=duration_ms,
        gpu_device="cuda:1",
        model="qwen2.5-0.5b-assembler-stub",
    )
    _listener_state["assembled_jobs"] = int(_listener_state["assembled_jobs"]) + 1


def _listener_loop() -> None:
    conn = None
    try:
        conn = psycopg2.connect(SETTINGS.database_url)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("LISTEN assembly_ready;")
        _listener_state["listening"] = True

        while not _listener_stop.is_set():
            ready, _, _ = select.select([conn], [], [], 1.0)
            if not ready:
                continue

            conn.poll()
            while conn.notifies:
                notify = conn.notifies.pop(0)
                payload = str(notify.payload)
                _listener_state["last_payload"] = payload
                _recent_tokens.append(payload)

                try:
                    uuid.UUID(payload)
                except ValueError:
                    continue

                _assemble_job(payload)
    except Exception as exc:
        _listener_state["last_error"] = str(exc)
        _listener_state["listening"] = False
    finally:
        _listener_state["listening"] = False
        if conn is not None:
            conn.close()


@app.on_event("startup")
def startup() -> None:
    global _listener_thread
    _listener_stop.clear()
    _listener_thread = threading.Thread(target=_listener_loop, daemon=True)
    _listener_thread.start()


@app.on_event("shutdown")
def shutdown() -> None:
    _listener_stop.set()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "listening" if _listener_state["listening"] else "degraded",
        "listener": _listener_state,
    }


@app.get("/health/listener-check")
def listener_check(token: str) -> dict[str, Any]:
    return {
        "status": "ok" if token in _recent_tokens else "waiting",
        "token": token,
        "listening": bool(_listener_state["listening"]),
    }
