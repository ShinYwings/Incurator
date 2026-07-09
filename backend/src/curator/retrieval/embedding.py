"""P5: embedding lifecycle for v0.3.2 DB-native search.

Two stages, both model-optional so search degrades gracefully:

1. ``materialize_chunks`` — split every ``search_documents`` row into
   content-addressed ``search_chunks`` (deterministic, no model). Runs as part of
   ``wiki reindex`` / compile after the document materializer (P3).
2. ``embed_corpus`` — embed chunks that lack a ready vector for the active
   ``provider/model``, storing L2-normalized float32 BLOBs keyed by
   ``(chunk_id, provider, model)`` with an ``input_hash`` staleness signal. A
   missing/unreachable embedder leaves the corpus FTS5-only (``degraded``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .. import db
from .chunking import chunk_text
from .providers import Embedder

__all__ = [
    "ChunkResult",
    "EmbedResult",
    "current_embedding_coverage",
    "materialize_chunks",
    "embed_corpus",
    "pack_vector",
    "unpack_vector",
]


@dataclass(frozen=True)
class ChunkResult:
    documents: int
    chunks: int


@dataclass(frozen=True)
class EmbedResult:
    embedded: int = 0
    skipped: int = 0
    failures: int = 0
    degraded: bool = False
    warning: str = ""
    fingerprint: str = ""


def current_embedding_coverage(
    db_path: Path,
    provider: str,
    model: str,
) -> tuple[int, int]:
    """Return ``(total_chunks, ready_current_embeddings)`` for provider/model."""
    with db.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(c.chunk_id) AS total,
                SUM(CASE WHEN e.chunk_id IS NULL THEN 0 ELSE 1 END) AS ready
            FROM search_chunks c
            LEFT JOIN search_embeddings e
              ON e.chunk_id = c.chunk_id
             AND e.provider = ?
             AND e.model = ?
             AND e.status = 'ready'
             AND e.input_hash = c.input_hash
            """,
            (provider, model),
        ).fetchone()
    return int(row["total"] or 0), int(row["ready"] or 0)


def _sha8(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]


def _input_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def pack_vector(vec: list[float] | np.ndarray) -> tuple[bytes, int]:
    """L2-normalize and pack a vector to little-endian float32 bytes."""
    arr = np.asarray(vec, dtype=np.float32)
    norm = float(np.linalg.norm(arr)) or 1.0
    arr = (arr / norm).astype("<f4")
    return arr.tobytes(), arr.shape[0]


def unpack_vector(blob: bytes, dim: int) -> np.ndarray:
    return np.frombuffer(blob, dtype="<f4", count=dim)


def _chunk_config(search_config: dict) -> dict:
    cfg = dict((search_config or {}).get("chunking") or {})
    return {
        "target_tokens": int(cfg.get("target_tokens", 256)),
        "max_tokens": int(cfg.get("max_tokens", 384)),
        "overlap_tokens": int(cfg.get("overlap_tokens", 48)),
        "min_tokens": int(cfg.get("min_tokens", 32)),
    }


