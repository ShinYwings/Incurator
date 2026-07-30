"""Memory paths: HippoRAG-style associative walks over the graph (explore).

Deterministic bounded walk over ``graph_relations`` from seed entities, scored by
an explicit linear combination (SCHEMA.md §11.6). Full Personalized
PageRank is intentionally out of scope for v0.3.1.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from .. import db

__all__ = ["MemoryPath", "build_memory_paths", "record_memory_paths", "query_hash"]


@dataclass
class MemoryPath:
    start_node_id: str
    hops: list[dict] = field(default_factory=list)
    score: float = 0.0
    source_span_ids: list[str] = field(default_factory=list)


def query_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _score(hops: list[dict], span_ids: list[str], *, domain_fit: float) -> float:
    if not hops:
        return 0.0
    confidences = [float(h.get("confidence") or 0.0) for h in hops]
    avg_conf = sum(confidences) / len(confidences)
    span_support = 1.0 if span_ids else 0.0
    seed_score = 1.0  # path always starts from a seed entity
    recency = 0.0  # promoted/recency not modeled in v0.3.1
    length_penalty = 1.0 / len(hops)  # prefer shorter, tighter paths
    return (
        0.35 * seed_score
        + 0.25 * avg_conf
        + 0.20 * span_support
        + 0.10 * recency
        + 0.10 * domain_fit
    ) * length_penalty


def build_memory_paths(
    db_path: Path,
    *,
    seed_entity_ids: list[str],
    max_depth: int = 2,
    max_paths: int = 20,
    domain_terms: list[str] | None = None,
) -> list[MemoryPath]:
    """Walk the relation graph from seeds, returning scored paths (best first)."""
    domain_terms = [t.lower() for t in (domain_terms or [])]
    paths: list[MemoryPath] = []

    def _domain_fit(entity_id: str) -> float:
        if not domain_terms:
            return 0.0
        ent = db.get_graph_entity(db_path, entity_id)
        if not ent:
            return 0.0
        hay = f"{ent.get('canonical_name','')} {ent.get('description','')}".lower()
        return 1.0 if any(t in hay for t in domain_terms) else 0.0

    def _walk(current: str, depth: int, visited: set[str], hops: list[dict], spans: list[str]) -> None:
        if len(paths) >= max_paths:
            return
        if depth == 0:
            return
        for rel in db.relation_neighborhood(
            db_path,
            [current],
            lifecycle_status="active",
        ):
            nxt = (
                rel["target_entity_id"]
                if rel["source_entity_id"] == current
                else rel["source_entity_id"]
            )
            if nxt in visited:
                continue
            hop = {
                "from": current,
                "relation_id": rel["id"],
                "relation_type": rel["relation_type"],
                "to": nxt,
                "confidence": rel["confidence"],
            }
            new_hops = [*hops, hop]
            new_spans = sorted(set(spans) | set(rel.get("source_span_ids") or []))
            domain_fit = max(_domain_fit(current), _domain_fit(nxt))
            paths.append(
                MemoryPath(
                    start_node_id=new_hops[0]["from"],
                    hops=new_hops,
                    score=_score(new_hops, new_spans, domain_fit=domain_fit),
                    source_span_ids=new_spans,
                )
            )
            _walk(nxt, depth - 1, visited | {nxt}, new_hops, new_spans)

    for seed in seed_entity_ids:
        _walk(seed, max_depth, {seed}, [], [])

    paths.sort(key=lambda p: p.score, reverse=True)
    return paths[:max_paths]


def record_memory_paths(
    db_path: Path, paths: list[MemoryPath], *, q_hash: str, route: str = "explore"
) -> list[str]:
    ids: list[str] = []
    for path in paths:
        pid = db.record_memory_path(
            db_path,
            query_hash=q_hash,
            route=route,
            path=path.hops,
            start_node_id=path.start_node_id,
            score=path.score,
            source_span_ids=path.source_span_ids,
        )
        ids.append(pid)
    return ids
