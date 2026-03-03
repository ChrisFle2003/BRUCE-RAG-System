#!/usr/bin/env python3
"""Import markdown/plaintext files into BRUCE Knowledge DB (MVP)."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_SRC = PROJECT_ROOT / "src" / "python"
if str(PYTHON_SRC) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC))

from embedding.service import get_embedder
from common.settings import SETTINGS


def chunk_text(text: str, size: int = 800, overlap_words: int = 35) -> list[str]:
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        current: list[str] = []
        current_len = 0
        idx = start
        while idx < len(words):
            token = words[idx]
            projected = current_len + len(token) + (1 if current else 0)
            if projected > size and current:
                break
            current.append(token)
            current_len = projected
            idx += 1

        if not current:
            current = [words[start][:size]]
            idx = start + 1

        chunk = " ".join(current).strip()
        if chunk:
            chunks.append(chunk)

        if idx >= len(words):
            break
        start = max(start + 1, idx - overlap_words)

    return chunks


def checksum_from_embedding(embedding: list[int]) -> int:
    payload = ",".join(str(v) for v in embedding).encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def import_file(conn, file_path: Path, bib_id: int) -> tuple[int, int]:
    text = file_path.read_text(encoding="utf-8", errors="ignore").strip()
    if not text:
        return 0, 0

    embedder = get_embedder()

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO seiten (bib_id, title, content, full_path)
            VALUES (%s, %s, %s, %s)
            RETURNING seite_id
            """,
            (bib_id, file_path.stem, text, str(file_path)),
        )
        seite_id = int(cur.fetchone()[0])

        chunks = chunk_text(text)
        inserted_chunks = 0
        for idx, chunk in enumerate(chunks):
            embedding = embedder.embed_int16(chunk)
            checksum = checksum_from_embedding(embedding)
            state_vec = embedder.state_vec(embedding)

            cur.execute(
                """
                INSERT INTO vektoren (
                    bib_id, seite_id, dims, checksum, cascade_level,
                    cube_x, cube_y, cube_z, cube_w, cube_u, cube_v, cube_t
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (checksum) DO UPDATE
                SET
                    indexed_at = NOW(),
                    cube_x = EXCLUDED.cube_x,
                    cube_y = EXCLUDED.cube_y,
                    cube_z = EXCLUDED.cube_z,
                    cube_w = EXCLUDED.cube_w,
                    cube_u = EXCLUDED.cube_u,
                    cube_v = EXCLUDED.cube_v,
                    cube_t = EXCLUDED.cube_t
                RETURNING vektor_id
                """,
                (
                    bib_id,
                    seite_id,
                    embedding,
                    checksum,
                    min(idx, 5),
                    state_vec[0],
                    state_vec[1],
                    state_vec[2],
                    state_vec[3],
                    state_vec[4],
                    state_vec[5],
                    state_vec[6],
                ),
            )
            vektor_id = int(cur.fetchone()[0])

            cur.execute(
                """
                INSERT INTO chunks (bib_id, seite_id, chunk_index, text, vektor_id)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (bib_id, seite_id, idx, chunk, vektor_id),
            )
            inserted_chunks += 1

    conn.commit()
    return 1, inserted_chunks


def main() -> int:
    parser = argparse.ArgumentParser(description="Import md/txt files into BRUCE knowledge DB")
    parser.add_argument("path", type=Path, help="Directory or file to import")
    parser.add_argument("--bib-id", type=int, default=2000, help="Target bibliothek_id")
    args = parser.parse_args()

    root = args.path
    if not root.exists():
        raise SystemExit(f"Path not found: {root}")

    files: list[Path]
    if root.is_file():
        files = [root]
    else:
        files = [
            f
            for f in sorted(root.rglob("*"))
            if f.is_file() and f.suffix.lower() in {".md", ".txt"}
        ]

    if not files:
        print("No .md/.txt files found.")
        return 0

    total_docs = 0
    total_chunks = 0

    with psycopg2.connect(SETTINGS.database_url) as conn:
        for file_path in files:
            docs, chunks = import_file(conn, file_path, args.bib_id)
            total_docs += docs
            total_chunks += chunks
            if docs:
                print(f"Imported: {file_path} ({chunks} chunks)")

    print(f"Done. Documents: {total_docs}, Chunks: {total_chunks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
