"""Retrieval data models for the v0.3.1 query orchestrator.

See ``docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`` §17, §28–§30.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "QueryRequest",
    "EvidenceItem",
    "EvidencePack",
    "GraphStatus",
    "QueryResultV031",
    "StructuredLocator",
    "ROUTES",
]

ROUTES = ("local", "global", "explore", "source-section")


@dataclass
class QueryRequest:
    question: str
    english_query: str = ""
    input_language: str = ""
    final_output_language: str = "English"
    workspace_path: str = ""
    mode: str = "auto"  # auto | local | global | explore | source-section
    source_key: str = ""  # source id / relpath for source-section
    session_id: str | None = None

    @property
    def working_query(self) -> str:
        return (self.english_query or self.question).strip()


@dataclass
class StructuredLocator:
    """Resolved sub-document target for an evidence item (SYSTEM_BEHAVIOR §29.2).

    Supplements (never replaces) the authoritative source_span_id.
    Rendering clients read locator_status before making a link clickable.
    """
    source_id: int | None          # FK to sources.id; None for external-only
    source_kind: str               # vault_markdown | vault_pdf | external_uri | promoted_wiki
    relpath: str | None            # vault-relative path (None for external_uri)
    heading: str | None            # nearest heading above the span (Markdown)
    block_id: str | None           # Obsidian block anchor ^block-id (Markdown)
    page_number: int | None        # verified printed page number (PDF)
    toc_id: str | None             # PDF table-of-contents section id
    external_uri: str | None       # reference-mode external URI
    # exact | fallback_file | fallback_source | duplicate_anchor | stale | unavailable
    locator_status: str


@dataclass
class EvidenceItem:
    id: str
    # source_span | knowledge_unit | community_report | synthesis | memory_path | qmd_hit | entity
    kind: str
    title: str
    text: str
    score: float = 0.0
    source_span_ids: list[str] = field(default_factory=list)
    community_report_id: str = ""
    memory_path_id: str = ""
    synthesis_node_id: str = ""
    # F10 (SEARCH_ENGINE_SCHEMA §10.2): "ok" when ``text`` is the hydrated full
    # span text; "stale" when hydration was unavailable and ``text`` falls back
    # to the 200-char preview (an explicit flag, so the preview is never silently
    # presented as sufficient evidence).
    evidence_status: str = "ok"
    # §29.5: resolved sub-document locator; None when no backing source_span_id.
    locator: StructuredLocator | None = None


@dataclass
class EvidencePack:
    route: str
    items: list[EvidenceItem] = field(default_factory=list)
    source_span_ids: list[str] = field(default_factory=list)
    community_report_ids: list[str] = field(default_factory=list)
    synthesis_node_ids: list[str] = field(default_factory=list)
    memory_path_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    retrieval_trace: dict = field(default_factory=dict)
    # §30.1: RTR-* retrieval execution id; set by build_evidence.
    retrieval_execution_id: str = ""
    # §28.4: per-route omission counts (e.g. {"global_reports": 5}).
    omitted_counts: dict = field(default_factory=dict)

    def evidence_block(self, *, max_chars: int = 16000) -> str:
        """Render items up to max_chars; append explicit omission marker (§28.3)."""
        lines: list[str] = []
        used = 0
        rendered = 0
        for item in self.items:
            chunk = f"[{item.kind} {item.id}] {item.title}\n{item.text}".strip()
            if used + len(chunk) > max_chars:
                break
            lines.append(chunk)
            used += len(chunk)
            rendered += 1
        omitted = len(self.items) - rendered
        if omitted > 0:
            marker = f"[{omitted} item{'s' if omitted != 1 else ''} omitted — character budget reached]"
            lines.append(marker)
        return "\n\n".join(lines)


@dataclass
class GraphStatus:
    has_entities: bool = False
    has_relations: bool = False
    has_reports: bool = False

    @property
    def complete(self) -> bool:
        return self.has_entities and self.has_reports


@dataclass
class QueryResultV031:
    question: str
    answer: str = ""
    route: str = ""
    trace_id: str = ""
    prompt_trace_ids: list[str] = field(default_factory=list)
    source_span_ids: list[str] = field(default_factory=list)
    community_report_ids: list[str] = field(default_factory=list)
    synthesis_node_ids: list[str] = field(default_factory=list)
    memory_path_ids: list[str] = field(default_factory=list)
    insight_candidate_ids: list[str] = field(default_factory=list)
    input_language: str = ""
    english_query: str = ""
    final_output_language: str = ""
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.answer)
