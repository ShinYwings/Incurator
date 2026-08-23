"""Evidence-pack construction per route (v0.3.1).

Combines the DB graph (entities/relations/community_reports/memory_paths/
source_spans — the source of truth) with DB-native hybrid search (FTS5 + vector
+ RRF + reranking). Search is the fallback path; when unavailable or the graph
is incomplete, evidence degrades with a warning.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from .. import config as cfg
from .. import curate_yml, db
from ..pipeline import memory_paths as mp
from ..pipeline.source_spans import classify_span_loss, describe_span_loss
from .models import EvidenceItem, EvidencePack, QueryRequest, StructuredLocator

__all__ = ["build_evidence", "seed_terms"]

_STOP = {
    "the", "and", "for", "with", "what", "which", "that", "this", "from", "into",
    "does", "are", "how", "why", "when", "where", "between", "about", "of", "to",
    "is", "a", "an", "in", "on",
}

# §28.2 / §22.6: maximum community reports / synthesis nodes for global route.
_MAX_GLOBAL_REPORTS = 10
_MAX_GLOBAL_SYNTHESIS = 6


def _hydrate_full_texts(db_path: Path, span_ids: list[str]) -> dict[str, str]:
    """Hydrate exact full span text for evidence items (F10, §10.2).

    Lazy-imports the compile pipeline to avoid a module-level import cycle
    (``pipeline.compile`` imports ``retrieval.materializer``).
    """
    from ..pipeline.compile import hydrate_spans

    return hydrate_spans(db_path, span_ids)


def _span_relpaths(db_path: Path, span_ids: list[str]) -> dict[str, str]:
    """Map span_id -> source relpath, for policy source-scope filtering (§28.1)."""
    if not span_ids:
        return {}
    return {
        row["id"]: row.get("relpath", "")
        for row in db.get_source_spans_by_ids(db_path, span_ids)
    }


def _scope_filter_spans(
    db_path: Path,
    span_ids: list[str],
    policy: "curate_yml.CurationPolicy | None",
) -> list[str]:
    """Return only the span ids whose source relpath is in policy scope (§28.1).

    A ``None`` policy is the open default — all spans pass.
    """
    if policy is None or not span_ids:
        return list(span_ids)
    relpaths = _span_relpaths(db_path, span_ids)
    return [s for s in span_ids if policy.allows_source(relpaths.get(s, ""))]


def _item_in_scope(
    db_path: Path,
    item: EvidenceItem,
    policy: "curate_yml.CurationPolicy | None",
) -> bool:
    """Strict source-scope rule (§28.1).

    An item is kept only when **every** backing span is in scope. A single
    out-of-scope span drops the whole item — for a multi-source L2/L3 artifact
    (community report, synthesis) the rendered *text* already commingles all its
    sources, so keeping it would leak excluded content and trimming
    ``source_span_ids`` would corrupt provenance. ``source_span_ids`` is therefore
    never mutated here. Items with no backing spans carry no provenance to judge
    and are kept.
    """
    if policy is None or not item.source_span_ids:
        return True
    kept = _scope_filter_spans(db_path, item.source_span_ids, policy)
    return len(kept) == len(item.source_span_ids)


def _apply_policy_scope(
    db_path: Path,
    pack: EvidencePack,
    policy: "curate_yml.CurationPolicy | None",
) -> None:
    """Drop out-of-scope evidence from the pack and recompute provenance (§28.1).

    Single source of truth for every route: strictly excludes any item with an
    out-of-scope backing span, records the number dropped in
    ``omitted_counts['policy_excluded']`` (conservation of candidate mass), then
    rebuilds ``source_span_ids`` and the per-kind id lists from the survivors so
    no excluded span/report/synthesis lingers in the pack.
    """
    if policy is None:
        return
    original_count = len(pack.items)
    pack.items = [it for it in pack.items if _item_in_scope(db_path, it, policy)]
    dropped = original_count - len(pack.items)
    if dropped:
        pack.omitted_counts["policy_excluded"] = (
            pack.omitted_counts.get("policy_excluded", 0) + dropped
        )
    spans: set[str] = set()
    reports: list[str] = []
    syntheses: list[str] = []
    mpaths: list[str] = []
    for it in pack.items:
        spans.update(it.source_span_ids)
        if it.community_report_id:
            reports.append(it.community_report_id)
        if it.synthesis_node_id:
            syntheses.append(it.synthesis_node_id)
        if it.memory_path_id:
            mpaths.append(it.memory_path_id)
    pack.source_span_ids = sorted(spans)
    pack.community_report_ids = sorted(set(reports))
    pack.synthesis_node_ids = sorted(set(syntheses))
    if mpaths:
        pack.memory_path_ids = mpaths


def _source_meta_by_ids(db_path: Path, source_ids: list[int]) -> dict[int, dict]:
    """Batch-fetch source metadata for locator resolution (§29.4)."""
    if not source_ids:
        return {}
    with db.connect(db_path) as conn:
        ph = ",".join("?" for _ in source_ids)
        rows = conn.execute(
            f"SELECT id, file_type, external_ref, import_origin_ref, "
            f"logical_source_id, is_reference "
            f"FROM sources WHERE id IN ({ph})",
            tuple(source_ids),
        ).fetchall()
    return {row["id"]: dict(row) for row in rows}


def _build_locator(span: dict, src: dict) -> StructuredLocator:
    """Build a StructuredLocator from a span row and its source metadata (§29.4)."""
    ft = src.get("file_type", "md")
    relpath = span.get("relpath")
    if ft == "pdf":
        source_kind = "vault_pdf"
    elif src.get("is_reference"):
        source_kind = "external_uri"
    elif relpath and relpath.lstrip("/").startswith("02_Wiki/"):
        source_kind = "promoted_wiki"  # §29.2: note promoted from L4
    else:
        source_kind = "vault_markdown"
    heading = span.get("section_title")
    toc_id = span.get("toc_id")
    page_number = span.get("page_number")
    logical = str(src.get("logical_source_id") or "")
    external_uri = None
    if src.get("is_reference"):
        external_uri = (
            f"zotero://open-pdf/library/items/{logical.split(':', 1)[1]}"
            if logical.startswith("zotero:")
            else (src.get("external_ref") or src.get("import_origin_ref"))
        )
    if not relpath:
        locator_status = "fallback_source"
    elif heading or toc_id or page_number:
        locator_status = "exact"
    else:
        locator_status = "fallback_file"
    return StructuredLocator(
        source_id=span.get("source_id"),
        source_kind=source_kind,
        relpath=relpath,
        heading=heading,
        block_id=None,
        page_number=page_number,
        toc_id=toc_id,
        external_uri=external_uri,
        locator_status=locator_status,
    )


def seed_terms(query: str, limit: int = 8) -> list[str]:
    """Entity seed terms from the INTERNAL (English) query.

    Latin-only on purpose: `working_query` is English by contract. Tokenizing
    other scripts here would mean the internals had gone multilingual, which is
    what the boundary translation exists to prevent. If a non-English question
    reaches this point, the caller failed to supply `english_query` and
    `context_fetch` warns about it rather than quietly returning nothing.
    """
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
    """DB-native hybrid search hits."""
    try:
        from .. import search

        # min_score=0 — native RRF/rerank scores are not on a fixed 0–1 scale, so the
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
        # A search hit over a report or synthesis node IS L3/L4 evidence. The
        # engine knows the record type; dropping it here made real L4 content
        # arrive as an anonymous `search_hit` with an empty `synthesis_node_id`,
        # so the pack's own counters reported zero synthesis while serving it.
        record_type = getattr(hit, "record_type", "") or ""
        items.append(
            EvidenceItem(
                id=hit.full_path, kind="search_hit", title=hit.title or hit.full_path,
                text=text, score=hit.score, source_span_ids=hit.source_span_ids,
                support_status=getattr(hit, "support_status", "") or "",
                community_report_id=(
                    hit.docid if record_type == "community_report" else ""
                ),
                synthesis_node_id=(
                    hit.docid if record_type == "synthesis_node" else ""
                ),
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
    if not span_ids:
        return []
    full = _hydrate_full_texts(db_path, span_ids)
    span_by_id = {span["id"]: span for span in db.get_source_spans_by_ids(db_path, span_ids)}
    spans = [span_by_id[span_id] for span_id in span_ids if span_id in span_by_id]
    src_ids = [s["source_id"] for s in spans if s.get("source_id") is not None]
    src_meta = _source_meta_by_ids(db_path, list(set(src_ids)))
    items: list[EvidenceItem] = []
    for span in spans:
        text = full.get(span["id"])
        sid = span.get("source_id")
        locator = _build_locator(span, src_meta.get(sid, {}) if sid is not None else {})
        body = text if text is not None else span.get("text_preview", "")
        # A region the parser could not read reaches the model as a bare artifact
        # (`**==> picture [185 x 12] intentionally omitted <==**`) unless we say
        # what it is. That produced answers that hedged — "I cannot retrieve the
        # text of equation 29" — without ever naming the cause or the remedy.
        # Substituting the description does not hide evidence: there is no text
        # here to hide, and the artifact conveys nothing the description does not.
        loss = _span_loss(span)
        if loss is not None:
            body = describe_span_loss(loss)
        items.append(
            EvidenceItem(
                id=span["id"], kind="source_span",
                title=span.get("section_title") or span.get("relpath", ""),
                text=body,
                evidence_status="ok" if text is not None else "stale",
                source_span_ids=[span["id"]],
                locator=locator,
            )
        )
    return items


def _span_loss(span: dict) -> dict | None:
    """Read a span's §26.2b loss record, tolerating rows never backfilled.

    Falls back to classifying the stored text directly: `backfill_span_loss`
    fills the record in during `wiki sync`, but a vault that has not synced yet
    must still get a truthful answer rather than the raw parser artifact.
    """
    raw = span.get("metadata")
    if raw:
        try:
            metadata = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError):
            metadata = None
        if isinstance(metadata, dict):
            loss = metadata.get("loss")
            if isinstance(loss, dict):
                return loss
    return classify_span_loss(str(span.get("text_preview") or ""))


def _report_score(rep: dict, query_terms: set[str]) -> float:
    """Query-relevance score: overlap of query terms with report title+summary (§22.6)."""
    if not query_terms:
        return rep.get("rank", 0.0)
    target = f'{rep.get("title", "")} {rep.get("summary", "")}'.lower()
    target_tokens = set(re.findall(r"[a-z][a-z0-9+\-]*", target))
    overlap = len(query_terms & target_tokens)
    return overlap / len(query_terms) + rep.get("rank", 0.0) * 0.01


def _report_items(
    db_path: Path,
    query: str = "",
    limit: int = _MAX_GLOBAL_REPORTS,
) -> tuple[list[EvidenceItem], list[str], list[str], int]:
    """Return top-N query-relevant community reports (§28.2 / §22.6).

    Returns (items, report_ids, span_ids, omitted_count).
    """
    query_terms = {t.lower() for t in re.findall(r"[a-zA-Z][a-zA-Z0-9+\-]*", query)
                   if t.lower() not in _STOP and len(t) > 2}
    all_reports = db.list_community_reports(db_path)
    scored = sorted(all_reports, key=lambda r: _report_score(r, query_terms), reverse=True)
    selected = scored[:limit]
    omitted = max(0, len(all_reports) - len(selected))
    items: list[EvidenceItem] = []
    report_ids: list[str] = []
    span_ids: set[str] = set()
    for rep in selected:
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
    return items, report_ids, sorted(span_ids), omitted


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
    paths: cfg.WikiPaths,
    request: QueryRequest,
    route: str,
    *,
    policy: curate_yml.CurationPolicy | None = None,
    limit: int = 8,
) -> EvidencePack:
    """Build an evidence pack for the given route (§28–§30).

    ``policy`` — the resolved CurationPolicy forwarded by the orchestrator
    (§28.1).  When None, defaults to open policy (no source filter, no
    workspace-specific constraints) for backward compatibility.
    """
    db_path = paths.state_db
    q = request.working_query
    warnings: list[str] = []
    pack = EvidencePack(route=route, warnings=warnings)

    # `seed_terms`' docstring has promised since v0.47.0 that "context_fetch
    # warns about it rather than quietly returning nothing" when a non-English
    # question reaches seeding. It never did — nothing in this module or in
    # `context_service` inspected `english_query` at all. A documented invariant
    # with no implementation is why ROADMAP A1 was misdiagnosed twice, so land
    # the warning the contract already advertises.
    #
    # Scoped to `unset`: a derived-but-empty query is a whole-corpus question,
    # which `intent` routes to `global`, and `global` does not seed entities —
    # warning there would fire on a path working exactly as designed, and a
    # warning that fires when nothing is wrong is one the user learns to skip.
    if request.english_query_status == "unset" and q and not seed_terms(q):
        warnings.append(
            "english_query was not derived by the caller; internals received the "
            "raw question and English-only entity seeding matched nothing"
        )
    # §30.1: generate a unique retrieval execution ID for this call.
    pack.retrieval_execution_id = f"RTR-{uuid.uuid4().hex[:8]}"

    if route == "source-section":
        sid = _resolve_source_id(db_path, request.source_key)
        if sid is None:
            warnings.append(f"unknown source: {request.source_key}")
        else:
            spans = db.list_source_spans(db_path, sid)
            span_ids = [s["id"] for s in spans]
            pack.items.extend(_span_items(db_path, span_ids))
            pack.source_span_ids = span_ids
        _apply_policy_scope(db_path, pack, policy)
        return pack

    if route == "global":
        # §28.2: query-relevant bounded synthesis + community reports.
        syn_items, syn_ids, syn_spans = _synthesis_items(db_path, limit=_MAX_GLOBAL_SYNTHESIS)
        report_items, report_ids, report_spans, report_omitted = _report_items(
            db_path, query=q, limit=_MAX_GLOBAL_REPORTS
        )
        items = syn_items + report_items
        if not items:
            warnings.append("no synthesis or community reports; falling back to search")
            _add_search_hits(pack, paths, q, limit)
        else:
            pack.items = items
            pack.source_span_ids = sorted(set(syn_spans) | set(report_spans))
        if report_omitted:
            pack.omitted_counts["global_reports"] = report_omitted
        pack.synthesis_node_ids = syn_ids
        pack.community_report_ids = report_ids
        _apply_policy_scope(db_path, pack, policy)
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
        report_items, report_ids, report_spans, _ = _report_items(db_path, query=q, limit=3)
        pack.items.extend(syn_items)  # synthesis primer (highest-level)
        pack.items.extend(report_items)  # community primer (already bounded to 3)
        pack.items.extend(ent_items)
        pack.memory_path_ids = mpath_ids
        pack.synthesis_node_ids = syn_ids
        pack.community_report_ids = report_ids
        pack.source_span_ids = sorted(set(span_ids) | set(report_spans) | set(syn_spans))
        _apply_policy_scope(db_path, pack, policy)
        return pack

    # local: entities + their spans + search hits.
    ent_items, span_ids = _entity_evidence(db_path, q)
    pack.items.extend(ent_items)
    pack.items.extend(_span_items(db_path, span_ids))
    pack.source_span_ids = span_ids
    _add_search_hits(pack, paths, q, limit)
    _apply_policy_scope(db_path, pack, policy)
    return pack
