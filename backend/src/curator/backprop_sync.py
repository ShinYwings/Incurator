"""v0.3.1 backprop sync: Exhibition reverse-parse → classify → plan.

When a human/agent edits an L4 Exhibition markdown file, this reverse-parses it,
classifies the change (``curator.backprop_classify``), and produces a safe action:
derived insights become provisional candidates; corrections yield an explicit
patch plan (``curator.backprop_patch_plan``) targeting GENERATED nodes only.
Source truth is never rewritten (SYSTEM_BEHAVIOR_v0.3.1 §18, §22.2).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import page_writer, prompting
from .backprop_classifier import BackpropClassification, BackpropEvent, classify_feedback
from .insight_lifecycle import ActionPlan, create_insight_from_classification, plan_action

__all__ = ["BackpropSyncResult", "backprop_from_exhibition", "build_patch_plan"]


@dataclass
class BackpropSyncResult:
    exhibition_id: str
    classification: BackpropClassification
    plan: ActionPlan
    insight_candidate_id: str = ""
    patch_plan: dict[str, Any] | None = None
    dry_run: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def build_patch_plan(
    db_path: Path, client: Any, classification: BackpropClassification, *, evidence: str = ""
) -> dict[str, Any] | None:
    """Run the patch-plan contract for a correction. Returns the plan dict or None."""
    contract = prompting.REGISTRY.get("curator.backprop_patch_plan")
    input_obj = contract.input_model(
        classification=classification.classification,
        affected_nodes_block="\n".join(classification.affected_nodes),
        evidence_block=evidence,
    )
    run = prompting.run_prompt(
        db_path, client, contract, input_obj, query_trace_id=classification.trace_id,
    )
    if run.parsed is None:
        return None
    return run.parsed.model_dump()


def backprop_from_exhibition(
    paths,
    client: Any,
    exh_id: str,
    *,
    previous: str = "",
    dry_run: bool = False,
    curate_spec_hash: str = "",
) -> BackpropSyncResult:
    """Reverse-parse an edited Exhibition and classify the change.

    Reads the EXH markdown, builds a BackpropEvent, classifies it, plans a safe
    action, and (unless dry_run) creates an insight candidate / records a patch
    plan. Never edits source truth.
    """
    exh_path = paths.exhibitions / f"{exh_id}.md"
    if not exh_path.exists():
        empty = BackpropClassification(classification="ambiguous", reason="exhibition not found")
        return BackpropSyncResult(
            exhibition_id=exh_id, classification=empty, plan=plan_action(empty),
            dry_run=dry_run, error=f"exhibition not found: {exh_id}",
        )

    page = page_writer.read_page(exh_path)
    fm = page.frontmatter if page else {}
    body = page.body if page else ""
    # Affected generated nodes = the EXH's core concepts (+ its own id).
    affected = [str(c) for c in (fm.get("core_concepts") or [])]
    affected = [_id_from_link(c) for c in affected] + [exh_id]
    spans = [str(s) for s in (fm.get("source_span_ids") or [])]

    event = BackpropEvent(
        previous_artifact=previous,
        updated_artifact=body,
        linked_evidence="\n".join(spans),
        backprop_policy="never_rewrite_original_source",
        workspace_id=str(fm.get("workspace_id") or ""),
        affected_node_ids=affected,
    )
    classification = classify_feedback(paths.state_db, event, client, curate_spec_hash=curate_spec_hash)
    plan = plan_action(classification)

    candidate_id = ""
    patch_plan = None
    if not dry_run and plan.creates_candidate:
        candidate_id = create_insight_from_classification(
            paths.state_db, classification, statement=_first_line(body) or exh_id,
            workspace_id=event.workspace_id, source_event_id=exh_id,
            evidence=[{"source_span_ids": spans}],
        )
    if plan.action == "patch_generated":
        patch_plan = build_patch_plan(
            paths.state_db, client, classification, evidence="\n".join(spans)
        )
    return BackpropSyncResult(
        exhibition_id=exh_id, classification=classification, plan=plan,
        insight_candidate_id=candidate_id, patch_plan=patch_plan, dry_run=dry_run,
    )


def _id_from_link(ref: str) -> str:
    ref = ref.strip().strip("[]")
    return ref.split("/")[-1] if "/" in ref else ref


def _first_line(body: str) -> str:
    for line in body.splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            return s[:200]
    return ""
