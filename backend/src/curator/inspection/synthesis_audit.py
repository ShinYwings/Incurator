"""Read-only synthesis/report/answer audit payloads.

These helpers hydrate existing DB provenance into JSON-ready dictionaries. They
do not call an LLM and do not mutate state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import db


def _loads_list(raw: Any) -> list:
    if isinstance(raw, list):
        return raw
    if raw is None:
        return []
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _loads_obj(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if raw is None:
        return {}
    try:
        parsed = json.loads(str(raw))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _ordered(rows: list[dict], ids: list[str], key: str = "id") -> list[dict]:
    rank = {value: i for i, value in enumerate(ids)}
    return sorted(rows, key=lambda row: rank.get(str(row.get(key)), len(rank)))


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _get_rows(db_path: Path, table: str, column: str, ids: list[str]) -> list[dict]:
    ids = _dedupe(ids)
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    with db.connect(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM {table} WHERE {column} IN ({placeholders})",
            tuple(ids),
        ).fetchall()
        return _ordered([dict(row) for row in rows], ids, column)


def _decode_source_span(row: dict) -> dict:
    data = dict(row)
    data["metadata"] = _loads_obj(data.get("metadata"))
    return data


def _decode_knowledge_unit(row: dict) -> dict:
    data = dict(row)
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    return data


def _decode_entity(row: dict) -> dict:
    data = dict(row)
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    data["knowledge_unit_ids"] = _loads_list(data.get("knowledge_unit_ids"))
    return data


def _decode_relation(row: dict) -> dict:
    data = dict(row)
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    return data


def _decode_report(row: dict) -> dict:
    data = dict(row)
    data["findings"] = _loads_list(data.pop("finding_json", "[]"))
    data["entity_ids"] = _loads_list(data.get("entity_ids"))
    data["relation_ids"] = _loads_list(data.get("relation_ids"))
    data["source_span_ids"] = _loads_list(data.get("source_span_ids"))
    return data


def _decode_prompt(row: dict) -> dict:
    return {
        "traceId": row["trace_id"],
        "promptId": row["prompt_id"],
        "promptVersion": row["prompt_version"],
        "family": row["family"],
        "role": row.get("role") or "",
        "validatorStatus": row.get("validator_status") or "pending",
        "validatorErrors": _loads_list(row.get("validator_errors")),
        "modelProvider": row.get("model_provider") or "",
        "modelName": row.get("model_name") or "",
        "inputHash": row.get("input_hash") or "",
        "outputHash": row.get("output_hash") or "",
        "queryTraceId": row.get("query_trace_id"),
        "latencyMs": row.get("latency_ms"),
        "createdAt": row.get("created_at"),
        "finishedAt": row.get("finished_at"),
    }


def _format_query_trace(row: dict) -> dict:
    return {
        "traceId": row["trace_id"],
        "workspaceId": row.get("workspace_id") or "default",
        "route": row.get("route") or "",
        "routeReason": row.get("route_reason") or "",
        "evidence": row.get("evidence") or [],
        "sourceSpanIds": row.get("source_span_ids") or [],
        "communityReportIds": row.get("community_report_ids") or [],
        "synthesisNodeIds": row.get("synthesis_node_ids") or [],
        "memoryPathIds": row.get("memory_path_ids") or [],
        "promptTraceIds": row.get("prompt_trace_ids") or [],
        "insightCandidateIds": row.get("insight_candidate_ids") or [],
        "retrievalTrace": row.get("retrieval_trace") or {},
        "warnings": row.get("warnings") or [],
        "latencyMs": row.get("latency_ms"),
        "createdAt": row.get("created_at"),
    }


def _collect_knowledge_units(
    db_path: Path,
    *,
    source_span_ids: list[str],
    knowledge_unit_ids: list[str],
) -> list[dict]:
    rows: list[dict] = []
    with db.connect(db_path) as conn:
        if knowledge_unit_ids:
            placeholders = ",".join("?" for _ in knowledge_unit_ids)
            rows.extend(
                dict(row)
                for row in conn.execute(
                    f"SELECT * FROM knowledge_units WHERE id IN ({placeholders})",
                    tuple(knowledge_unit_ids),
                ).fetchall()
            )
        all_units = conn.execute("SELECT * FROM knowledge_units").fetchall()
    span_set = set(source_span_ids)
    known = {str(row["id"]) for row in rows}
    for row in all_units:
        data = dict(row)
        if data["id"] in known:
            continue
        if span_set.intersection(_loads_list(data.get("source_span_ids"))):
            rows.append(data)
            known.add(str(data["id"]))
    decoded = [_decode_knowledge_unit(row) for row in rows]
    ordered_ids = [*knowledge_unit_ids, *[row["id"] for row in decoded]]
    return _ordered(decoded, _dedupe(ordered_ids))


def _current_dependency_hash(db_path: Path, depends_on_type: str, depends_on_id: str) -> str | None:
    table_column = {
        "source_span": ("source_spans", "id", "content_hash"),
        "community_report": ("community_reports", "id", "dependency_hash"),
        "synthesis_node": ("synthesis_nodes", "id", "dependency_hash"),
    }.get(depends_on_type)
    if table_column is None:
        return None
    table, column, hash_column = table_column
    with db.connect(db_path) as conn:
        row = conn.execute(
            f"SELECT {hash_column} FROM {table} WHERE {column} = ?",
            (depends_on_id,),
        ).fetchone()
    return str(row[hash_column]) if row else None


def _dependency_warnings(db_path: Path, artifact_id: str) -> list[str]:
    warnings: list[str] = []
    with db.connect(db_path) as conn:
        deps = conn.execute(
            "SELECT * FROM artifact_dependencies WHERE artifact_id = ? ORDER BY created_at",
            (artifact_id,),
        ).fetchall()
    for dep in deps:
        row = dict(dep)
        current = _current_dependency_hash(
            db_path,
            str(row["depends_on_type"]),
            str(row["depends_on_id"]),
        )
        if current is None:
            warnings.append(
                f"missing dependency: {row['depends_on_type']} {row['depends_on_id']}"
            )
        elif current != row["dependency_hash"]:
            warnings.append(
                f"stale dependency: {row['artifact_id']} depends on "
                f"{row['depends_on_id']} hash {row['dependency_hash']} != {current}"
            )
    return warnings


def _base_payload(kind: str, item_id: str) -> dict:
    return {
        "ok": True,
        "kind": kind,
        "id": item_id,
        "community_reports": [],
        "entities": [],
        "relations": [],
        "knowledge_units": [],
        "source_spans": [],
        "prompt_runs": [],
        "query_trace": None,
        "dependency_warnings": [],
        "warnings": [],
    }


def _hydrate(
    db_path: Path,
    payload: dict,
    *,
    synthesis: dict | None = None,
    report_ids: list[str] | None = None,
    source_span_ids: list[str] | None = None,
    prompt_trace_ids: list[str] | None = None,
) -> dict:
    warnings: list[str] = payload["warnings"]
    dependency_warnings: list[str] = payload["dependency_warnings"]

    reports: list[dict] = []
    wanted_report_ids = _dedupe([
        *(report_ids or []),
        *(_loads_list(synthesis.get("community_report_ids")) if synthesis else []),
    ])
    for report_id in wanted_report_ids:
        report = db.get_community_report(db_path, report_id)
        if report is None:
            warnings.append(f"missing community report: {report_id}")
        else:
            reports.append(report)
            dependency_warnings.extend(_dependency_warnings(db_path, report_id))
    payload["community_reports"] = reports

    entity_ids = _dedupe([eid for report in reports for eid in report.get("entity_ids", [])])
    relation_ids = _dedupe([rid for report in reports for rid in report.get("relation_ids", [])])
    entity_rows = [_decode_entity(row) for row in _get_rows(db_path, "graph_entities", "id", entity_ids)]
    relation_rows = [_decode_relation(row) for row in _get_rows(db_path, "graph_relations", "id", relation_ids)]
    payload["entities"] = entity_rows
    payload["relations"] = relation_rows

    found_entities = {row["id"] for row in entity_rows}
    for missing in sorted(set(entity_ids) - found_entities):
        warnings.append(f"missing graph entity: {missing}")
    found_relations = {row["id"] for row in relation_rows}
    for missing in sorted(set(relation_ids) - found_relations):
        warnings.append(f"missing graph relation: {missing}")
    for relation in relation_rows:
        for endpoint in (relation.get("source_entity_id"), relation.get("target_entity_id")):
            if endpoint and endpoint not in found_entities:
                warnings.append(f"unresolved graph endpoint: {endpoint}")

    span_ids = _dedupe([
        *(source_span_ids or []),
        *(_loads_list(synthesis.get("source_span_ids")) if synthesis else []),
        *[span for report in reports for span in report.get("source_span_ids", [])],
        *[span for entity in entity_rows for span in entity.get("source_span_ids", [])],
        *[span for relation in relation_rows for span in relation.get("source_span_ids", [])],
    ])
    span_rows = [_decode_source_span(row) for row in _get_rows(db_path, "source_spans", "id", span_ids)]
    payload["source_spans"] = span_rows
    found_spans = {row["id"] for row in span_rows}
    for missing in sorted(set(span_ids) - found_spans):
        warnings.append(f"missing source span: {missing}")

    unit_ids = _dedupe([unit for entity in entity_rows for unit in entity.get("knowledge_unit_ids", [])])
    unit_rows = _collect_knowledge_units(db_path, source_span_ids=span_ids, knowledge_unit_ids=unit_ids)
    payload["knowledge_units"] = unit_rows

    prompt_ids = _dedupe([
        *(prompt_trace_ids or []),
        *([synthesis.get("prompt_run_id")] if synthesis and synthesis.get("prompt_run_id") else []),
        *[report.get("prompt_run_id") for report in reports if report.get("prompt_run_id")],
        *[unit.get("prompt_run_id") for unit in unit_rows if unit.get("prompt_run_id")],
    ])
    prompt_rows: list[dict] = []
    for prompt_id in prompt_ids:
        row = db.get_prompt_run(db_path, prompt_id)
        if row is None:
            warnings.append(f"missing prompt trace: {prompt_id}")
        else:
            prompt_rows.append(_decode_prompt(row))
    payload["prompt_runs"] = prompt_rows

    if synthesis:
        dependency_warnings.extend(_dependency_warnings(db_path, synthesis["id"]))
    if not span_rows:
        warnings.append("weak grounding: no source spans resolved")
    return payload


def _format_synthesis(node: dict) -> dict:
    return {
        "id": node["id"],
        "title": node["title"],
        "statement": node["statement"],
        "full_content": node.get("full_content") or "",
        "confidence": node.get("confidence") or 0.0,
        "community_report_ids": node.get("community_report_ids") or [],
        "concept_ids": node.get("concept_ids") or [],
        "source_span_ids": node.get("source_span_ids") or [],
        "prompt_run_id": node.get("prompt_run_id"),
        "dependency_hash": node.get("dependency_hash") or "",
        "created_at": node.get("created_at"),
        "updated_at": node.get("updated_at"),
    }


def list_synthesis_summaries(db_path: Path, *, limit: int = 50) -> list[dict]:
    return [
        {
            "id": row["id"],
            "title": row["title"],
            "confidence": row["confidence"],
            "sourceSpanIds": row.get("source_span_ids") or [],
            "communityReportIds": row.get("community_report_ids") or [],
            "promptRunId": row.get("prompt_run_id"),
            "updatedAt": row.get("updated_at") or row.get("created_at"),
        }
        for row in db.list_synthesis_nodes(db_path)[:limit]
    ]


def build_synthesis_audit(db_path: Path, synthesis_id: str) -> dict:
    node = db.get_synthesis_node(db_path, synthesis_id)
    if node is None:
        return {"ok": False, "kind": "synthesis", "id": synthesis_id, "error": f"unknown synthesis: {synthesis_id}"}
    synthesis = _format_synthesis(node)
    payload = _base_payload("synthesis", synthesis_id)
    payload["synthesis"] = synthesis
    return _hydrate(db_path, payload, synthesis=synthesis)


def build_report_audit(db_path: Path, report_id: str) -> dict:
    report = db.get_community_report(db_path, report_id)
    if report is None:
        return {"ok": False, "kind": "report", "id": report_id, "error": f"unknown report: {report_id}"}
    payload = _base_payload("report", report_id)
    return _hydrate(
        db_path,
        payload,
        report_ids=[report_id],
        source_span_ids=report.get("source_span_ids", []),
        prompt_trace_ids=[report["prompt_run_id"]] if report.get("prompt_run_id") else [],
    )


def build_answer_audit(db_path: Path, trace_id: str) -> dict:
    trace = db.get_query_trace(db_path, trace_id)
    if trace is None:
        return {"ok": False, "kind": "answer", "id": trace_id, "error": f"unknown answer trace: {trace_id}"}
    payload = _base_payload("answer", trace_id)
    payload["query_trace"] = _format_query_trace(trace)
    payload["warnings"] = list(trace.get("warnings") or [])
    synthesis_ids = trace.get("synthesis_node_ids") or []
    synthesis = None
    if synthesis_ids:
        node = db.get_synthesis_node(db_path, synthesis_ids[0])
        if node is None:
            payload["warnings"].append(f"missing synthesis node: {synthesis_ids[0]}")
        else:
            synthesis = _format_synthesis(node)
            payload["synthesis"] = synthesis
    return _hydrate(
        db_path,
        payload,
        synthesis=synthesis,
        report_ids=trace.get("community_report_ids") or [],
        source_span_ids=trace.get("source_span_ids") or [],
        prompt_trace_ids=trace.get("prompt_trace_ids") or [],
    )
