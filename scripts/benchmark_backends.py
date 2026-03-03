#!/usr/bin/env python3
"""Benchmark calc backend modes via end-to-end API queries."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.error import URLError


QUERIES = [
    "Wie funktioniert der Bruce Router?",
    "Was ist die Startup Sequence?",
    "Welche Rolle hat pgvector?",
    "Erkläre die Assembler Konfidenzregeln",
    "Welche Performance Targets gibt es?",
    "Was ist die Aufgabe vom Hierarchical Guard?",
    "Wie sieht die Pipeline von Query bis Final Answer aus?",
    "Wozu dient die Tabelle routing_versions?",
    "Wie wird bibliothek_id für Partition Pruning verwendet?",
    "Warum werden Vektoren als int16 gespeichert?",
    "Was bedeutet StateToHierarchyMapper im Core?",
    "Welche Endpunkte gibt es im API Service?",
    "Wie funktioniert POST /api/v1/queries?",
    "Wie pollt man /api/v1/queries/{id} korrekt?",
    "Welche Rolle spielt der Assembler Dienst?",
    "Wie wird low confidence markiert?",
    "Welche Daten liegen in calc_results?",
    "Was speichert final_answers?",
    "Wie wird trace_log genutzt?",
    "Welche Warmup-Phasen gibt es?",
    "Wie wird Backpressure mit MAX_PENDING gelöst?",
    "Wie funktioniert Fail-Fast bei Modellrouting?",
    "Wofuer steht BRUCE als Route im MVP?",
    "Wozu dient DOCS_DE im Routing?",
    "Welche SQL Indizes sind fuer Retrieval wichtig?",
    "Wie laufen Chunking und Import aktuell?",
    "Wie laeuft make db-init und make up?",
    "Wie verhalten sich extractive und hf_api im Vergleich?",
    "Welche Guard-Whitelist Modi sind erlaubt?",
    "Wie sollte man den Produktionsstart absichern?",
]


def _log(msg: str) -> None:
    """Print timestamped log message."""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}", file=sys.stderr)


def _compose_up(project_root: str, env: dict[str, str]) -> None:
    merged = os.environ.copy()
    merged.update(env)
    _log(f"Starting containers with CALC_BACKEND={env.get('CALC_BACKEND')}")
    subprocess.run(
        [
            "docker",
            "compose",
            "up",
            "-d",
            "--no-deps",
            "--force-recreate",
            "api",
            "calc_bruce",
            "calc_docs_de",
        ],
        cwd=project_root,
        env=merged,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    _log("Containers started")


def _submit(api_base: str, query: str) -> dict[str, Any]:
    payload = json.dumps({"query": query, "language": "de"}).encode("utf-8")
    req = urllib.request.Request(
        f"{api_base}/api/v1/queries",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _wait_ready(url: str, timeout_s: float = 25.0) -> None:
    deadline = time.time() + timeout_s
    last_error = "unknown"
    _log(f"Waiting for {url} (timeout: {timeout_s}s)")
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=4) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("status") == "ready":
                _log(f"✓ {url} is ready")
                return
            last_error = f"status={payload.get('status')}"
        except (URLError, TimeoutError, ValueError, OSError) as exc:
            last_error = str(exc)
        time.sleep(0.35)
    raise RuntimeError(f"service not ready: {url} ({last_error})")


def _poll(api_base: str, query_id: str, timeout_s: float = 25.0) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    poll_count = 0
    payload = {}
    
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{api_base}/api/v1/queries/{query_id}", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            poll_count += 1
            
            status = payload.get("status")
            if status == "assembled":
                _log(f"✓ Query {query_id} assembled after {poll_count} polls")
                return payload
            
            if poll_count % 10 == 0:  # Log every 10 polls
                _log(f"  Query {query_id} status: {status} (poll {poll_count})")
                
        except (URLError, TimeoutError, ValueError, OSError) as exc:
            _log(f"  Warning: poll error for {query_id}: {exc}")
            
        time.sleep(0.2)
    
    final_status = payload.get("status", "unknown")
    raise TimeoutError(f"Query {query_id} not assembled within {timeout_s}s (final status: {final_status}, polls: {poll_count})")


def _run_suite(api_base: str) -> dict[str, Any]:
    latencies: list[float] = []
    qualities: list[float] = []

    for idx, query in enumerate(QUERIES, 1):
        _log(f"Query {idx}/{len(QUERIES)}: {query[:50]}...")
        started = time.perf_counter()
        try:
            accepted = _submit(api_base, query)
            query_id = accepted.get("query_id")
            if not query_id:
                _log(f"  ✗ Failed to get query_id: {accepted}")
                continue
                
            result = _poll(api_base, query_id)
            latency_ms = (time.perf_counter() - started) * 1000.0
            latencies.append(latency_ms)

            quality = float((result.get("result") or {}).get("quality") or 0.0)
            qualities.append(quality)
            _log(f"  ✓ Latency: {latency_ms:.0f}ms, Quality: {quality:.3f}")
        except Exception as exc:
            _log(f"  ✗ Error: {exc}")

    if not latencies:
        raise RuntimeError("No successful queries completed")
        
    return {
        "cases": len(latencies),
        "avg_latency_ms": round(statistics.mean(latencies), 2),
        "p95_latency_ms": round(statistics.quantiles(latencies, n=100)[94], 2),
        "avg_quality": round(statistics.mean(qualities), 3),
    }


def _load_env_file(project_root: str) -> None:
    env_path = Path(project_root) / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark extractive vs hf_api backend")
    parser.add_argument("--api-base", default="http://localhost:9998")
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--hf-model", default="")
    args = parser.parse_args()

    _load_env_file(args.project_root)
    results: dict[str, Any] = {}

    _log("=" * 60)
    _log("BRUCE RAG BACKEND BENCHMARK")
    _log("=" * 60)

    _compose_up(
        args.project_root,
        {
            "CALC_BACKEND": "extractive",
            "CALC_BACKEND_DOCS": "extractive",
            "HF_FALLBACK_ENABLED": "0",
            "HF_FALLBACK_ENABLED_DOCS": "0",
        },
    )
    _wait_ready(f"{args.api_base}/api/v1/health", timeout_s=30.0)
    _wait_ready("http://localhost:8003/health", timeout_s=30.0)
    _wait_ready("http://localhost:8012/health", timeout_s=30.0)
    
    _log("Running EXTRACTIVE backend benchmark...")
    results["extractive"] = _run_suite(args.api_base)

    hf_token = os.getenv("HF_API_TOKEN", "").strip()
    hf_model = (args.hf_model or os.getenv("HF_API_MODEL", "google/flan-t5-base")).strip()
    if not hf_token:
        _log("Skipping HF_API benchmark (HF_API_TOKEN not set)")
        results["hf_api"] = {"status": "skipped", "reason": "HF_API_TOKEN not set"}
    else:
        _log(f"Running HF_API benchmark with model: {hf_model}")
        _compose_up(
            args.project_root,
            {
                "CALC_BACKEND": "hf_api",
                "CALC_BACKEND_DOCS": "hf_api",
                "HF_FALLBACK_ENABLED": "0",
                "HF_FALLBACK_ENABLED_DOCS": "0",
                "HF_API_TOKEN": hf_token,
                "HF_API_MODEL": hf_model,
            },
        )
        _wait_ready("http://localhost:8003/health", timeout_s=30.0)
        _wait_ready("http://localhost:8012/health", timeout_s=30.0)
        results["hf_api"] = {"model": hf_model, **_run_suite(args.api_base)}

    # Restore default backend for normal development flow.
    _log("Restoring default backend...")
    _compose_up(
        args.project_root,
        {
            "CALC_BACKEND": "extractive",
            "CALC_BACKEND_DOCS": "extractive",
            "HF_FALLBACK_ENABLED": "0",
            "HF_FALLBACK_ENABLED_DOCS": "0",
        },
    )

    _log("=" * 60)
    _log("RESULTS:")
    _log("=" * 60)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
