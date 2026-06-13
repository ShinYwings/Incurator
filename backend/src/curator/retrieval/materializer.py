"""Materialize authoritative DB records into the v0.3.2 search corpus."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .. import constants as consts
from .. import db

__all__ = ["MaterializeResult", "materialize_search_documents"]


_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


@dataclass(frozen=True)
class MaterializeResult:
    documents: int
    chunks: int = 0
    embeddings: int = 0
    skipped_unchanged: int = 0
    failures: int = 0


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


def _upsert_doc(
    db_path: Path,
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
) -> None:
    text = f"{title}\n{body}".strip()
    db.upsert_search_document(
        db_path,
        record_type=record_type,
        record_id=record_id,
        source_id=source_id,
        projection_path=projection_path,
        title=title.strip(),
        body=body.strip(),
        language=_language(text),
        content_hash=_json_hash({"record_type": record_type, "record_id": record_id, "title": title, "body": body}),
        dependency_hash=_json_hash(dependency_parts if dependency_parts is not None else {}),
        provenance={
            "record_type": record_type,
            "record_id": record_id,
            "source_span_ids": source_span_ids or [],
            **(provenance or {}),
        },
    )


def materialize_search_documents(
    db_path: Path, search_config: dict | None = None
) -> MaterializeResult:
    """Rebuild ``search_documents``, both FTS tables, and ``search_chunks``.

    Documents are projected from the authoritative rows (P3), then chunked for the
    vector layer (P5). Embeddings are generated separately by ``embed_corpus`` so
    the model-free materialization step always succeeds; embedding count stays
    zero here and is filled by ``wiki reindex --embed`` / compile's embed pass.
    """
    db.clear_search_corpus(db_path)
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
                "SELECT * FROM source_spans ORDER BY source_id, id"
            ).fetchall()
        ]
        # Serve only authoritative-generation units (SYSTEM_BEHAVIOR §26.3):
        # staged/discarded-generation rows are never materialized into search.
        units = [
            dict(row)
            for row in conn.execute(
                "SELECT ku.* FROM knowledge_units ku "
                "JOIN compiler_generations g ON g.id = ku.generation_id "
                "WHERE ku.retired_at IS NULL AND ku.support_status = 'verified' "
                "AND g.status = 'authoritative' "
                "ORDER BY ku.source_id, ku.id"
            ).fetchall()
        ]
        entities = [
            dict(row)
            for row in conn.execute("SELECT * FROM graph_entities ORDER BY id").fetchall()
        ]
        relations = [
            dict(row)
            for row in conn.execute("SELECT * FROM graph_relations ORDER BY id").fetchall()
        ]
        reports = [
            dict(row)
            for row in conn.execute("SELECT * FROM community_reports ORDER BY id").fetchall()
        ]
        syntheses = [
            dict(row)
            for row in conn.execute("SELECT * FROM synthesis_nodes ORDER BY id").fetchall()
        ]

    span_source_ids = {str(row["id"]): int(row["source_id"]) for row in spans}
    entity_names = {str(row["id"]): str(row["canonical_name"]) for row in entities}
    count = 0

    for row in spans:
        source_id = int(row["source_id"])
        title = str(row.get("section_title") or sources.get(source_id, {}).get("relpath") or "")
        body = str(row.get("text_preview") or "")
        _upsert_doc(
            db_path,
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
        )
        count += 1

    for row in units:
        span_ids = [str(v) for v in _loads_list(row.get("source_span_ids"))]
        _upsert_doc(
            db_path,
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
            },
            provenance={
                "unit_type": row.get("unit_type"),
                "truth_status": row.get("truth_status"),
                "confidence": row.get("confidence"),
            },
        )
        count += 1

    for row in entities:
        span_ids = [str(v) for v in _loads_list(row.get("source_span_ids"))]
        _upsert_doc(
            db_path,
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
        )
        count += 1

    for row in relations:
        span_ids = [str(v) for v in _loads_list(row.get("source_span_ids"))]
        source_name = entity_names.get(str(row.get("source_entity_id")), str(row.get("source_entity_id") or ""))
        target_name = entity_names.get(str(row.get("target_entity_id")), str(row.get("target_entity_id") or ""))
        relation_type = str(row.get("relation_type") or "")
        description = str(row.get("description") or "")
        title = f"{source_name} {relation_type} {target_name}".strip()
        body = description or title
        _upsert_doc(
            db_path,
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
            },
        )
        count += 1

    for row in reports:
        span_ids = [str(v) for v in _loads_list(row.get("source_span_ids"))]
        body = "\n\n".join(
            part for part in (str(row.get("summary") or ""), str(row.get("full_content") or "")) if part
        )
        _upsert_doc(
            db_path,
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
        )
        count += 1

    for row in syntheses:
        span_ids = [str(v) for v in _loads_list(row.get("source_span_ids"))]
        body = "\n\n".join(
            part for part in (str(row.get("statement") or ""), str(row.get("full_content") or "")) if part
        )
        _upsert_doc(
            db_path,
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
        )
        count += 1

    from . import embedding

    chunk_result = embedding.materialize_chunks(db_path, search_config or {})
    db.set_index_meta(db_path, "search_materialized_documents", str(count))
    db.set_index_meta(db_path, "search_materializer_version", "v0.3.2-p5")
    return MaterializeResult(documents=count, chunks=chunk_result.chunks)
