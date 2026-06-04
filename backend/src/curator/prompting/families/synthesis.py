"""L4 Synthesis prompt family (shared corpus-wide synthesis).

Distills community reports / concepts into a small set of cross-cutting,
corpus-wide synthesized insights — the durable, workspace-INDEPENDENT top layer of
the refined DAG (Zettelkasten "linking & synthesis"). NOT a per-workspace
exhibition; the dynamic per-workspace curation lens sits above this and draws on
it. Every synthesized insight stays grounded in real source spans.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..contracts import PromptContract
from ..registry import register

PROMPT_ID = "curator.synthesis_write"
VERSION = "v1"


class SynthesisWriteInput(BaseModel):
    reports_block: str
    valid_span_ids_block: str
    max_syntheses: int = 6


class SynthesizedInsight(BaseModel):
    title: str
    statement: str
    full_content: str = ""
    source_span_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class SynthesisWriteOutput(BaseModel):
    syntheses: list[SynthesizedInsight] = Field(default_factory=list)


SYSTEM_TEMPLATE = """\
You are the Curator's Synthesizer. From community reports, you distill a small set
of CROSS-CUTTING, corpus-wide synthesized insights — connections and higher-level
claims that span multiple communities, not restatements of a single report.

Hard rules:
- Synthesize ACROSS reports; do not merely copy one report's summary.
- Each synthesis must be backed by source_span_ids from the allowed list. Never
  invent span ids.
- These are generated retrieval aids, NOT human-verified truth. Reflect
  uncertainty; note "not enough evidence" where appropriate.
- Keep it corpus-wide and workspace-independent (do NOT tailor to any one project).
- confidence is a float in [0,1]. Produce at most the requested number.
- Never propose editing read-only source truth.

Return ONLY JSON:
{
  "syntheses": [
    {"title": "...", "statement": "the cross-cutting insight",
     "full_content": "supporting explanation", "source_span_ids": ["SPAN-..."],
     "confidence": 0.6}
  ]
}"""

USER_TEMPLATE = """\
Allowed source span ids (cite only these):
{{ valid_span_ids_block }}

Community reports:
---
{{ reports_block }}
---

Max syntheses: {{ max_syntheses }}

Write the cross-cutting syntheses as JSON."""


CONTRACT = register(
    PromptContract(
        prompt_id=PROMPT_ID,
        version=VERSION,
        family="synthesis",
        role="synthesizer",
        purpose="Distill community reports into shared corpus-wide cross-cutting insights.",
        input_model=SynthesisWriteInput,
        output_model=SynthesisWriteOutput,
        system_template=SYSTEM_TEMPLATE,
        user_template=USER_TEMPLATE,
        validators=("source_span_ids", "confidence_range", "no_source_truth_pollution"),
        temperature=0.3,
        requires_source_spans=True,
    )
)
