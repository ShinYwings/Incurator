"""v0.3.1 backprop classifier.

Classifies a feedback/change event BEFORE any patch, via the
``curator.backprop_classify`` contract. The classification drives the insight
lifecycle (insight_lifecycle.py). Source truth is never rewritten — the classifier
only diagnoses; patching targets generated nodes only.

See ``docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`` §18.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import prompting

__all__ = ["BackpropEvent", "BackpropClassification", "classify_feedback"]

CLASSIFICATIONS = (
    "correction", "contradiction", "derived_insight",
    "style_only", "promotion_request", "ambiguous",
)


@dataclass
class BackpropEvent:
    previous_artifact: str
    updated_artifact: str
    linked_evidence: str = ""
    backprop_policy: str = ""
    human_request: str = ""
    workspace_id: str = ""
    affected_node_ids: list[str] = field(default_factory=list)


@dataclass
class BackpropClassification:
    classification: str
    confidence: float = 0.0
    affected_nodes: list[str] = field(default_factory=list)
    source_truth_impact: str = "none"
    recommended_action: str = "no_op"
    reason: str = ""
    trace_id: str = ""
    ok: bool = False


def classify_feedback(
    db_path: Path, event: BackpropEvent, client: Any, *, curate_spec_hash: str = ""
) -> BackpropClassification:
    contract = prompting.REGISTRY.get("curator.backprop_classify")
    input_obj = contract.input_model(
        previous_artifact=event.previous_artifact,
        updated_artifact=event.updated_artifact,
        linked_evidence_block=event.linked_evidence,
        backprop_policy_block=event.backprop_policy,
        human_request=event.human_request,
    )
    run = prompting.run_prompt(
        db_path, client, contract, input_obj,
        curate_spec_hash=curate_spec_hash,
    )
    if run.parsed is None:
        return BackpropClassification(
            classification="ambiguous",
            reason="classification failed validation",
            recommended_action="flag_review",
            trace_id=run.trace_id,
            ok=False,
        )
    p = run.parsed
    return BackpropClassification(
        classification=getattr(p, "classification", "ambiguous"),
        confidence=getattr(p, "confidence", 0.0),
        affected_nodes=list(getattr(p, "affected_nodes", []) or event.affected_node_ids),
        source_truth_impact=getattr(p, "source_truth_impact", "none"),
        recommended_action=getattr(p, "recommended_action", "no_op"),
        reason=getattr(p, "reason", ""),
        trace_id=run.trace_id,
        ok=True,
    )
