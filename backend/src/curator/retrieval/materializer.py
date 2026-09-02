"""Materialize authoritative DB records into the v0.3.2 search corpus."""

from __future__ import annotations

import logging

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .. import constants as consts
from .. import db

__all__ = ["MaterializeResult", "materialize_search_documents"]


from ..pipeline import source_spans

_LOG = logging.getLogger(__name__)


_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


@dataclass(frozen=True)
class MaterializeResult:
    documents: int
    chunks: int = 0
    embeddings: int = 0
    skipped_unchanged: int = 0
    failures: int = 0
    #: Spans whose full text could not be recovered, so the index holds their
    #: 200-char preview instead. Reported because a silent fallback rate would
    #: look exactly like a successful reindex while search stayed truncated.
    preview_fallbacks: int = 0


def _json_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _loads_list(raw: Any) -> list:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return value if isinstance(value, list) else []


def _language(text: str) -> str:
    return "ko" if _CJK_RE.search(text) else ""


def _first_source_id(span_ids: Iterable[str], span_source_ids: dict[str, int]) -> int | None:
    for span_id in span_ids:
        source_id = span_source_ids.get(span_id)
        if source_id is not None:
            return source_id
    return None


def _projection_path(record_type: str, row: dict[str, Any], source_contexts: dict[int, str]) -> str:
    if record_type == "source_span":
        context_id = source_contexts.get(int(row["source_id"]))
        return f"{consts.LAYER_L1}/{context_id}.md" if context_id else ""
    if record_type == "knowledge_unit":
        atom_id = row.get("atom_node_id") or ""
        return f"{consts.LAYER_L2}/{atom_id}.md" if atom_id else ""
    if record_type == "synthesis_node":
        return f"{consts.LAYER_L4}/{row['id']}.md"
    return ""


