"""Shared L4 Synthesis layer (corpus-wide cross-cutting insights).

The synthesis layer is the durable, workspace-INDEPENDENT top of the refined DAG:
it distills the community reports (L3) into a small set of cross-cutting,
source-grounded synthesized insights — like the "synthesis" tier in other LLM
wiki repos (Zettelkasten permanent/synthesis notes, RAPTOR roll-ups). It is NOT a
per-workspace artifact; the dynamic Curation lens sits ABOVE this layer and
selects/recombines synthesis nodes per workspace/query (never stored).

Synthesis is generated wholesale from all community reports and is content-
addressed by a corpus ``dependency_hash`` so it is skipped when nothing changed.
Synthesis nodes are stored in the ``synthesis_nodes`` DB table (authoritative) and
projected to ``.curator/Collections/04_Synthesis/SYN-*.md`` as disposable
corpus.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

import yaml

from .. import config as cfg
from .. import constants as consts
from .. import db, prompting
from . import projection

__all__ = ["corpus_dependency_hash", "generate_synthesis", "reemit_synthesis"]


#: Separator between the corpus hash and the layer's node count. `#` cannot occur
#: in a hex digest, so a stored value either carries a cardinality or is legacy.
_LAYER_CARDINALITY_SEP = "#"


def layer_dependency_hash(dep_hash: str, node_count: int) -> str:
    """The value stored in ``synthesis_nodes.dependency_hash``.

    The corpus hash alone cannot distinguish a complete layer from a truncated
    one. `generate_synthesis` regenerates wholesale — clear, then write N nodes each
    stamped with the current hash — so a crash between the clear and the last
    write leaves a partial layer whose every surviving node carries the *current*
    hash. The idempotency guard then reads it as complete and no later build ever
    regenerates the missing nodes.

    Recording the intended cardinality alongside the hash makes that state
    detectable with no schema change (this codebase has no `ALTER TABLE` path, so
    a new column could not reach an existing vault). The value stays opaque and
    compared only for equality.
    """
    return f"{dep_hash}{_LAYER_CARDINALITY_SEP}{node_count}"


def layer_is_current(nodes: "list[dict]", dep_hash: str) -> bool:
    """True when the stored layer is complete AND built from this corpus.

    False for a truncated layer, a layer built from a different corpus, and for
    legacy rows that carry a bare hash with no cardinality — the last of those
    reads as unknown rather than current, which is how a vault frozen by the old
    behavior repairs itself on the next build.
    """
    if not nodes:
        return False
    expected = layer_dependency_hash(dep_hash, len(nodes))
    return all(n.get("dependency_hash") == expected for n in nodes)


def corpus_dependency_hash(reports: list[dict]) -> str:
    """Content-addressed hash of all community reports feeding the synthesis layer.

    Hashes the depended-on report content (not timestamps) so the synthesis layer
    is marked stale whenever any report's content changes.
    """
    payload = json.dumps(
        [
            (
                r["id"],
                r.get("title", ""),
                r.get("summary", ""),
                r.get("full_content", ""),
                r.get("dependency_hash", ""),
                r.get("source_span_ids") or [],
            )
            for r in sorted(reports, key=lambda x: x["id"])
        ],
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _reports_block(reports: list[dict]) -> str:
    return "\n\n".join(
        f'[{r["id"]}] {r.get("title","")}\n{r.get("summary","")}\n{r.get("full_content","")}'.strip()
        for r in reports
    )


def _concept_ids_for_reports(
    paths: cfg.WikiPaths,
    report_ids: list[str],
    concept_ids_by_report: dict[str, str] | None = None,
) -> list[str]:
    mapping = dict(concept_ids_by_report or {})
    missing = set(report_ids) - set(mapping)
    if missing:
        for path in sorted(paths.concepts.glob(f"{consts.PREFIX_L3}-*.md")):
            try:
                page = yaml.safe_load(
                    path.read_text(encoding="utf-8").split("---", 2)[1]
                )
            except Exception:
                continue
            if not isinstance(page, dict):
                continue
            report_id = str(page.get("community_report_id") or "")
            concept_id = str(page.get("id") or path.stem)
            if report_id in missing and concept_id.startswith(f"{consts.PREFIX_L3}-"):
                mapping[report_id] = concept_id
    return sorted({mapping[rid] for rid in report_ids if mapping.get(rid)})


def generate_synthesis(
    paths: cfg.WikiPaths,
    client: Any,
    *,
    curate_spec_hash: str = "",
    max_syntheses: int = 6,
    concept_ids_by_report: dict[str, str] | None = None,
) -> list[str]:
    """Generate the shared synthesis layer from all community reports.

    Returns the list of SYN node ids. Skips (returns existing ids) when the corpus
    dependency hash is unchanged, so re-running without DAG changes costs no LLM.
    Source truth is never touched; every synthesis cites only allowed span ids.
    """
    reports = db.list_community_reports(paths.state_db)
    if not reports:
        if db.list_synthesis_nodes(paths.state_db):
            db.clear_synthesis_nodes(paths.state_db)
        reemit_synthesis(paths)
        return []

    dep_hash = corpus_dependency_hash(reports)
    report_ids = [r["id"] for r in reports]
    concept_ids = _concept_ids_for_reports(paths, report_ids, concept_ids_by_report)

    existing = db.list_synthesis_nodes(paths.state_db)
    if layer_is_current(existing, dep_hash):
        if any(list(n.get("concept_ids") or []) != concept_ids for n in existing):
            with db.connect(paths.state_db) as conn:
                conn.execute(
                    "UPDATE synthesis_nodes SET concept_ids = ?, updated_at = ?",
                    (json.dumps(concept_ids), db._now_iso()),
                )
            reemit_synthesis(paths)
        return [n["id"] for n in existing]

    span_ids = sorted({sid for r in reports for sid in (r.get("source_span_ids") or [])})

    contract = prompting.REGISTRY.get("curator.synthesis_write")
    input_obj = contract.input_model(
        reports_block=_reports_block(reports),
        valid_span_ids_block="\n".join(span_ids),
        max_syntheses=max_syntheses,
    )
    result = prompting.run_prompt(
        paths.state_db,
        client,
        contract,
        input_obj,
        validation_context={"valid_span_ids": set(span_ids)},
        source_span_ids=span_ids,
        curate_spec_hash=curate_spec_hash,
    )
    if not (result.ok and result.parsed is not None):
        errs = "; ".join(result.validation.errors) if getattr(result, "validation", None) else "Unknown LLM error"
        raise RuntimeError(f"Synthesis generation failed: {errs}")

    # Regenerated wholesale: drop the stale layer, then write the fresh one.
    db.clear_synthesis_nodes(paths.state_db)
    node_ids: list[str] = []
    parsed = cast(Any, result.parsed)
    # Every node records how many the layer is meant to hold, so an interrupted
    # write is detectable afterwards even though each row commits separately.
    layer_hash = layer_dependency_hash(dep_hash, len(parsed.syntheses))
    for item in parsed.syntheses:
        item_spans = list(item.source_span_ids) or span_ids
        syn_id = db.upsert_synthesis_node(
            paths.state_db,
            title=item.title,
            statement=item.statement,
            full_content=item.full_content,
            community_report_ids=report_ids,
            concept_ids=concept_ids,
            source_span_ids=item_spans,
            confidence=float(item.confidence),
            dependency_hash=layer_hash,
            prompt_run_id=result.trace_id,
        )
        for span_id in item_spans:
            db.record_artifact_dependency(
                paths.state_db,
                artifact_id=syn_id,
                artifact_type="synthesis_node",
                depends_on_id=span_id,
                depends_on_type="source_span",
                dependency_hash=dep_hash,
            )
        node_ids.append(syn_id)

    reemit_synthesis(paths)
    return node_ids


def reemit_synthesis(paths: cfg.WikiPaths) -> int:
    """Re-emit the derived SYN markdown corpus from authoritative DB rows.

    Deletes existing SYN-*.md projections, then re-emits from ``synthesis_nodes``
    so the derived projection always reflects the DB. Returns the count emitted.
    """
    out_dir: Path = paths.synthesis
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob(f"{consts.PREFIX_L4}-*.md"):
        stale.unlink()

    count = 0
    for node in db.list_synthesis_nodes(paths.state_db):
        page = projection.emit_synthesis_markdown(node)
        (out_dir / f"{node['id']}.md").write_text(page, encoding="utf-8")
        count += 1
    return count
