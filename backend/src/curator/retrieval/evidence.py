"""Evidence-pack construction per route (v0.3.1).

Combines the DB graph (entities/relations/community_reports/memory_paths/
source_spans — the source of truth) with qmd search over the derived
``.curator/Collections`` corpus. qmd is the fallback retrieval engine; when it is
unavailable or the graph is incomplete, evidence degrades with a warning.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from .. import config as cfg
from .. import db
from ..pipeline import memory_paths as mp
from .models import EvidenceItem, EvidencePack, QueryRequest

__all__ = ["build_evidence", "seed_terms"]

_STOP = {
    "the", "and", "for", "with", "what", "which", "that", "this", "from", "into",
    "does", "are", "how", "why", "when", "where", "between", "about", "of", "to",
    "is", "a", "an", "in", "on",
}


def _hydrate_full_texts(db_path: Path, span_ids: list[str]) -> dict[str, str]:
    """Hydrate exact full span text for evidence items (F10, §10.2).

    Lazy-imports the compile pipeline to avoid a module-level import cycle
    (``pipeline.compile`` imports ``retrieval.materializer``).
    """
    from ..pipeline.compile import hydrate_spans

    return hydrate_spans(db_path, span_ids)


def seed_terms(query: str, limit: int = 8) -> list[str]:
    terms: list[str] = []
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9+\-]*", query):
        low = tok.lower()
        if low in _STOP or (len(tok) <= 3 and not tok.isupper()):
            continue
        if tok not in terms:
            terms.append(tok)
    return terms[:limit]


def _search_hits(
    paths: cfg.WikiPaths, query: str, limit: int, warnings: list[str]
) -> tuple[list[EvidenceItem], dict]:
    """DB-native hybrid search hits (v0.3.2; replaces the qmd fallback)."""
    try:
        from .. import search

        # min_score=0 — native RRF/rerank scores are not on qmd's 0–1 scale, so the
        # engine ranks and caps by `limit` rather than hard-thresholding.
        results = search.query(
            paths, query, mode="hybrid", limit=limit, min_score=0.0,
            hydrate=True, rerank=True, persist=False,
        )
    except Exception as e:  # backend error → degrade gracefully
        warnings.append(f"search unavailable: {e}")
        return [], {}
    warnings.extend(results.warnings if hasattr(results, "warnings") else [])
    items: list[EvidenceItem] = []
    for hit in results.hits:
        text = (hit.full_content or hit.snippet or "")[:1200]
        items.append(
            EvidenceItem(
                id=hit.full_path, kind="search_hit", title=hit.title or hit.full_path,
                text=text, score=hit.score, source_span_ids=hit.source_span_ids,
            )
        )
    return items, results.retrieval_trace


def _add_search_hits(
    pack: EvidencePack, paths: cfg.WikiPaths, query: str, limit: int
) -> None:
    hits, retrieval_trace = _search_hits(paths, query, limit, pack.warnings)
    pack.items.extend(hits)
    pack.source_span_ids = sorted({
        *pack.source_span_ids,
        *(span_id for hit in hits for span_id in hit.source_span_ids),
    })
    pack.retrieval_trace = retrieval_trace


def _entity_evidence(db_path: Path, query: str) -> tuple[list[EvidenceItem], list[str]]:
    items: list[EvidenceItem] = []
    span_ids: set[str] = set()
    seen: set[str] = set()
    for term in seed_terms(query):
        for ent in db.find_graph_entities(db_path, term, limit=5):
            if ent["id"] in seen:
                continue
            seen.add(ent["id"])
            items.append(
                EvidenceItem(
                    id=ent["id"], kind="entity",
                    title=f'{ent["canonical_name"]} ({ent["entity_type"]})',
                    text=ent.get("description", ""),
                    source_span_ids=ent.get("source_span_ids", []),
                )
            )
            span_ids.update(ent.get("source_span_ids") or [])
    return items, sorted(span_ids)


def _span_items(db_path: Path, span_ids: list[str]) -> list[EvidenceItem]:
    full = _hydrate_full_texts(db_path, span_ids)
    items: list[EvidenceItem] = []
    for span in db.get_source_spans_by_ids(db_path, span_ids):
        text = full.get(span["id"])
        items.append(
            EvidenceItem(
                id=span["id"], kind="source_span",
                title=span.get("section_title") or span.get("relpath", ""),
                text=text if text is not None else span.get("text_preview", ""),
                evidence_status="ok" if text is not None else "stale",
                source_span_ids=[span["id"]],
            )
        )
    return items


def _report_items(db_path: Path) -> tuple[list[EvidenceItem], list[str], list[str]]:
    items: list[EvidenceItem] = []
    report_ids: list[str] = []
    span_ids: set[str] = set()
    for rep in db.list_community_reports(db_path):
        findings = "; ".join(f.get("summary", "") for f in rep.get("findings", []) if isinstance(f, dict))
        items.append(
            EvidenceItem(
                id=rep["id"], kind="community_report", title=rep.get("title", ""),
                text=f'{rep.get("summary","")}\n{findings}'.strip(),
                source_span_ids=rep.get("source_span_ids", []),
                community_report_id=rep["id"], score=rep.get("rank", 0.0),
            )
        )
        report_ids.append(rep["id"])
        span_ids.update(rep.get("source_span_ids") or [])
    return items, report_ids, sorted(span_ids)


def _synthesis_items(db_path: Path, limit: int = 6) -> tuple[list[EvidenceItem], list[str], list[str]]:
    """Shared L4 Synthesis nodes — the durable corpus-wide cross-cutting insights.

    These are the highest-level standing evidence for broad/global reasoning; the
    dynamic Curation lens recombines them with community reports at query time.
    """
    items: list[EvidenceItem] = []
    node_ids: list[str] = []
    span_ids: set[str] = set()
    for node in db.list_synthesis_nodes(db_path)[:limit]:
        items.append(
            EvidenceItem(
                id=node["id"], kind="synthesis", title=node.get("title", ""),
                text=f'{node.get("statement","")}\n{node.get("full_content","")}'.strip(),
                source_span_ids=node.get("source_span_ids", []),
                synthesis_node_id=node["id"], score=node.get("confidence", 0.0),
            )
        )
        node_ids.append(node["id"])
        span_ids.update(node.get("source_span_ids") or [])
    return items, node_ids, sorted(span_ids)


def _resolve_source_id(db_path: Path, source_key: str) -> int | None:
    if source_key.isdigit():
        return int(source_key)
    with db.connect(db_path) as conn:
        row = conn.execute("SELECT id FROM sources WHERE relpath = ?", (source_key,)).fetchone()
    return int(row["id"]) if row else None


def build_evidence(
    paths: cfg.WikiPaths, request: QueryRequest, route: str, *, limit: int = 8
) -> EvidencePack:
    db_path = paths.state_db
    q = request.working_query
    warnings: list[str] = []
    pack = EvidencePack(route=route, warnings=warnings)
    # §30.1: generate a unique retrieval execution ID for this call.
    pack.retrieval_execution_id = f"RTR-{uuid.uuid4().hex[:8]}"

    if route == "source-section":
        sid = _resolve_source_id(db_path, request.source_key)
        if sid is None:
            warnings.append(f"unknown source: {request.source_key}")
        else:
            spans = db.list_source_spans(db_path, sid)
            full = _hydrate_full_texts(db_path, [s["id"] for s in spans])
            for span in spans:
                text = full.get(span["id"])
                pack.items.append(
                    EvidenceItem(
                        id=span["id"], kind="source_span",
                        title=span.get("section_title") or "",
                        text=text if text is not None else span.get("text_preview", ""),
                        evidence_status="ok" if text is not None else "stale",
                        source_span_ids=[span["id"]],
                    )
                )
            pack.source_span_ids = [s["id"] for s in spans]
        return pack

    if route == "global":
        # Shared L4 Synthesis nodes are the highest-level standing evidence; lead
        # with them, then back them with the community reports they distil.
        syn_items, syn_ids, syn_spans = _synthesis_items(db_path)
        report_items, report_ids, report_spans = _report_items(db_path)
        items = syn_items + report_items
        if not items:
            warnings.append("no synthesis or community reports; falling back to qmd")
            _add_search_hits(pack, paths, q, limit)
        else:
            pack.items = items
            pack.source_span_ids = sorted(set(syn_spans) | set(report_spans))
        pack.synthesis_node_ids = syn_ids
        pack.community_report_ids = report_ids
        return pack

    if route == "explore":
        ent_items, span_ids = _entity_evidence(db_path, q)
        seed_ids = [it.id for it in ent_items]
        paths_found = mp.build_memory_paths(db_path, seed_entity_ids=seed_ids, max_depth=2)
        mpath_ids = mp.record_memory_paths(db_path, paths_found, q_hash=mp.query_hash(q), route="explore")
        for path_obj, pid in zip(paths_found, mpath_ids):
            hop_desc = " → ".join(h.get("relation_type", "") for h in path_obj.hops)
            pack.items.append(
                EvidenceItem(
                    id=pid, kind="memory_path", title="associative path",
                    text=hop_desc, score=path_obj.score,
                    source_span_ids=path_obj.source_span_ids, memory_path_id=pid,
                )
            )
            span_ids = sorted(set(span_ids) | set(path_obj.source_span_ids))
        syn_items, syn_ids, syn_spans = _synthesis_items(db_path, limit=3)
        report_items, report_ids, report_spans = _report_items(db_path)
        pack.items.extend(syn_items)  # synthesis primer (highest-level)
        pack.items.extend(report_items[:3])  # community primer
        pack.items.extend(ent_items)
        pack.memory_path_ids = mpath_ids
        pack.synthesis_node_ids = syn_ids
        pack.community_report_ids = report_ids[:3]
        pack.source_span_ids = sorted(set(span_ids) | set(report_spans) | set(syn_spans))
        return pack

    # local: entities + their spans + qmd hits.
    ent_items, span_ids = _entity_evidence(db_path, q)
    pack.items.extend(ent_items)
    pack.items.extend(_span_items(db_path, span_ids))
    pack.source_span_ids = span_ids
    _add_search_hits(pack, paths, q, limit)
    return pack
