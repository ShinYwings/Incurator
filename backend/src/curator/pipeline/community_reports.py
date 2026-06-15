"""Community detection + GraphRAG-style report generation (L3).

Community detection is deterministic (connected components over
``graph_relations``, NO LLM). Report writing uses the registered
``curator.community_report_write`` contract. Reports are stored in the
``community_reports`` DB table with a ``dependency_hash`` of their inputs so
staleness is detectable.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import db, prompting

__all__ = [
    "CommunityPlan",
    "detect_communities",
    "generate_community_report",
    "generate_report_prose",
]


@dataclass
class CommunityPlan:
    community_key: str
    entity_ids: list[str] = field(default_factory=list)
    relation_ids: list[str] = field(default_factory=list)


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def _community_key(entity_ids: list[str]) -> str:
    digest = hashlib.sha256("|".join(sorted(entity_ids)).encode("utf-8")).hexdigest()
    return f"comm-{digest[:12]}"


def detect_communities(db_path: Path) -> list[CommunityPlan]:
    """Group entities into communities by connected components over relations.

    Entities with no relations are not assigned a community (a single isolated
    node yields no useful global report). A later version may use Leiden.
    """
    with db.connect(db_path) as conn:
        rels = conn.execute(
            "SELECT id, source_entity_id, target_entity_id FROM graph_relations"
        ).fetchall()

    uf = _UnionFind()
    rel_by_pair: dict[str, list[str]] = {}
    for rel in rels:
        a, b = rel["source_entity_id"], rel["target_entity_id"]
        uf.union(a, b)
        rel_by_pair.setdefault(uf.find(a), [])  # ensure key exists later

    # Group entities and relations by component root.
    comp_entities: dict[str, set[str]] = {}
    comp_relations: dict[str, list[str]] = {}
    for rel in rels:
        root = uf.find(rel["source_entity_id"])
        comp_entities.setdefault(root, set()).update(
            (rel["source_entity_id"], rel["target_entity_id"])
        )
        comp_relations.setdefault(root, []).append(rel["id"])

    plans: list[CommunityPlan] = []
    for root, entities in comp_entities.items():
        entity_ids = sorted(entities)
        plans.append(
            CommunityPlan(
                community_key=_community_key(entity_ids),
                entity_ids=entity_ids,
                relation_ids=sorted(comp_relations.get(root, [])),
            )
        )
    plans.sort(key=lambda p: p.community_key)
    return plans


def _dependency_hash(entities: list[dict], relations: list[dict]) -> str:
    """Content-addressed hash of the report's inputs.

    Hashes the actual depended-on content (not timestamps) so the report is
    marked stale whenever an input entity/relation's content changes, regardless
    of timestamp resolution.
    """
    payload = json.dumps(
        {
            "entities": [
                (
                    e["id"],
                    e.get("canonical_name", ""),
                    e.get("entity_type", ""),
                    e.get("description", ""),
                    e.get("source_span_ids") or [],
                )
                for e in entities
            ],
            "relations": [
                (
                    r["id"],
                    r.get("relation_type", ""),
                    r.get("description", ""),
                    r.get("confidence", 0.0),
                    r.get("source_span_ids") or [],
                )
                for r in relations
            ],
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _entities_block(entities: list[dict]) -> str:
    return "\n".join(
        f'{e["id"]} ({e.get("entity_type","")}): {e.get("canonical_name","")} — {e.get("description","")}'
        for e in entities
    )


def _relations_block(db_path: Path, relation_ids: list[str]) -> tuple[str, list[dict]]:
    if not relation_ids:
        return "", []
    with db.connect(db_path) as conn:
        placeholders = ",".join("?" for _ in relation_ids)
        rows = conn.execute(
            f"SELECT * FROM graph_relations WHERE id IN ({placeholders})",
            tuple(relation_ids),
        ).fetchall()
    rels = [dict(r) for r in rows]
    block = "\n".join(
        f'{r["source_entity_id"]} --{r["relation_type"]}--> {r["target_entity_id"]} '
        f'(conf {r["confidence"]}): {r.get("description","")}'
        for r in rels
    )
    return block, rels


def generate_community_report(
    db_path: Path,
    client: Any,
    plan: CommunityPlan,
    *,
    curate_spec_hash: str = "",
) -> str | None:
    """Generate and store one community report. Returns the REP- id or None."""
    entities = [
        e for e in (db.get_graph_entity(db_path, eid) for eid in plan.entity_ids) if e
    ]
    if not entities:
        return None
    rel_block, rels = _relations_block(db_path, plan.relation_ids)
    span_ids = sorted(
        {sid for e in entities for sid in (e.get("source_span_ids") or [])}
        | {sid for r in rels for sid in (r.get("source_span_ids") or [])}
    )

    contract = prompting.REGISTRY.get("curator.community_report_write")
    input_obj = contract.input_model(
        community_title=f"Community {plan.community_key}",
        entities_block=_entities_block(entities),
        relations_block=rel_block,
        valid_span_ids_block="\n".join(span_ids),
    )
    result = prompting.run_prompt(
        db_path,
        client,
        contract,
        input_obj,
        validation_context={"valid_span_ids": set(span_ids)},
        source_span_ids=span_ids,
        curate_spec_hash=curate_spec_hash,
    )
    if not (result.ok and result.parsed is not None):
        error_msg = "; ".join(result.validation.errors) if hasattr(result, "validation") and result.validation else "Unknown LLM error"
        raise RuntimeError(f"Community report generation failed: {error_msg}")

    parsed = result.parsed
    findings = [f.model_dump() for f in getattr(parsed, "findings", [])]
    return db.upsert_community_report(
        db_path,
        community_key=plan.community_key,
        title=getattr(parsed, "title", ""),
        summary=getattr(parsed, "summary", ""),
        full_content=getattr(parsed, "full_content", ""),
        dependency_hash=_dependency_hash(entities, rels),
        findings=findings,
        entity_ids=plan.entity_ids,
        relation_ids=plan.relation_ids,
        source_span_ids=getattr(parsed, "source_span_ids", []) or span_ids,
        rank=float(getattr(parsed, "rank", 0.0) or 0.0),
        prompt_run_id=result.trace_id,
    )


def generate_report_prose(
    db_path: Path,
    client: Any,
    report: dict,
    *,
    curate_spec_hash: str = "",
) -> str | None:
    """Fill a claim-grounded report SKELETON with LLM prose (SYSTEM_BEHAVIOR §27.5).

    The deterministic ``db.rebuild_graph_generation`` already built the report's
    IDENTITY and GROUNDING (``community_key``, ``entity_ids``, the EXACT ``active``
    ``relation_ids``, the eligible-support ``source_span_ids``, and every identity/
    dependency hash). This pass only adds the human-readable prose, merge-upserted
    by ``community_key`` so the structural/grounding columns are PRESERVED (every
    omitted column defaults to *preserve existing* in ``upsert_community_report``).
    The report cites ONLY its active relations' eligible claim spans — there is no
    whole-community-span fallback (§27.5, F9). Returns the ``REP-`` id, or ``None``
    when the community has no resolvable entity."""
    entity_ids = report.get("entity_ids") or []
    relation_ids = report.get("relation_ids") or []
    entities = [
        e for e in (db.get_graph_entity(db_path, eid) for eid in entity_ids) if e
    ]
    if not entities:
        return None
    rel_block, _rels = _relations_block(db_path, relation_ids)
    # Ground prose strictly in the report's claim-grounded span closure (computed by
    # rebuild_graph_generation from the active verified support), never a broad set.
    span_ids = list(report.get("source_span_ids") or [])

    contract = prompting.REGISTRY.get("curator.community_report_write")
    input_obj = contract.input_model(
        community_title=f"Community {report['community_key']}",
        entities_block=_entities_block(entities),
        relations_block=rel_block,
        valid_span_ids_block="\n".join(span_ids),
    )
    result = prompting.run_prompt(
        db_path,
        client,
        contract,
        input_obj,
        validation_context={"valid_span_ids": set(span_ids)},
        source_span_ids=span_ids,
        curate_spec_hash=curate_spec_hash,
    )
    if not (result.ok and result.parsed is not None):
        error_msg = (
            "; ".join(result.validation.errors)
            if hasattr(result, "validation") and result.validation
            else "Unknown LLM error"
        )
        raise RuntimeError(f"Community report prose generation failed: {error_msg}")

    parsed = result.parsed
    findings = [f.model_dump() for f in getattr(parsed, "findings", [])]
    return db.upsert_community_report(
        db_path,
        community_key=report["community_key"],
        title=getattr(parsed, "title", ""),
        summary=getattr(parsed, "summary", ""),
        full_content=getattr(parsed, "full_content", ""),
        findings=findings,
        rank=float(getattr(parsed, "rank", 0.0) or 0.0),
        prompt_run_id=result.trace_id,
    )
