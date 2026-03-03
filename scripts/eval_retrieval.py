#!/usr/bin/env python3
"""Evaluate retrieval quality via API debug endpoint using MRR/Recall@K."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from typing import Any
import urllib.request


@dataclass
class EvalCase:
    query: str
    expected_terms: list[str]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _relevant(chunk_text: str, expected_terms: list[str]) -> bool:
    normalized = _normalize(chunk_text)
    return any(term.lower() in normalized for term in expected_terms)


def _reciprocal_rank(relevance: list[bool]) -> float:
    for idx, rel in enumerate(relevance, start=1):
        if rel:
            return 1.0 / float(idx)
    return 0.0


def _recall_at_k(relevance: list[bool], k: int) -> float:
    return 1.0 if any(relevance[:k]) else 0.0


def run_eval(api_base: str, cases: list[EvalCase], limit: int) -> dict[str, Any]:
    mrr_total = 0.0
    recall_at_1 = 0.0
    recall_at_3 = 0.0
    recall_at_5 = 0.0
    details: list[dict[str, Any]] = []

    for case in cases:
        req = urllib.request.Request(
            f"{api_base}/api/v1/debug/retrieval",
            data=json.dumps({"query": case.query, "limit": limit}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        routes = payload.get("routes", [])
        chunks: list[dict[str, Any]] = payload.get("merged_chunks") or []
        if not chunks:
            for route in routes:
                chunks.extend(route.get("chunks", []))
            chunks.sort(key=lambda item: float(item.get("similarity", 0.0)), reverse=True)

        relevance = [_relevant(str(chunk.get("content", "")), case.expected_terms) for chunk in chunks]
        rr = _reciprocal_rank(relevance)
        r1 = _recall_at_k(relevance, 1)
        r3 = _recall_at_k(relevance, 3)
        r5 = _recall_at_k(relevance, 5)

        mrr_total += rr
        recall_at_1 += r1
        recall_at_3 += r3
        recall_at_5 += r5

        top_score = chunks[0].get("similarity") if chunks else None
        details.append(
            {
                "query": case.query,
                "routes": len(routes),
                "rr": round(rr, 3),
                "recall@1": int(r1),
                "recall@3": int(r3),
                "recall@5": int(r5),
                "top_similarity": top_score,
            }
        )

    total = float(len(cases))
    return {
        "cases": len(cases),
        "mrr": round(mrr_total / total, 3),
        "recall@1": round(recall_at_1 / total, 3),
        "recall@3": round(recall_at_3 / total, 3),
        "recall@5": round(recall_at_5 / total, 3),
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate BRUCE retrieval quality")
    parser.add_argument("--api-base", default="http://localhost:9998")
    parser.add_argument("--limit", type=int, default=6)
    args = parser.parse_args()

    cases = [
        EvalCase("Wie funktioniert der Bruce Router?", ["router", "routing", "guard"]),
        EvalCase("Was ist die Startup Sequence?", ["startup", "phase", "cold-start"]),
        EvalCase("Welche Rolle hat pgvector?", ["pgvector", "hnsw"]),
        EvalCase("Erkläre die Assembler Konfidenzregeln", ["confidence", "konfidenz", "low_conf"]),
        EvalCase("Welche Performance Targets gibt es?", ["100ms", "latenz", "p95"]),
        EvalCase("Vergleiche Bruce Router und Startup Dokumentation", ["router", "startup"]),
    ]

    result = run_eval(api_base=args.api_base, cases=cases, limit=args.limit)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
