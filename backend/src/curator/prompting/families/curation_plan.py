"""Curation-plan prompt family.

Converts a workspace's curate.yml (compiled policy) plus graph/source inventory
into a curation plan: source scope, retrieval modes, target concepts, output
shape, verification strategy, and known gaps.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..contracts import PromptContract
from ..registry import register

PROMPT_ID = "curator.curation_plan"
VERSION = "v1"


class CurationPlanInput(BaseModel):
    curate_spec_block: str
    source_inventory_block: str
    graph_inventory_block: str


class CurationPlanOutput(BaseModel):
    route: str
    selected_sources: list[str] = Field(default_factory=list)
    excluded_sources: list[str] = Field(default_factory=list)
    target_concepts: list[str] = Field(default_factory=list)
    required_report_levels: list[int] = Field(default_factory=list)
    retrieval_modes: list[str] = Field(default_factory=list)
    output_shape: str = ""
    verification_strategy: str = ""
    prompt_profile: str = ""
    known_gaps: list[str] = Field(default_factory=list)


SYSTEM_TEMPLATE = """\
You are the Curator's Planner. Given a workspace's Knowledge Requirement
Specification (curate.yml) and the available source/graph inventory, you produce
a concrete curation plan that drives the dynamic curation lens and query routing.

Hard rules:
- Respect the spec's source include/exclude rules. List excluded sources and
  rely only on selected ones.
- Choose retrieval_modes from: local, global, explore, source-section.
- Honor the spec's allowed reasoning modes and verification policy.
- Name known_gaps honestly; do not invent coverage that the inventory lacks.
- Never propose editing read-only source truth.

Return ONLY JSON:
{
  "route": "global",
  "selected_sources": ["03_Notes/..."],
  "excluded_sources": ["03_Notes/private/..."],
  "target_concepts": ["..."],
  "required_report_levels": [0],
  "retrieval_modes": ["local", "global"],
  "output_shape": "evidence pack with Evidence Map, Synthesis, Gaps, Directives",
  "verification_strategy": "require source spans; surface contradictions",
  "prompt_profile": "technical-research",
  "known_gaps": ["..."]
}"""

USER_TEMPLATE = """\
Knowledge Requirement Specification (curate.yml, compiled):
---
{{ curate_spec_block }}
---

Source inventory:
---
{{ source_inventory_block }}
---

Graph / community inventory:
---
{{ graph_inventory_block }}
---

Produce the curation plan as JSON."""


CONTRACT = register(
    PromptContract(
        prompt_id=PROMPT_ID,
        version=VERSION,
        family="curation_plan",
        role="planner",
        purpose="Compile curate.yml + inventory into a curation plan.",
        input_model=CurationPlanInput,
        output_model=CurationPlanOutput,
        system_template=SYSTEM_TEMPLATE,
        user_template=USER_TEMPLATE,
        validators=("no_source_truth_pollution",),
        temperature=0.2,
    )
)
