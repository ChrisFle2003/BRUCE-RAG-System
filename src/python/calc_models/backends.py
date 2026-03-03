from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import httpx

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
    "what",
    "how",
    "the",
}


@dataclass
class Chunk:
    seite_id: int
    content: str
    similarity: float


def _tokens(text: str) -> set[str]:
    return {
        tok
        for tok in re.findall(r"[a-zA-Z0-9äöüÄÖÜß]+", text.lower())
        if len(tok) >= 3 and tok not in STOPWORDS
    }


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


def _best_snippet(chunk_text: str, query_tokens: set[str]) -> str:
    parts = [
        part.strip()
        for part in re.split(r"(?<=[\.\!\?])\s+|\n+", chunk_text)
        if part.strip()
    ]
    if not parts:
        return chunk_text[:320]
    if not query_tokens:
        return parts[0][:320]

    ranked = sorted(
        parts,
        key=lambda part: _soft_overlap_ratio(query_tokens, _tokens(part)),
        reverse=True,
    )
    return ranked[0][:320]


def _confidence(chunk: Chunk, query_text: str) -> float:
    query_tokens = _tokens(query_text)
    chunk_tokens = _tokens(chunk.content)
    overlap = _soft_overlap_ratio(query_tokens, chunk_tokens)

    base = max(0.0, min(0.99, float(chunk.similarity)))
    score = (0.65 * base) + (0.35 * overlap) + 0.10
    return round(min(score, 0.99), 2)


class ModelBackend:
    name = "base"

    def infer(self, query_text: str, chunks: list[Chunk], max_items: int = 4, route_name: str = "DEFAULT") -> list[dict[str, Any]]:
        raise NotImplementedError


class ExtractiveBackend(ModelBackend):
    name = "extractive-v1"

    def infer(self, query_text: str, chunks: list[Chunk], max_items: int = 4, route_name: str = "DEFAULT") -> list[dict[str, Any]]:
        if not chunks:
            return [
                {
                    "type": "fact",
                    "content": "Keine Chunks geliefert; Antwort basiert auf minimalem Stub.",
                    "confidence": 0.62,
                    "entity_id": "stub:no_chunks",
                }
            ]

        bausteine: list[dict[str, Any]] = []
        query_tokens = _tokens(query_text)
        for chunk in sorted(chunks, key=lambda c: c.similarity, reverse=True)[:max_items]:
            snippet = _best_snippet(chunk.content, query_tokens)
            conf = _confidence(chunk, query_text)
            overlap = _soft_overlap_ratio(query_tokens, _tokens(chunk.content))
            if overlap >= 0.5:
                conf = max(conf, 0.72)
            bausteine.append(
                {
                    "type": "fact",
                    "content": snippet,
                    "confidence": conf,
                    "source_seite_id": chunk.seite_id,
                    "entity_id": f"chunk:{chunk.seite_id}",
                }
            )

            lowered = chunk.content.lower()
            if "def " in lowered or "class " in lowered or "{" in lowered:
                bausteine.append(
                    {
                        "type": "code",
                        "content": chunk.content[:320],
                        "confidence": 1.0,
                        "source_seite_id": chunk.seite_id,
                        "entity_id": f"code:{chunk.seite_id}",
                    }
                )

        return bausteine


class HFBackend(ModelBackend):
    name = "hf-local"

    def __init__(self) -> None:
        self._pipeline = None
        model_name = os.getenv("HF_MODEL", "sshleifer/tiny-gpt2")
        try:
            from transformers import pipeline

            self._pipeline = pipeline("text-generation", model=model_name)
            self.name = f"hf-local:{model_name}"
        except Exception:
            self._pipeline = None
            self.name = "hf-local:unavailable"

    def infer(self, query_text: str, chunks: list[Chunk], max_items: int = 4, route_name: str = "DEFAULT") -> list[dict[str, Any]]:
        if not self._pipeline:
            return ExtractiveBackend().infer(query_text, chunks, max_items=max_items, route_name=route_name)

        context = "\n\n".join(chunk.content[:240] for chunk in chunks[:max_items])
        prompt = (
            "Beantworte die Frage nur mit den folgenden Kontextinformationen. "
            "Falls Kontext unzureichend ist, sag das klar.\n\n"
            f"Frage: {query_text}\n\n"
            f"Kontext:\n{context}\n\nAntwort:"
        )
        generated = self._pipeline(prompt, max_new_tokens=120, do_sample=False)
        text = generated[0]["generated_text"]
        answer = text.split("Antwort:", 1)[-1].strip()[:600]

        return [
            {
                "type": "fact",
                "content": answer,
                "confidence": 0.82,
                "entity_id": "hf:answer",
                "source_seite_id": chunks[0].seite_id if chunks else 0,
            }
        ]


