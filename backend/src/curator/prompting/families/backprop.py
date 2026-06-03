"""Backprop prompt family: classify feedback, then plan a safe patch.

Classification runs before any patch. Source truth is never rewritten to include
later derived insight; patch plans target generated nodes only.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..contracts import PromptContract
from ..registry import register

Classification = Literal[
    "correction",
    "contradiction",
    "derived_insight",
    "style_only",
    "promotion_request",
    "ambiguous",
]
SourceTruthImpact = Literal["none", "source_misread", "source_conflict", "unsafe"]
RecommendedAction = Literal[
    "patch_generated", "flag_review", "create_insight_candidate", "promote", "no_op"
]


# --- classify --------------------------------------------------------

class BackpropClassifyInput(BaseModel):
    previous_artifact: str
    updated_artifact: str
    linked_evidence_block: str
    backprop_policy_block: str
    human_request: str = ""


class BackpropClassifyOutput(BaseModel):
    classification: Classification
    confidence: float = Field(ge=0.0, le=1.0)
    affected_nodes: list[str] = Field(default_factory=list)
    source_truth_impact: SourceTruthImpact = "none"
    recommended_action: RecommendedAction = "no_op"
    reason: str = ""


CLASSIFY_SYSTEM = """\
You are the Curator's Backprop Diagnoser. You classify a change/feedback event
before any repair is attempted.

Classifications:
- correction: a generated artifact misread its evidence -> patch generated node.
- contradiction: two sources/artifacts conflict -> flag both, require review.
- derived_insight: a later interpretation not stated by the source ->
  create_insight_candidate; do NOT rewrite the source.
- style_only: presentation change, no claim change -> no expensive rebuild.
- promotion_request: human wants durable knowledge -> promote (writes 02_Wiki/).
- ambiguous: unclear -> flag_review.

Hard rules:
- Original source truth must NEVER be rewritten to include later derived insight.
- Prefer flag_review when uncertain.

Return ONLY JSON:
{"classification": "correction", "confidence": 0.0, "affected_nodes": [],
 "source_truth_impact": "none", "recommended_action": "patch_generated", "reason": "..."}"""

CLASSIFY_USER = """\
Backprop policy:
---
{{ backprop_policy_block }}
---

Previous artifact:
---
{{ previous_artifact }}
---

Updated artifact:
---
{{ updated_artifact }}
---

Linked evidence:
---
{{ linked_evidence_block }}
---

Human request (if any): {{ human_request }}

Classify the change as JSON."""


# --- patch plan ------------------------------------------------------

class BackpropPatchPlanInput(BaseModel):
    classification: str
    affected_nodes_block: str
    evidence_block: str


class BackpropPatchPlanOutput(BaseModel):
    nodes_to_patch: list[str] = Field(default_factory=list)
    nodes_to_invalidate: list[str] = Field(default_factory=list)
    reports_to_refresh: list[str] = Field(default_factory=list)
    exhibitions_to_refresh: list[str] = Field(default_factory=list)
    preserve_human_verified: list[str] = Field(default_factory=list)
    sources_unchanged: list[str] = Field(default_factory=list)
    notes: str = ""


PATCH_SYSTEM = """\
You are the Curator's Backprop Planner. Given a classification and affected
nodes, you produce an explicit, safe patch plan.

Hard rules:
- Only generated nodes may be patched/invalidated. List human-verified nodes to
  preserve and sources that must remain unchanged.
- Never plan to edit 03_Notes/, 04_Resources/, or 06_Archives/.

Return ONLY JSON:
{"nodes_to_patch": [], "nodes_to_invalidate": [], "reports_to_refresh": [],
 "exhibitions_to_refresh": [], "preserve_human_verified": [],
 "sources_unchanged": [], "notes": "..."}"""

PATCH_USER = """\
Classification: {{ classification }}

Affected nodes:
---
{{ affected_nodes_block }}
---

Evidence:
---
{{ evidence_block }}
---

Produce the patch plan as JSON."""


CLASSIFY_CONTRACT = register(
    PromptContract(
        prompt_id="curator.backprop_classify",
        version="v1",
        family="backprop",
        role="diagnoser",
        purpose="Classify a backprop feedback/change event.",
        input_model=BackpropClassifyInput,
        output_model=BackpropClassifyOutput,
        system_template=CLASSIFY_SYSTEM,
        user_template=CLASSIFY_USER,
        validators=("confidence_range", "no_source_truth_pollution"),
        temperature=0.1,
    )
)

PATCH_PLAN_CONTRACT = register(
    PromptContract(
        prompt_id="curator.backprop_patch_plan",
        version="v1",
        family="backprop",
        role="planner",
        purpose="Plan a safe patch for generated nodes only.",
        input_model=BackpropPatchPlanInput,
        output_model=BackpropPatchPlanOutput,
        system_template=PATCH_SYSTEM,
        user_template=PATCH_USER,
        validators=("no_source_truth_pollution",),
        temperature=0.1,
    )
)
