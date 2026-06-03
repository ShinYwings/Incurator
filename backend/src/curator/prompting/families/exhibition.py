"""Exhibition prompt family.

Writes or refreshes an Exhibition: a workspace-specific curated context package
controlled by curate.yml. Separates source-backed claims from derived
suggestions and records gaps, contradictions, and agent directives.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..contracts import PromptContract
from ..registry import register

PROMPT_ID = "curator.exhibition_write"
VERSION = "v1"


class ExhibitionWriteInput(BaseModel):
    goal_block: str
    output_contract_block: str
    evidence_block: str
    valid_span_ids_block: str
    final_output_language: str = "English"


class ExhibitionWriteOutput(BaseModel):
    title: str
    markdown: str
    source_span_ids: list[str] = Field(default_factory=list)
    unresolved_gaps: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    agent_directives: list[str] = Field(default_factory=list)
    insight_candidates: list[str] = Field(default_factory=list)


SYSTEM_TEMPLATE = """\
You are the Curator staging an Exhibition for a workspace Artist. An Exhibition
is a curated context package, NOT a generic chatbot answer.

Hard rules:
- The workspace goal and output contract are the controlling spec. Follow the
  requested sections, style, and citation style.
- Separate source-backed claims (cite source_span_ids from the allowed list)
  from derived suggestions (clearly marked).
- Record unresolved_gaps, contradictions, and agent_directives.
- Put genuinely new interpretations into insight_candidates, not into the
  source-backed claims.
- Never invent source span ids. Never propose editing read-only source truth.
- Write the markdown in the requested final output language.

Return ONLY JSON:
{
  "title": "string",
  "markdown": "the full Exhibition body in markdown",
  "source_span_ids": ["SPAN-..."],
  "unresolved_gaps": ["..."],
  "contradictions": ["..."],
  "agent_directives": ["..."],
  "insight_candidates": ["..."]
}"""

USER_TEMPLATE = """\
Workspace goal:
---
{{ goal_block }}
---

Output contract:
---
{{ output_contract_block }}
---

Allowed source span ids (cite only these):
{{ valid_span_ids_block }}

Evidence:
---
{{ evidence_block }}
---

Final output language: {{ final_output_language }}

Write the Exhibition as JSON."""


CONTRACT = register(
    PromptContract(
        prompt_id=PROMPT_ID,
        version=VERSION,
        family="exhibition",
        role="synthesizer",
        purpose="Stage a workspace Exhibition context package from curate.yml.",
        input_model=ExhibitionWriteInput,
        output_model=ExhibitionWriteOutput,
        system_template=SYSTEM_TEMPLATE,
        user_template=USER_TEMPLATE,
        validators=("source_span_ids", "no_source_truth_pollution"),
        temperature=0.3,
        requires_source_spans=True,
    )
)
