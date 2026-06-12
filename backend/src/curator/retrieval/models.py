"""Retrieval data models for the v0.3.1 query orchestrator.

See ``docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`` §17.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "QueryRequest",
    "EvidenceItem",
    "EvidencePack",
    "GraphStatus",
    "QueryResultV031",
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

    def evidence_block(self, *, max_chars: int = 16000) -> str:
        lines: list[str] = []
        used = 0
        for item in self.items:
            chunk = f"[{item.kind} {item.id}] {item.title}\n{item.text}".strip()
            if used + len(chunk) > max_chars:
                break
            lines.append(chunk)
            used += len(chunk)
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
