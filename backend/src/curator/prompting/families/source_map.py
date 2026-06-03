"""Source-map prompt family: structure-preserving reading of a source.

Converts source content into a structured source map (sections, spans, math
blocks, figures) WITHOUT synthesizing new insight. This is the L1 reading prompt
for cases where an LLM pass refines the deterministic parser structure.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..contracts import PromptContract
from ..registry import register

PROMPT_ID = "curator.source_map"
VERSION = "v1"


class SourceMapInput(BaseModel):
    source_title: str
    source_text: str


class SourceMapSection(BaseModel):
    title: str
    summary: str = ""
    key_claims: list[str] = Field(default_factory=list)
    math_blocks: list[str] = Field(default_factory=list)
    figure_refs: list[str] = Field(default_factory=list)


class SourceMapOutput(BaseModel):
    title: str
    sections: list[SourceMapSection] = Field(default_factory=list)
    parse_warnings: list[str] = Field(default_factory=list)


SYSTEM_TEMPLATE = """\
You are the Curator's Source Mapper. You read one source document and produce a
faithful, structure-preserving map of it.

Hard rules:
- Do NOT synthesize new insight, opinions, or cross-source connections.
- Do NOT translate a source claim into a different claim.
- Preserve mathematical expressions exactly, including $$...$$ / $...$ delimiters.
- Preserve figure/table references as they appear.
- When the structure is ambiguous, record it in parse_warnings rather than guessing.
- Never propose editing the original source.

Return ONLY JSON matching this shape:
{
  "title": "string",
  "sections": [
    {
      "title": "string",
      "summary": "one or two sentences, source-faithful",
      "key_claims": ["claim stated by the source"],
      "math_blocks": ["$$...$$"],
      "figure_refs": ["Figure 1", "Table 2"]
    }
  ],
  "parse_warnings": ["string"]
}"""

USER_TEMPLATE = """\
Source title: {{ source_title }}

Source text:
---
{{ source_text }}
---

Produce the source map as JSON."""


CONTRACT = register(
    PromptContract(
        prompt_id=PROMPT_ID,
        version=VERSION,
        family="source_map",
        role="reader",
        purpose="Structure-preserving map of one source; no new insight.",
        input_model=SourceMapInput,
        output_model=SourceMapOutput,
        system_template=SYSTEM_TEMPLATE,
        user_template=USER_TEMPLATE,
        validators=("no_source_truth_pollution",),
        trace_fields=("source_title",),
        temperature=0.1,
    )
)