def _build_doc(
    *,
    record_type: str,
    record_id: str,
    title: str,
    body: str,
    source_id: int | None,
    projection_path: str = "",
    source_span_ids: list[str] | None = None,
    dependency_parts: Any = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = f"{title}\n{body}".strip()
    return {
        "doc_id": f"DOC-{record_type}-{record_id}",
        "record_type": record_type,
        "record_id": record_id,
        "source_id": source_id,
        "projection_path": projection_path,
        "title": title.strip(),
        "body": body.strip(),
        "language": _language(text),
        "content_hash": _json_hash({
            "record_type": record_type,
            "record_id": record_id,
            "title": title,
            "body": body,
        }),
        "dependency_hash": _json_hash(
            dependency_parts if dependency_parts is not None else {}
        ),
        "provenance_json": json.dumps({
            "record_type": record_type,
            "record_id": record_id,
            "source_span_ids": source_span_ids or [],
            **(provenance or {}),
        }),
    }


def _sync_docs(db_path: Path, docs: list[dict[str, Any]]) -> None:
    now = db._now_iso()
    with db.connect(db_path) as conn:
        if docs:
            conn.execute("CREATE TEMP TABLE current_search_docs(doc_id TEXT PRIMARY KEY)")
            conn.executemany(
                "INSERT INTO current_search_docs(doc_id) VALUES (?)",
                [(str(doc["doc_id"]),) for doc in docs],
            )
            conn.executemany(
                """
                INSERT INTO search_documents
                    (doc_id, record_type, record_id, source_id, projection_path, title,
                     body, language, content_hash, dependency_hash, provenance_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                    record_type = excluded.record_type,
                    record_id = excluded.record_id,
                    source_id = excluded.source_id,
                    projection_path = excluded.projection_path,
                    title = excluded.title,
                    body = excluded.body,
                    language = excluded.language,
                    content_hash = excluded.content_hash,
                    dependency_hash = excluded.dependency_hash,
                    provenance_json = excluded.provenance_json,
                    updated_at = excluded.updated_at
                """,
                [
                    (
                        doc["doc_id"],
                        doc["record_type"],
                        doc["record_id"],
                        doc["source_id"],
                        doc["projection_path"],
                        doc["title"],
                        doc["body"],
                        doc["language"],
                        doc["content_hash"],
                        doc["dependency_hash"],
                        doc["provenance_json"],
                        now,
                    )
                    for doc in docs
                ],
            )
            conn.execute(
                "DELETE FROM search_documents "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM current_search_docs c "
                "WHERE c.doc_id = search_documents.doc_id"
                ")"
            )
            conn.execute("DROP TABLE current_search_docs")
        else:
            conn.execute("DELETE FROM search_documents")

        conn.execute("DELETE FROM search_documents_fts")
        conn.execute("DELETE FROM search_documents_fts_tri")
        fts_rows = [
            (
                doc["title"],
                doc["body"],
                doc["record_type"],
                doc["record_id"],
                doc["doc_id"],
            )
            for doc in docs
        ]
        if fts_rows:
            for tbl in ("search_documents_fts", "search_documents_fts_tri"):
                conn.executemany(
                    f"INSERT INTO {tbl} (title, body, record_type, record_id, doc_id) "
                    "VALUES (?, ?, ?, ?, ?)",
                    fts_rows,
                )


def _current_embedding_count(db_path: Path) -> int:
    with db.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM search_embeddings e
            JOIN search_chunks c ON c.chunk_id = e.chunk_id
            WHERE e.status = 'ready'
              AND e.input_hash = c.input_hash
            """
        ).fetchone()
    return int(row[0] or 0)


def _hydrated_span_texts(db_path: Path, span_ids: list[str]) -> dict[str, str]:
    """Full span text, recovered by re-parsing the source and matching on hash.

    Lazily imported: `pipeline.compile` imports this module, so a module-level
    import is a cycle. `evidence.py` reaches the same function the same way.

    Never fatal. A vault whose sources have moved should still get an index built
    from previews rather than no index at all.
    """
    if not span_ids:
        return {}
    try:
        from ..pipeline.compile import hydrate_spans

        return hydrate_spans(db_path, span_ids)
    except Exception:  # noqa: BLE001 - degrade to previews, and say so
        _LOG.warning(
            "could not hydrate span text for the search index; "
            "falling back to 200-char previews",
            exc_info=True,
        )
        return {}


def materialize_search_documents(
    db_path: Path, search_config: dict | None = None
) -> MaterializeResult:
    """Rebuild ``search_documents``, both FTS tables, and ``search_chunks``.

    Documents are projected from the authoritative rows (P3), then chunked for the
    vector layer (P5). Embeddings are generated separately by ``embed_corpus`` so
    the model-free materialization step always succeeds; embedding count stays
    zero here and is filled by ``wiki reindex --embed`` / compile's embed pass.
    """
    with db.connect(db_path) as conn:
        sources = {
            int(row["id"]): dict(row)
            for row in conn.execute("SELECT * FROM sources ORDER BY id").fetchall()
        }
        source_contexts = {
            sid: str(row.get("context_id") or "")
            for sid, row in sources.items()
            if row.get("context_id")
        }
        spans = [
            dict(row)
            for row in conn.execute(
                "SELECT ss.* FROM source_spans ss "
                "JOIN sources s ON s.id = ss.source_id "
                "ORDER BY ss.source_id, ss.id"
            ).fetchall()
        ]
        # Serve only authoritative-generation units (SYSTEM_BEHAVIOR §26.3):
        # staged/discarded-generation rows are never materialized into search.
        #
        # `support_status` is deliberately NOT a filter here. It used to be
        # (`AND ku.support_status = 'verified'`), which made claim-support
        # validation an ADMISSION GATE on the search index: a unit that had not
        # been validated was not merely ranked lower, it was invisible to every
        # route, every ranker, and every reranker.
        #
        # Measured on a real 36-source vault: 1,701 of 2,799 live units (61%)
        # were excluded. Only 1,149 of those were formula-related at all; 552
        # had `formula_status='not_applicable'` and were simply never checked.
        # Validation of an `uncertain` claim needs a calibrated secondary
        # validator (`pipeline/claim_support.py`), and when none is configured
        # the unit stays `unchecked` forever — so a missing config silently
        # deleted most of the knowledge base from retrieval.
        #
        # This is the same defect shape as the v0.43.0 relation-corroboration
        # gate, and it takes the same fix: support becomes a RANKING and
        # LABELLING signal, not an admission gate. Unverified knowledge is
        # served, ranked below verified knowledge, and labelled so the reader
        # can see what it is.
        #
        # `failed` is the ONE exception and stays excluded. It does not mean
        # "lower confidence" — it means the support check RAN and found the
        # cited span does not support the claim, i.e. a detected hallucination.
        # `test_compile_source_l2_excludes_failed_claim_from_downstream` pins
        # that guard: such a unit writes no atom page and never feeds graph
        # extraction, so serving it in search would be the one place ungrounded
        # content leaked back in.
        #
        # Note 498 of the 584 `failed` units carry
        # `formula_status='preserved_in_text'` — the formula IS verifiably in
        # the cited span and only the prose-overlap bar failed them. Those are
        # false negatives, but the fix belongs at the support gate
        # (§26.1), not here: relaxing the index would also admit the 86 units
        # whose formula is genuinely `missing`.
        units = [
            dict(row)
            for row in conn.execute(
                "SELECT ku.* FROM knowledge_units ku "
                "JOIN compiler_generations g ON g.id = ku.generation_id "
                "JOIN sources s ON s.id = ku.source_id AND s.id = g.source_id "
                "WHERE ku.retired_at IS NULL "
                "AND ku.support_status <> 'failed' "
                "AND g.status = 'authoritative' "
                "ORDER BY ku.source_id, ku.id"
            ).fetchall()
        ]
        canonical_entities = [
            dict(row)
            for row in conn.execute(
                "SELECT e.* FROM graph_entities e "
                "WHERE e.resolution_state = 'canonical' "
                "ORDER BY e.id"
            ).fetchall()
        ]
        relations = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM graph_relations "
                "WHERE lifecycle_status = 'active' ORDER BY id"
            ).fetchall()
        ]
        all_relation_entity_ids = {
            str(value)
            for row in conn.execute(
                "SELECT source_entity_id, target_entity_id FROM graph_relations"
            ).fetchall()
            for value in (row["source_entity_id"], row["target_entity_id"])
        }
        reports = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM community_reports "
                "WHERE retired_at IS NULL ORDER BY id"
            ).fetchall()
        ]
        syntheses = [
            dict(row)
            for row in conn.execute("SELECT * FROM synthesis_nodes ORDER BY id").fetchall()
        ]

    span_source_ids = {str(row["id"]): int(row["source_id"]) for row in spans}
    live_span_ids = set(span_source_ids)
    live_unit_ids = {str(row["id"]) for row in units}
    active_entity_ids = {
        str(value)
        for row in relations
        for value in (row["source_entity_id"], row["target_entity_id"])
    }
    entities = [
        row
        for row in canonical_entities
        if str(row["id"]) in active_entity_ids
        or (
            str(row["entity_type"]) not in {"vault_note", "vault_asset", "tag"}
            and (
                bool(
                    live_span_ids.intersection(
                        str(value)
                        for value in _loads_list(row.get("source_span_ids"))
                    )
                )
                or bool(
                    live_unit_ids.intersection(
                        str(value)
                        for value in _loads_list(row.get("knowledge_unit_ids"))
                    )
                )
                or str(row["id"]) not in all_relation_entity_ids
            )
        )
    ]
    active_relation_ids = {str(row["id"]) for row in relations}
    reports = [
        row
        for row in reports
        if set(
            str(value) for value in _loads_list(row.get("relation_ids"))
        ).issubset(active_relation_ids)
        and set(
            str(value) for value in _loads_list(row.get("source_span_ids"))
        ).issubset(live_span_ids)
    ]
    live_report_ids = {str(row["id"]) for row in reports}
    syntheses = [
        row
        for row in syntheses
        if set(
            str(value)
            for value in _loads_list(row.get("community_report_ids"))
        ).issubset(live_report_ids)
        and set(
            str(value) for value in _loads_list(row.get("source_span_ids"))
        ).issubset(live_span_ids)
    ]
    entity_names = {str(row["id"]): str(row["canonical_name"]) for row in entities}
    docs: list[dict[str, Any]] = []

    # The index gets a truncated span's FULL text where the source can be read,
    # and says how often it could not.
    #
    # `source_spans` has no full-text column — only `content_hash`, computed over
    # the whole span, and `text_preview`, which is the first 200 characters
    # (`pipeline/source_spans.py:31`). Indexing the preview meant the searchable
    # body of a span WAS those 200 characters. Measured on a real vault: 4,865 of
    # 11,774 spans (41.3%) sit exactly at that cap, with a true median length of
    # 418 and a p90 of 1,426 — 118,733 characters invisible to search in a
    # 300-span sample alone.
    #
    # It is not only a recall problem. The primary hybrid-search path reads this
    # body straight back out (`engine.py:_hydrate`) and hands it to the model, so
    # a cut mid-word reached the answer. Only the entity/source-section route
    # re-hydrated (`evidence.py:297`).
    #
    # `text_preview` is left alone: SCHEMA.md locks it immutable, and rewriting it
    # would move `content_hash` and therefore span identity, which 20,230
    # knowledge_units and 19,521 claim_supports are anchored to.
    # ONLY the spans the preview actually truncated. A preview shorter than the
    # cap already holds the whole span, so hydrating it buys nothing and costs
    # twice:
    #
    #  - `hydrate_spans` re-parses the SOURCE FILE. `materialize_search_documents`
    #    is called about 2N+2 times per `wiki add`/`wiki sync` from six sites in
    #    the compile pipeline, including the error path and the cached no-op path,
    #    and its span query is vault-wide. Hydrating everything turned a cheap DB
    #    projection into repeated full-corpus PDF parsing.
    #  - `text_preview` collapses internal whitespace (`" ".join(text.split())`)
    #    and hydration does not, so the body of an untruncated span would change
    #    for whitespace alone — measured, 53% of them — and every one would
    #    re-embed for no gain, since embeddings are keyed on the text.
    #
    # Both were found by review. Restricting to the truncated set is what makes
    # the fix pay only for what it fixes.
    truncated = [
        str(row["id"])
        for row in spans
        if len(str(row.get("text_preview") or "")) >= source_spans._PREVIEW_CHARS
    ]
    truncated_ids = set(truncated)
    span_full_text = _hydrated_span_texts(db_path, truncated)
    preview_fallbacks = 0

    for row in spans:
        source_id = int(row["source_id"])
        title = str(row.get("section_title") or sources.get(source_id, {}).get("relpath") or "")
        span_id = str(row["id"])
        hydrated = span_full_text.get(span_id)
        if hydrated:
            body = hydrated
        elif span_id not in truncated_ids:
            # Never truncated, so its preview IS the whole span. Not a fallback,
            # and counting it as one would make the warning the user sees a lie:
            # on a healthy vault most spans land here.
            body = str(row.get("text_preview") or "")
        else:
            # The source moved or changed, so the text cannot be recovered. A
            # truncated body beats no body — but count it, because a silent 40%
            # fallback rate would look exactly like success.
            body = str(row.get("text_preview") or "")
            preview_fallbacks += 1
        docs.append(_build_doc(
            record_type="source_span",
            record_id=str(row["id"]),
            source_id=source_id,
            title=title,
            body=body,
            projection_path=_projection_path("source_span", row, source_contexts),
            source_span_ids=[str(row["id"])],
            dependency_parts={
                "content_hash": row.get("content_hash"),
                "relpath": row.get("relpath"),
                "start_char": row.get("start_char"),
                "end_char": row.get("end_char"),
            },
            provenance={
                "relpath": row.get("relpath"),
                "span_type": row.get("span_type"),
                "page_number": row.get("page_number"),
                "toc_id": row.get("toc_id"),
            },
        ))

    for row in units:
        span_ids = [str(v) for v in _loads_list(row.get("source_span_ids"))]
        docs.append(_build_doc(
            record_type="knowledge_unit",
            record_id=str(row["id"]),
            source_id=row.get("source_id"),
            title=str(row.get("canonical_name") or ""),
            body=str(row.get("statement") or ""),
            projection_path=_projection_path("knowledge_unit", row, source_contexts),
            source_span_ids=span_ids,
            dependency_parts={
                "source_span_ids": span_ids,
                "prompt_run_id": row.get("prompt_run_id"),
                "truth_status": row.get("truth_status"),
                # Re-materialize when support changes: the status now drives
                # ranking and the served label, so a stale copy would misreport
                # how well-grounded the claim is.
                "support_status": row.get("support_status"),
            },
            provenance={
                "unit_type": row.get("unit_type"),
                "truth_status": row.get("truth_status"),
                "confidence": row.get("confidence"),
                "support_status": row.get("support_status") or "unchecked",
                "formula_status": row.get("formula_status") or "",
            },
        ))

    for row in entities:
        span_ids = [str(v) for v in _loads_list(row.get("source_span_ids"))]
        docs.append(_build_doc(
            record_type="graph_entity",
            record_id=str(row["id"]),
            source_id=_first_source_id(span_ids, span_source_ids),
            title=str(row.get("canonical_name") or ""),
            body=str(row.get("description") or ""),
            source_span_ids=span_ids,
            dependency_parts={
                "source_span_ids": span_ids,
                "knowledge_unit_ids": _loads_list(row.get("knowledge_unit_ids")),
                "prompt_run_id": row.get("prompt_run_id"),
            },
            provenance={"entity_type": row.get("entity_type")},
        ))

    for row in relations:
        span_ids = [str(v) for v in _loads_list(row.get("source_span_ids"))]
        source_name = entity_names.get(str(row.get("source_entity_id")), str(row.get("source_entity_id") or ""))
        target_name = entity_names.get(str(row.get("target_entity_id")), str(row.get("target_entity_id") or ""))
        relation_type = str(row.get("relation_type") or "")
        description = str(row.get("description") or "")
        title = f"{source_name} {relation_type} {target_name}".strip()
        body = description or title
        docs.append(_build_doc(
            record_type="graph_relation",
            record_id=str(row["id"]),
            source_id=_first_source_id(span_ids, span_source_ids),
            title=title,
            body=body,
            source_span_ids=span_ids,
            dependency_parts={
                "source_entity_id": row.get("source_entity_id"),
                "target_entity_id": row.get("target_entity_id"),
                "source_span_ids": span_ids,
                "prompt_run_id": row.get("prompt_run_id"),
            },
            provenance={
                "relation_type": relation_type,
                "assertion_source": row.get("assertion_source"),
                "confidence": row.get("confidence"),
                "edge_class": row.get("edge_class"),
                "lifecycle_status": row.get("lifecycle_status"),
                "generation_id": row.get("generation_id"),
            },
        ))

    for row in reports:
        span_ids = [str(v) for v in _loads_list(row.get("source_span_ids"))]
        body = "\n\n".join(
            part for part in (str(row.get("summary") or ""), str(row.get("full_content") or "")) if part
        )
        docs.append(_build_doc(
            record_type="community_report",
            record_id=str(row["id"]),
            source_id=_first_source_id(span_ids, span_source_ids),
            title=str(row.get("title") or ""),
            body=body,
            source_span_ids=span_ids,
            dependency_parts={
                "dependency_hash": row.get("dependency_hash"),
                "entity_ids": _loads_list(row.get("entity_ids")),
                "relation_ids": _loads_list(row.get("relation_ids")),
            },
            provenance={
                "community_key": row.get("community_key"),
                "level": row.get("level"),
                "rank": row.get("rank"),
            },
        ))

    for row in syntheses:
        span_ids = [str(v) for v in _loads_list(row.get("source_span_ids"))]
        body = "\n\n".join(
            part for part in (str(row.get("statement") or ""), str(row.get("full_content") or "")) if part
        )
        docs.append(_build_doc(
            record_type="synthesis_node",
            record_id=str(row["id"]),
            source_id=_first_source_id(span_ids, span_source_ids),
            title=str(row.get("title") or ""),
            body=body,
            projection_path=_projection_path("synthesis_node", row, source_contexts),
            source_span_ids=span_ids,
            dependency_parts={
                "dependency_hash": row.get("dependency_hash"),
                "community_report_ids": _loads_list(row.get("community_report_ids")),
                "concept_ids": _loads_list(row.get("concept_ids")),
            },
            provenance={"confidence": row.get("confidence")},
        ))

    from . import embedding

    _sync_docs(db_path, docs)
    chunk_result = embedding.materialize_chunks(db_path, search_config or {})
    preserved_embeddings = _current_embedding_count(db_path)
    db.set_index_meta(db_path, "search_materialized_documents", str(len(docs)))
    db.set_index_meta(db_path, "search_materializer_version", "v0.3.2-p5")
    if preview_fallbacks:
        _LOG.warning(
            "search index: %d of %d spans could not be hydrated and were indexed "
            "from their 200-char preview",
            preview_fallbacks,
            len(spans),
        )

    return MaterializeResult(
        documents=len(docs),
        chunks=chunk_result.chunks,
        embeddings=preserved_embeddings,
        skipped_unchanged=preserved_embeddings,
        preview_fallbacks=preview_fallbacks,
    )
