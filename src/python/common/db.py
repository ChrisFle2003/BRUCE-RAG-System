import uuid
from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.pool
from psycopg2.extras import Json, RealDictCursor

from common.settings import SETTINGS

# --- Connection Pool (Singleton) ---
_pool: psycopg2.pool.ThreadedConnectionPool | None = None


def _get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=5,
            maxconn=50,
            dsn=SETTINGS.database_url,
        )
    return _pool


@contextmanager
def get_conn(autocommit: bool = False):
    """
    Gives a pooled connection and returns it to the pool after context.
    No TCP handshake anymore - connections stay open and are recycled.
    """
    pool = _get_pool()
    conn = pool.getconn()
    conn.autocommit = autocommit
    try:
        yield conn
        if not autocommit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def check_database() -> bool:
    try:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True
    except Exception:
        return False


def list_libraries() -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT bib_id, name, language FROM bibliotheken ORDER BY bib_id ASC"
            )
            return [dict(row) for row in cur.fetchall()]


def fetch_active_routes() -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT config_json
                FROM routing_versions
                WHERE is_active = TRUE
                ORDER BY deployed_at DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if not row:
                return []
            config = row[0] or {}
            routes = config.get("routes", [])
            return [r for r in routes if isinstance(r, dict)]


def is_query_whitelisted(query_text: str) -> bool:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT pattern, match_type FROM whitelist")
            rows = cur.fetchall()

    if not rows:
        return True

    normalized = query_text.strip()
    for row in rows:
        pattern = row["pattern"]
        match_type = row["match_type"]

        if pattern == "__ALLOW_ALL__":
            return True

        if match_type == "exact" and normalized == pattern:
            return True
        if match_type == "prefix" and normalized.startswith(pattern):
            return True
        if match_type == "regex":
            import re

            if re.search(pattern, normalized):
                return True

    return False


def insert_pipeline_job(
    query_text: str,
    trace_id: str,
    state_vec: list[int],
    expected_routes: list[int],
) -> str:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pipeline_jobs (trace_id, query_text, state_vec, expected_routes)
                VALUES (%s, %s, %s, %s)
                RETURNING job_id
                """,
                (trace_id, query_text, state_vec, expected_routes),
            )
            job_id = cur.fetchone()[0]
    return str(job_id)


def get_job_status(job_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT job_id, trace_id, status, created_at, completed_at
                FROM pipeline_jobs
                WHERE job_id = %s
                """,
                (job_id,),
            )
            job = cur.fetchone()
            if not job:
                return None

            cur.execute(
                """
                SELECT answer_text, low_confidence_sections, sources,
                       assembly_quality_score, timing, created_at
                FROM final_answers
                WHERE job_id = %s
                """,
                (job_id,),
            )
            answer = cur.fetchone()

    payload = dict(job)
    if answer:
        payload["result"] = {
            "text": answer["answer_text"],
            "low_confidence_sections": answer["low_confidence_sections"],
            "sources": answer["sources"],
            "quality": answer["assembly_quality_score"],
            "timing": answer["timing"],
            "created_at": answer["created_at"],
        }
    return payload


def insert_calc_result(
    job_id: str,
    route_id: int,
    route_name: str,
    bausteine: list[dict[str, Any]],
    source_seite_ids: list[int],
    duration_ms: int,
    model_version: str,
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO calc_results (
                    job_id, route_id, route_name, bausteine, source_seite_ids,
                    duration_ms, model_version
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (job_id, route_id) DO UPDATE
                SET
                    bausteine = EXCLUDED.bausteine,
                    source_seite_ids = EXCLUDED.source_seite_ids,
                    duration_ms = EXCLUDED.duration_ms,
                    model_version = EXCLUDED.model_version,
                    created_at = NOW()
                """,
                (
                    job_id,
                    route_id,
                    route_name,
                    Json(bausteine),
                    source_seite_ids,
                    duration_ms,
                    model_version,
                ),
            )


def fetch_calc_results(job_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT route_id, route_name, bausteine, source_seite_ids,
                       duration_ms, model_version, created_at
                FROM calc_results
                WHERE job_id = %s
                ORDER BY created_at ASC
                """,
                (job_id,),
            )
            return [dict(row) for row in cur.fetchall()]


def write_final_answer(
    job_id: str,
    answer_text: str,
    low_confidence_sections: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    quality: float,
    timing: dict[str, Any],
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO final_answers (
                    job_id, answer_text, low_confidence_sections, sources,
                    assembly_quality_score, timing
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (job_id) DO UPDATE
                SET
                    answer_text = EXCLUDED.answer_text,
                    low_confidence_sections = EXCLUDED.low_confidence_sections,
                    sources = EXCLUDED.sources,
                    assembly_quality_score = EXCLUDED.assembly_quality_score,
                    timing = EXCLUDED.timing,
                    created_at = NOW()
                """,
                (
                    job_id,
                    answer_text,
                    Json(low_confidence_sections),
                    Json(sources),
                    quality,
                    Json(timing),
                ),
            )
            cur.execute(
                """
                UPDATE pipeline_jobs
                SET status = 'assembled', completed_at = NOW()
                WHERE job_id = %s
                """,
                (job_id,),
            )


def insert_trace(
    trace_id: str,
    stage: str,
    duration_ms: int,
    gpu_device: str | None = None,
    model: str | None = None,
) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO trace_log (trace_id, stage, duration_ms, gpu_device, model)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (trace_id, stage, duration_ms, gpu_device, model),
            )


def new_trace_id() -> str:
    return f"trace_{uuid.uuid4().hex[:16]}"
