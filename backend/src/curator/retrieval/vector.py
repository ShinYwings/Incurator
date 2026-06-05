"""P6: brute-force NumPy cosine KNN over chunk embeddings (v0.3.2).

At personal-KB scale (hundreds–low-tens-of-thousands of chunks) a single
matrix-multiply by the normalized query vector is <50 ms and needs no ANN index
or extra dependency. Vectors are stored L2-normalized (see ``embedding.pack_vector``)
so cosine reduces to a dot product. Results collapse to the best chunk per
document; ``sqlite-vec`` is the documented accelerator only past ~50k chunks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .. import db

__all__ = ["VectorHit", "vector_search"]


@dataclass(frozen=True)
class VectorHit:
    doc_id: str
    chunk_id: str
    record_type: str
    score: float  # cosine similarity in [-1, 1]; higher = better
    rank: int  # 1-based; lower = better


def vector_search(
    db_path: Path,
    query_vec,
    *,
    provider: str,
    model: str,
    families: set[str] | None = None,
    limit: int = 50,
) -> list[VectorHit]:
    """Return the best-matching documents for ``query_vec`` by cosine similarity."""
    q = np.asarray(query_vec, dtype=np.float32)
    if q.size == 0:
        return []
    norm = float(np.linalg.norm(q)) or 1.0
    q = q / norm

    with db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT e.chunk_id, e.dim, e.vector, c.doc_id, c.record_type "
            "FROM search_embeddings e JOIN search_chunks c ON e.chunk_id = c.chunk_id "
            "WHERE e.provider = ? AND e.model = ? AND e.status = 'ready'",
            (provider, model),
        ).fetchall()
    if not rows:
        return []

    dim = int(rows[0]["dim"])
    if dim != q.shape[0]:
        return []  # model/dim mismatch → caller degrades to FTS5-only

    mat = np.frombuffer(b"".join(r["vector"] for r in rows), dtype="<f4").reshape(len(rows), dim)
    sims = mat @ q  # all normalized → cosine

    # collapse to the single best chunk per document
    best: dict[str, tuple[float, str, str]] = {}
    for i, row in enumerate(rows):
        doc_id = row["doc_id"]
        record_type = row["record_type"]
        if families and record_type not in families:
            continue
        score = float(sims[i])
        current = best.get(doc_id)
        if current is None or score > current[0]:
            best[doc_id] = (score, row["chunk_id"], record_type)

    ranked = sorted(best.items(), key=lambda kv: kv[1][0], reverse=True)[:limit]
    return [
        VectorHit(doc_id=doc_id, chunk_id=chunk_id, record_type=record_type, score=score, rank=i)
        for i, (doc_id, (score, chunk_id, record_type)) in enumerate(ranked, start=1)
    ]
