"""Note-writing context prompt family.

Packages Curator knowledge for the Artist writing in Obsidian. It provides
context and optional edit suggestions; it never overwrites notes on its own.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..contracts import PromptContract
from ..registry import register

PROMPT_ID = "curator.note_context_pack"
VERSION = "v1"


class NoteContextPackInput(BaseModel):
    note_topic: str
    evidence_block: str
    valid_span_ids_block: str
    final_output_language: str = "English"


class NoteContextPackOutput(BaseModel):
    context_markdown: str
    suggested_points: list[str] = Field(default_factory=list)
    source_span_ids: list[str] = Field(default_factory=list)


SYSTEM_TEMPLATE = """\
You are the Curator preparing context for the Artist who is writing a note in
Obsidian. You provide grounded context and suggestions, not a finished note.

Rules:
- Do NOT overwrite or rewrite the Artist's note. Provide context and points only.
- Keep citations visible: back claims with source_span_ids from the allowed list.
- Never invent span ids. Never propose editing read-only source truth.
- Write in the requested final output language.

Return ONLY JSON:
{"context_markdown": "...", "suggested_points": ["..."], "source_span_ids": ["SPAN-..."]}"""

USER_TEMPLATE = """\
Note topic: {{ note_topic }}

Allowed source span ids (cite only these):
{{ valid_span_ids_block }}

Evidence:
---
{{ evidence_block }}
---

Final output language: {{ final_output_language }}

Produce the note context pack as JSON."""


CONTRACT = register(
    PromptContract(
        prompt_id=PROMPT_ID,
        version=VERSION,
        family="note_writing",
        role="synthesizer",
        purpose="Package Curator knowledge as note-writing context for the Artist.",
        input_model=NoteContextPackInput,
        output_model=NoteContextPackOutput,
        system_template=SYSTEM_TEMPLATE,
        user_template=USER_TEMPLATE,
        validators=("source_span_ids", "no_source_truth_pollution"),
        temperature=0.3,
        requires_source_spans=True,
    )
)
