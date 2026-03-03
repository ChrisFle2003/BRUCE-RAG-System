from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Any

import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel

from common.settings import SETTINGS

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover
    SentenceTransformer = None


class EmbedRequest(BaseModel):
    text: str


class EmbedResponse(BaseModel):
    embedding: list[int]
    state_vec: list[int]
    model: str


class DeterministicEmbedder:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = self._load_model(model_name)

    def _load_model(self, model_name: str):
        if SentenceTransformer is None:
            return None
        try:
            return SentenceTransformer(model_name)
        except Exception:
            return None

    @staticmethod
    def dim_to_zone(val: int, num_zones: int) -> int:
        if num_zones <= 0:
            raise ValueError("num_zones must be positive")
        normalized = int(val) + 32768
        normalized = min(max(normalized, 0), 65535)
        zone_size = 65536 // num_zones
        zone = normalized // zone_size
        return min(zone, num_zones - 1)

    def _encode_float(self, text: str) -> np.ndarray:
        if self._model is None:
            return self._fallback_vector(text)

        raw = np.asarray(self._model.encode(text), dtype=np.float32)
        bins = np.array_split(raw, 64)
        reduced = np.array([float(chunk.mean()) for chunk in bins], dtype=np.float32)
        return np.tanh(reduced)

    @staticmethod
    def _fallback_vector(text: str) -> np.ndarray:
        values = []
        for i in range(64):
            digest = hashlib.sha256(f"{text}:{i}".encode("utf-8")).digest()
            signed = int.from_bytes(digest[:2], byteorder="little", signed=True)
            values.append(signed / 32768.0)
        return np.asarray(values, dtype=np.float32)

    def embed_int16(self, text: str) -> list[int]:
        vec = self._encode_float(text)
        quantized = np.clip(np.rint(vec * 32767.0), -32768, 32767).astype(np.int16)
        return [int(x) for x in quantized.tolist()]

    def state_vec(self, embedding: list[int]) -> list[int]:
        return [self.dim_to_zone(val, 27) for val in embedding[:7]]


@lru_cache(maxsize=1)
def get_embedder() -> DeterministicEmbedder:
    return DeterministicEmbedder(SETTINGS.embedding_model)


app = FastAPI(title="BRUCE Embedding Service", version="1.1")


@app.get("/health")
def health() -> dict[str, Any]:
    embedder = get_embedder()
    model_ready = embedder._model is not None
    return {
        "status": "ready",
        "model": SETTINGS.embedding_model,
        "backend": "sentence-transformers" if model_ready else "hash-fallback",
    }


@app.post("/embed", response_model=EmbedResponse)
def embed(request: EmbedRequest) -> EmbedResponse:
    embedder = get_embedder()
    embedding = embedder.embed_int16(request.text)
    return EmbedResponse(
        embedding=embedding,
        state_vec=embedder.state_vec(embedding),
        model=SETTINGS.embedding_model,
    )