class HFInferenceAPIBackend(ModelBackend):
    name = "hf-api"

    def __init__(self) -> None:
        # Default to a stronger seq2seq model than flan-t5-small.
        self.model_name = os.getenv("HF_API_MODEL", "google/flan-t5-base")
        self.api_token = os.getenv("HF_API_TOKEN", "")
        self.endpoint = f"https://api-inference.huggingface.co/models/{self.model_name}"
        if not self.api_token:
            self.name = "hf-api:missing-token"
        else:
            self.name = f"hf-api:{self.model_name}"

    def infer(self, query_text: str, chunks: list[Chunk], max_items: int = 4, route_name: str = "DEFAULT") -> list[dict[str, Any]]:
        if not self.api_token:
            return ExtractiveBackend().infer(query_text, chunks, max_items=max_items, route_name=route_name)

        context = "\n\n".join(chunk.content[:240] for chunk in chunks[:max_items])
        prompt = (
            "Beantworte die Frage kurz nur basierend auf dem Kontext. "
            "Falls unsicher, sage explizit unsicher.\n\n"
            f"Frage: {query_text}\n\nKontext:\n{context}\n\nAntwort:"
        )

        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(
                    self.endpoint,
                    headers={"Authorization": f"Bearer {self.api_token}"},
                    json={"inputs": prompt, "parameters": {"max_new_tokens": 120}},
                )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list) and payload:
                generated = str(payload[0].get("generated_text", "")).strip()
            elif isinstance(payload, dict):
                generated = str(payload.get("generated_text", "")).strip()
            else:
                generated = ""

            if not generated:
                raise ValueError("empty hf-api generation")

            return [
                {
                    "type": "fact",
                    "content": generated[:700],
                    "confidence": 0.8,
                    "entity_id": "hf_api:answer",
                    "source_seite_id": chunks[0].seite_id if chunks else 0,
                }
            ]
        except Exception:
            return ExtractiveBackend().infer(query_text, chunks, max_items=max_items, route_name=route_name)


class GraniteBackend(ModelBackend):
    """
    IBM Granite 3.2 350M via llama.cpp Server API.

    Designregel (RFC §6.5): Das Modell darf NUR aus den übergebenen Chunks
    antworten. Kein Weltwissen, keine Halluzinierung, nur Extraktion.
    temperature=0 + seed=42 garantiert Determinismus (RFC §2.1, §14).

    llama.cpp Server muss laufen:
        scripts/run_calc_server.sh 8001 0 /path/to/granite4-350m-h-q8_0.gguf
    """
    name = "granite4-350m-q8"

    def __init__(self) -> None:
        self.endpoint = os.getenv("LLAMA_ENDPOINT", "http://localhost:8080")
        self.name = f"granite4-350m-q8@{self.endpoint}"
        # Persistenter Client – kein TCP Handshake pro Request (RFC Performance)
        self._client = httpx.Client(
            base_url=self.endpoint,
            timeout=httpx.Timeout(connect=1.0, read=45.0, write=2.0, pool=1.0),
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=4),
        )
        # System-Prompts aus prompts.py (route-spezifisch)
        try:
            from calc_models.prompts import SYSTEM_PROMPTS
            self._system_prompts = SYSTEM_PROMPTS
        except ImportError:
            self._system_prompts = {"DEFAULT": "Du bist ein Wissens-Extraktor."}

    def infer(
        self,
        query_text: str,
        chunks: list[Chunk],
        max_items: int = 4,
        route_name: str = "DEFAULT",
    ) -> list[dict[str, Any]]:
        if not chunks:
            return [
                {
                    "type": "fact",
                    "content": "Keine Chunks verfügbar – Retrieval hat keine Ergebnisse geliefert.",
                    "confidence": 0.50,
                    "entity_id": "granite:no_chunks",
                }
            ]

        # System-Prompt für diese Route (RAG-Only, kein Weltwissen)
        system_prompt = self._system_prompts.get(
            route_name.upper(),
            self._system_prompts["DEFAULT"]
        )

        # Kontext aus Chunks aufbauen
        context_parts: list[str] = []
        for i, chunk in enumerate(chunks[:max_items], 1):
            context_parts.append(
                f"[Quelle {i} | Seite {chunk.seite_id} | Relevanz {chunk.similarity:.2f}]\n"
                f"{chunk.content[:600]}"
            )
        context_block = "\n\n---\n\n".join(context_parts)

        # Prompt: Streng auf Chunks beschränkt
        user_prompt = (
            f"FRAGE: {query_text}\n\n"
            f"VERFÜGBARE QUELLEN:\n\n{context_block}\n\n"
            "ANTWORT (nur aus den obigen Quellen, keine anderen Informationen):"
        )

        try:
            response = self._client.post(
                "/v1/chat/completions",
                json={
                    "model": "granite",           # llama.cpp Server ignoriert diesen Wert
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 256,
                    "temperature": 0.0,           # PFLICHT: RFC §2.1 Determinismus
                    "seed": 42,                   # PFLICHT: RFC §2.1 Reproduzierbarkeit
                    "top_p": 1.0,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()

            generated = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )

            if not generated or len(generated) < 5:
                raise ValueError("empty or too short granite response")

            # Konfidenz aus usage-Stats ableiten
            usage = data.get("usage", {})
            completion_tokens = int(usage.get("completion_tokens", 50))
            # Kurze, präzise Antworten = höhere Konfidenz (Granite halluziniert weniger)
            conf = min(0.93, 0.72 + (1.0 / max(completion_tokens, 10)) * 2.0)

            return [
                {
                    "type": "fact",
                    "content": generated,
                    "confidence": round(conf, 2),
                    "entity_id": f"granite:{route_name.lower()}",
                    "source_seite_id": chunks[0].seite_id if chunks else 0,
                    "meta": {
                        "model": self.name,
                        "completion_tokens": completion_tokens,
                        "chunks_used": len(context_parts),
                    },
                }
            ]

        except httpx.ConnectError:
            # llama-server nicht erreichbar → Graceful Fallback
            return ExtractiveBackend().infer(query_text, chunks, max_items=max_items, route_name=route_name)
        except Exception:
            return ExtractiveBackend().infer(query_text, chunks, max_items=max_items, route_name=route_name)


def get_backend() -> ModelBackend:
    backend_name = os.getenv("CALC_BACKEND", "extractive").lower()
    if backend_name == "granite":
        return GraniteBackend()
    if backend_name == "hf":
        return HFBackend()
    if backend_name in {"hf_api", "hf-api"}:
        return HFInferenceAPIBackend()
    return ExtractiveBackend()
