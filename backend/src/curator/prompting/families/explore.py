"""Explore prompt family (DRIFT-like discovery).

Expands a question into follow-up questions and ranks provisional insight
candidates. Insight candidates are provisional, never asserted as truth.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..contracts import PromptContract
from ..registry import register

PROMPT_ID = "curator.query_explore_expand"
VERSION = "v1"


class ExploreExpandInput(BaseModel):
    question: str
    primer_block: str
    valid_span_ids_block: str
    max_followups: int = 5


class ExploreInsightCandidate(BaseModel):
    statement: str
    rationale: str = ""
    source_span_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.4, ge=0.0, le=1.0)
    needs_human_review: bool = True


class ExploreExpandOutput(BaseModel):
    followup_questions: list[str] = Field(default_factory=list)
    insight_candidates: list[ExploreInsightCandidate] = Field(default_factory=list)


SYSTEM_TEMPLATE = """\
You are the Curator in explore mode, discovering non-obvious connections.

Rules:
- Generate up to the requested number of focused follow-up questions that would
  deepen understanding of the original question.
- Propose insight candidates: provisional connections or interpretations. These
  are NOT truth; mark needs_human_review and keep confidence modest.
- Back each candidate with source_span_ids from the allowed list where possible;
  never invent span ids.
- Never propose editing read-only source truth.

Return ONLY JSON:
{
  "followup_questions": ["..."],
  "insight_candidates": [
    {"statement": "...", "rationale": "...", "source_span_ids": ["SPAN-..."],
     "confidence": 0.4, "needs_human_review": true}
  ]
}"""

USER_TEMPLATE = """\
Original question: {{ question }}

Allowed source span ids (cite only these):
{{ valid_span_ids_block }}

Primer (from community reports / graph):
---
{{ primer_block }}
---

Max follow-ups: {{ max_followups }}

Expand the exploration as JSON."""


CONTRACT = register(
    PromptContract(
        prompt_id=PROMPT_ID,
        version=VERSION,
        family="explore",
        role="synthesizer",
        purpose="Generate follow-ups and provisional insight candidates.",
        input_model=ExploreExpandInput,
        output_model=ExploreExpandOutput,
        system_template=SYSTEM_TEMPLATE,
        user_template=USER_TEMPLATE,
        validators=("source_span_ids", "confidence_range",
                    "no_source_truth_pollution"),
        temperature=0.5,
    )
)
