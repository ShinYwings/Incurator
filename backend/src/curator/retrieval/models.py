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

#: What KIND of answer a question wants, as derived at the boundary. NOT a route:
#: a route is the intent PLUS `policy.allowed_routes` PLUS `GraphStatus`, and the
#: model can see none of the latter two. Kept in step with
#: `prompting.families.query.Intent` by a test.
QUERY_INTENTS = ("lookup", "synthesis", "discovery")


@dataclass(frozen=True)
class DerivedQuery:
    """What the boundary understood about the user's message.

    `search_query` is WHAT TO SEARCH FOR; `intent` is WHAT KIND OF QUESTION IT
    IS. Both fall out of the same reading of the message. Returning only the
    first is what forced routing to re-derive the second from surface keywords
    of a paraphrase — a lottery whose odds were measured at 6-in-8.

    A dataclass rather than a widened tuple: a 4-tuple of heterogeneous values
    invites a 5th, and each addition re-breaks every unpack site. This widens by
    defaulted field instead, and names the empty-query state so it can be
    reasoned about.
    """

    search_query: str
    is_knowledge_question: bool
    intent: str = ""
    reason: str = ""
    #: HOW this was produced — `"derived"` (the model read the message),
    #: `"fallback"` (the provider failed and terms were scraped from the raw
    #: message), or `"unset"` (nothing ran; the message was empty).
    #:
    #: `"fallback"` exists because it was indistinguishable from `"derived"`, and
    #: that cost a silent failure: `_fallback_search_terms` keeps every script,
    #: so a Korean question fell back to Korean, `is_knowledge_question` was True,
    #: the caller marked it `"derived"`, and the seeding warning — scoped to
    #: `"unset"` — was suppressed. English-only seeding then matched nothing with
    #: nothing said. A field that cannot express "somebody tried and failed"
    #: forces the caller to guess, and it guessed wrong.
    status: str = "derived"


@dataclass
class QueryRequest:
    question: str
    english_query: str = ""
    #: Whether a derivation actually RAN for this request.
    #:
    #:   "unset"   — it did not (CLI, MCP, tests). `working_query` falls back to
    #:               `question`, which is the best available behaviour, and
    #:               internals warn when English-only seeding then matches
    #:               nothing.
    #:   "derived"  — it did, and the model produced this query. An empty
    #:                `english_query` here is a legitimate result, not a failure:
    #:                a whole-corpus question has no search terms.
    #:   "fallback" — it was attempted and the provider failed, so these terms
    #:                were scraped from the raw message and may be in any
    #:                language. Internals must warn on this exactly as they do on
    #:                "unset"; treating it as "derived" is what made a dead
    #:                provider look like a working one.
    english_query_status: str = "unset"
    #: Whether the derivation judged this message to be a knowledge question.
    #:
    #: `True` when nothing derived (the safe default: never refuse a question
    #: because no classifier ran). `False` only when a derivation RAN and said
    #: the message asks for something to be done to text the user supplied —
    #: "translate this paragraph: <body>" — for which searching the body is
    #: worse than not searching at all.
    #:
    #: **Recorded, not yet acted on — say so rather than imply otherwise.**
    #: v0.69.0 computed this in the funnel, paid for it, and read only three of
    #: the four returned fields; v0.71.0 carries the fourth into the request and
    #: into the query trace so the cost is at least observable. But nothing in
    #: `context_fetch` reads it to skip retrieval yet, so on the funnel path
    #: `search_query` is still empty for such a message, `working_query` still
    #: falls back to the raw body, and retrieval still runs BM25 over the
    #: translation request. `plugin_api/context.py` gates its own path on
    #: `derived.is_knowledge_question` and returns an empty pack; the funnel does
    #: not, and making the two agree is a control-flow change that gets its own
    #: plan (USER_REPORT.md, 2026-08-29).
    is_knowledge_question: bool = True
    #: The derived intent (`QUERY_INTENTS`), or "" when no derivation ran.
    #:
    #: Routing used to read surface keywords off `working_query` — which is the
    #: EXTRACTOR'S PARAPHRASE, not the user's words. Measured: the same question
    #: asked eight times produced eight different English queries, and the route
    #: followed whichever synonym was sampled — `themes`/`summary` matched
    #: `_GLOBAL_SIGNALS`, `overview` did not, so one question reached `global`
    #: 6 times and `local` 2 times. An intent stated by the step that read the
    #: user's actual words removes the lottery.
    intent: str = ""
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
    # source_span | knowledge_unit | community_report | synthesis | memory_path | search_hit | entity
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
    # Claim-support state of the underlying knowledge unit, served as a LABEL
    # since v0.47.0 — it used to gate the search index entirely. Empty for
    # records that have no claim support (spans, entities, reports, synthesis).
    support_status: str = ""
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
        """Render items within max_chars; append explicit omission marker (§28.3).

        The rendered block — items, ``\\n\\n`` separators, AND the omission marker
        — never exceeds ``max_chars``. When items are omitted, a marker budget is
        reserved up front so the marker replaces the last partial item rather than
        overflowing the budget. A final hard slice guards the degenerate case where
        ``max_chars`` is smaller than the marker itself.
        """
        total = len(self.items)
        sep = "\n\n"

        def _render(items_budget: int) -> tuple[list[str], int]:
            lines: list[str] = []
            used = 0
            for item in self.items:
                chunk = f"[{item.kind} {item.id}] {item.title}\n{item.text}".strip()
                addition = len(chunk) + (len(sep) if lines else 0)
                if used + addition > items_budget:
                    break
                lines.append(chunk)
                used += addition
            return lines, used

        # First pass: how many items fit with the full budget?
        first_lines, _ = _render(max_chars)
        if len(first_lines) == total:
            return sep.join(first_lines)

        # Items will be omitted — reserve room for the marker (worst-case count).
        marker_for = lambda n: (  # noqa: E731
            f"[{n} item{'s' if n != 1 else ''} omitted — character budget reached]"
        )
        marker_budget = len(marker_for(total)) + len(sep)
        lines, _ = _render(max(0, max_chars - marker_budget))
        omitted = total - len(lines)
        if omitted > 0:
            lines.append(marker_for(omitted))
        block = sep.join(lines)
        # Defensive hard guarantee for pathologically small budgets.
        return block[:max_chars]


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
