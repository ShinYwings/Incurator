"""Community-report prompt family (GraphRAG-style global summaries).

Summarizes one graph community for global reasoning. Reports are generated
retrieval aids, not human truth; they include representative evidence,
contradictions, and "not enough evidence" notes where appropriate.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..contracts import PromptContract
from ..registry import register

PROMPT_ID = "curator.community_report_write"
VERSION = "v1"


class CommunityReportInput(BaseModel):
    community_title: str
    entities_block: str
    relations_block: str
    valid_span_ids_block: str


class ReportFinding(BaseModel):
    summary: str
    explanation: str = ""
    source_span_ids: list[str] = Field(default_factory=list)
    rank: float = Field(default=0.5, ge=0.0, le=1.0)


class CommunityReportOutput(BaseModel):
    title: str
    summary: str
    full_content: str
    findings: list[ReportFinding] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    source_span_ids: list[str] = Field(default_factory=list)
    rank: float = Field(default=0.5, ge=0.0, le=1.0)


SYSTEM_TEMPLATE = """\
You are the Curator's Community Analyst. You summarize one graph community
(a set of related entities and relations) into a report for global reasoning.

Hard rules:
- The report is a generated retrieval aid, NOT human-verified truth. Do not
  assert certainty the evidence does not support.
- Include representative findings, each backed by source_span_ids from the
  allowed list. Never invent span ids.
- Preserve central equations, formulas, and code expressions exactly when they
  are needed for a finding or explanation.
- Record disagreements in "contradictions".
- If evidence is thin, say so explicitly in the summary.
- rank fields are importance in [0,1].
- Never propose editing the original source.

Return ONLY JSON:
{
  "title": "string",
  "summary": "2-4 sentence global summary",
  "full_content": "longer markdown report",
  "findings": [
    {"summary": "...", "explanation": "...", "source_span_ids": ["SPAN-..."], "rank": 0.8}
  ],
  "contradictions": ["..."],
  "source_span_ids": ["SPAN-..."],
  "rank": 0.7
}"""

USER_TEMPLATE = """\
Community: {{ community_title }}

Allowed source span ids (cite only these):
{{ valid_span_ids_block }}

Entities:
---
{{ entities_block }}
---

Relations:
---
{{ relations_block }}
---

Write the community report as JSON."""


CONTRACT = register(
    PromptContract(
        prompt_id=PROMPT_ID,
        version=VERSION,
        family="community_reports",
        role="synthesizer",
        purpose="Summarize a graph community for global reasoning.",
        input_model=CommunityReportInput,
        output_model=CommunityReportOutput,
        system_template=SYSTEM_TEMPLATE,
        user_template=USER_TEMPLATE,
        validators=("source_span_ids", "confidence_range",
                    "no_source_truth_pollution"),
        trace_fields=("community_title",),
        temperature=0.3,
        requires_source_spans=True,
    )
)