def materialize_chunks(db_path: Path, search_config: dict | None = None) -> ChunkResult:
    """Chunk every search document into ``search_chunks`` (content-addressed)."""
    params = _chunk_config(search_config or {})
    docs = db.list_search_documents(db_path)
    rows: list[tuple] = []
    for doc in docs:
        body = "\n".join(part for part in (doc.get("title") or "", doc.get("body") or "") if part).strip()
        chunks = chunk_text(body, **params)
        span_ids = (doc.get("provenance") or {}).get("source_span_ids") or []
        for index, chunk in enumerate(chunks):
            ihash = _input_hash(chunk.text)
            chunk_id = f"CHK-{doc['doc_id']}-{index}-{_sha8(ihash)}"
            rows.append(
                (
                    chunk_id,
                    doc["doc_id"],
                    doc["record_type"],
                    doc["record_id"],
                    index,
                    chunk.char_start,
                    chunk.char_end,
                    chunk.text,
                    ihash,
                    json.dumps([str(s) for s in span_ids]),
                    json.dumps({"dependency_hash": doc.get("dependency_hash", "")}),
                )
            )
    if rows:
        with db.connect(db_path) as conn:
            conn.execute("CREATE TEMP TABLE current_search_chunks(chunk_id TEXT PRIMARY KEY)")
            conn.executemany(
                "INSERT INTO current_search_chunks(chunk_id) VALUES (?)",
                [(row[0],) for row in rows],
            )
            conn.executemany(
                """
                INSERT INTO search_chunks
                    (chunk_id, doc_id, record_type, record_id, chunk_index, char_start,
                     char_end, text, input_hash, source_span_ids, provenance_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chunk_id) DO UPDATE SET
                    doc_id = excluded.doc_id,
                    record_type = excluded.record_type,
                    record_id = excluded.record_id,
                    chunk_index = excluded.chunk_index,
                    char_start = excluded.char_start,
                    char_end = excluded.char_end,
                    text = excluded.text,
                    input_hash = excluded.input_hash,
                    source_span_ids = excluded.source_span_ids,
                    provenance_json = excluded.provenance_json
                """,
                rows,
            )
            conn.execute(
                "DELETE FROM search_chunks "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM current_search_chunks c "
                "WHERE c.chunk_id = search_chunks.chunk_id"
                ")"
            )
            conn.execute("DROP TABLE current_search_chunks")
    else:
        with db.connect(db_path) as conn:
            conn.execute("DELETE FROM search_chunks")
    db.set_index_meta(db_path, "search_chunk_count", str(len(rows)))
    return ChunkResult(documents=len(docs), chunks=len(rows))


def embed_corpus(
    db_path: Path,
    embedder: Embedder | None,
    *,
    batch_size: int = 32,
) -> EmbedResult:
    """Embed chunks missing a ready vector for the embedder's provider/model."""
    if embedder is None:
        db.set_index_meta(db_path, "search_embed_fingerprint", "")
        return EmbedResult(degraded=True, warning="no embedder configured (FTS5-only)")

    fingerprint = embedder.fingerprint
    existing = {
        row["chunk_id"]: row
        for row in db.get_search_embeddings(db_path, embedder.provider, embedder.model)
    }

    pending: list[dict] = []
    with db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT chunk_id, text, input_hash, provenance_json FROM search_chunks "
            "ORDER BY doc_id, chunk_index"
        ).fetchall()
    skipped = 0
    for row in rows:
        prior = existing.get(row["chunk_id"])
        if prior and prior.get("input_hash") == row["input_hash"]:
            skipped += 1
            continue
        pending.append(dict(row))

    embedded = 0
    failures = 0
    warning = ""
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        try:
            vectors = embedder.embed([r["text"] for r in batch])
        except Exception as exc:  # transport / model failure → degrade
            failures += len(batch)
            warning = f"embedding failed: {exc}"
            continue
        for row, vec in zip(batch, vectors):
            blob, dim = pack_vector(vec)
            dep = (json.loads(row.get("provenance_json") or "{}") or {}).get("dependency_hash", "")
            db.upsert_search_embedding(
                db_path,
                chunk_id=row["chunk_id"],
                provider=embedder.provider,
                model=embedder.model,
                dim=dim,
                vector=blob,
                input_hash=row["input_hash"],
                dependency_hash=dep,
            )
            embedded += 1

    db.set_index_meta(db_path, "search_embed_fingerprint", fingerprint if embedded or skipped else "")
    db.set_index_meta(db_path, "search_embedded_count", str(embedded + skipped))
    return EmbedResult(
        embedded=embedded,
        skipped=skipped,
        failures=failures,
        degraded=bool(failures and not (embedded or skipped)),
        warning=warning,
        fingerprint=fingerprint,
    )
