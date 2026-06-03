"""Knowledge-unit extraction prompt family (L2).

Extracts typed knowledge units from source spans. Every unit MUST cite at least
one real source span id. Derived interpretations are marked, not attached as
source-authored claims.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..contracts import PromptContract
from ..registry import register

PROMPT_ID = "curator.knowledge_unit_extract"
VERSION = "v1"

UnitType = Literal[
    "claim",
    "definition",
    "equation",
    "procedure",
    "method",
    "result",
    "observation",
    "constraint",
]


class KnowledgeUnitExtractInput(BaseModel):
    source_title: str
    # Spans presented to the model: each {id, section_title, text}.
    spans_block: str
    valid_span_ids_block: str


class ExtractedKnowledgeUnit(BaseModel):
    canonical_name: str
    unit_type: UnitType
    statement: str
    source_span_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    truth_status: Literal["source_supported", "derived_insight"] = "source_supported"


class KnowledgeUnitExtractOutput(BaseModel):
    units: list[ExtractedKnowledgeUnit] = Field(default_factory=list)


SYSTEM_TEMPLATE = """\
You are the Curator's Knowledge Unit Extractor. You convert source spans into
typed, atomic, individually-citable knowledge units.

Hard rules:
- Every unit MUST cite at least one source_span_id from the allowed list.
- No span, no unit. Never invent a span id that is not in the allowed list.
- One unit = one atomic fact/definition/equation/etc. Do not bundle.
- unit_type is one of: claim, definition, equation, procedure, method, result,
  observation, constraint.
- Preserve equations exactly (with $$...$$ / $...$ delimiters) in equation units.
- If a statement is your interpretation rather than something the source states,
  set truth_status to "derived_insight". Otherwise "source_supported".
- confidence is a float in [0,1].
- Never propose editing the original source.

Return ONLY JSON:
{
  "units": [
    {
      "canonical_name": "short name",
      "unit_type": "claim",
      "statement": "the atomic fact, faithful to the cited span(s)",
      "source_span_ids": ["SPAN-..."],
      "confidence": 0.0,
      "truth_status": "source_supported"
    }
  ]
}"""

USER_TEMPLATE = """\
Source: {{ source_title }}

Allowed source span ids (cite only these):
{{ valid_span_ids_block }}

Spans:
---
{{ spans_block }}
---

Extract the knowledge units as JSON."""


CONTRACT = register(
    PromptContract(
        prompt_id=PROMPT_ID,
        version=VERSION,
        family="knowledge_units",
        role="extractor",
        purpose="Extract typed L2 knowledge units, each citing source spans.",
        input_model=KnowledgeUnitExtractInput,
        output_model=KnowledgeUnitExtractOutput,
        system_template=SYSTEM_TEMPLATE,
        user_template=USER_TEMPLATE,
        validators=("source_span_ids", "requires_source_spans", "confidence_range",
                    "no_source_truth_pollution"),
        trace_fields=("source_title",),
        temperature=0.2,
        requires_source_spans=True,
    )
)
