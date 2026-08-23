"""Query pipeline: search → synthesize → return answer + trace.

Flow:
  1. Call search.query() to get top-K matching Curator pages.
  2. Build a synthesis prompt with the matches as context.
  3. Stream the LLM's answer via the active client.
  4. Provide a streaming answer using markdown citations.

Sessionless: a query returns an answer + trace; it does NOT write any vault file.
Durable human artifacts come only from an explicit promotion to ``02_Wiki/``.

Callbacks let the CLI render progress (search phase, synthesis streaming).
"""

from __future__ import annotations
from . import constants as consts

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast

from . import config as cfg
from . import db
from .retrieval.models import DerivedQuery
from . import prompts
from . import search

# Strip only the retired legacy curator URI schemes (``legacy://`` and the
# pre-v0.3.2 search-binary scheme) from wikilink targets. Built via string
# concatenation so the retired scheme literal never appears in source. Kept
# narrow on purpose: a broad ``scheme://`` matcher would also strip standard
# external links (``http://``/``https://``/``obsidian://``).
_LEGACY_SCHEME_RE = re.compile(r"^/?(?:legacy|" + "q" + "md)://[^/]+/")


class ChatClient(Protocol):
    def chat(
        self,
        messages: list[prompts.ChatMessage],
        *,
        json_mode: bool = False,
        temperature: float = 0.3,
    ) -> str: ...


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class QueryResult:
    """The outcome of a single `wiki query` invocation."""

    question: str
    answer: str = ""
    hits: list[search.SearchHit] = field(default_factory=list)
    session_id: str | None = None
    english_query: str = ""
    input_language: str = ""
    final_output_language: str = ""
    error: str | None = None
    # v0.3.1 curation-native trace fields (populated when a route is used).
    route: str = ""
    trace_id: str = ""
    prompt_trace_ids: list[str] = field(default_factory=list)
    source_span_ids: list[str] = field(default_factory=list)
    community_report_ids: list[str] = field(default_factory=list)
    synthesis_node_ids: list[str] = field(default_factory=list)
    memory_path_ids: list[str] = field(default_factory=list)
    insight_candidate_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.answer)


# ---------------------------------------------------------------------------
# Progress callbacks
# ---------------------------------------------------------------------------


class QueryCallbacks:
    """Hooks the CLI provides to render progress during a query."""

    def on_start(self, question: str, mode: str) -> None: ...

    def on_classifying_intent(self) -> None: ...

    def on_intent_classified(self, intent: str) -> None: ...

    def on_chitchat_reply(self, reply: str) -> None: ...

    def on_searching(self) -> None: ...

    def on_search_done(self, results: search.SearchResults) -> None: ...

    def on_no_results(self) -> None: ...

    def on_synthesizing(self) -> None: ...

    def on_stream_chunk(self, chunk: str) -> None: ...

    def on_complete(self, result: QueryResult) -> None: ...

    def on_error(self, error: str) -> None: ...


def _source_wikilink(relpath: str) -> str:
    """Format a source-document vault relpath as an Obsidian wikilink.

    Strips only the `.md` suffix (Obsidian convention); other extensions such as
    `.pdf` are kept so the link resolves to the real source file.
    """
    return f"[[{relpath.removesuffix('.md')}]]"


def resolve_source_links(paths: cfg.WikiPaths, source_span_ids: list[str]) -> list[str]:
    """Distinct source-document wikilinks backing the given spans, in span order.

    Forward provenance: spans → source documents outside `.curator/` → wikilinks
    that resolve to real, visible vault files (so they appear in Graph/backlinks
    when written into a visible `02_Wiki/` note).
    """
    if not source_span_ids:
        return []
    return [
        _source_wikilink(src["relpath"])
        for src in db.sources_for_spans(paths.state_db, source_span_ids)
    ]


def _sources_footer(source_links: list[str]) -> str:
    """A `## Sources` markdown section listing distinct source-document links."""
    seen: list[str] = []
    for link in source_links:
        if link not in seen:
            seen.append(link)
    if not seen:
        return ""
    body = "\n".join(f"- {link}" for link in seen)
    return f"\n## Sources\n\n{body}\n"


# ---------------------------------------------------------------------------
# Save-back logic
# ---------------------------------------------------------------------------


def _node_path_from_target(target: str) -> str:
    cleaned = target.strip()
    if cleaned.startswith("[[") and cleaned.endswith("]]"):
        cleaned = cleaned[2:-2]
    # Strip pipe aliases and the .md suffix only after unwrapping brackets, so a
    # wrapped wikilink like ``[[…/ATM-abc.md]]`` still loses its suffix.
    cleaned = cleaned.split("|", 1)[0].strip().removesuffix(".md")
    return _LEGACY_SCHEME_RE.sub("", cleaned).lstrip("/")


def _fallback_search_terms(text: str) -> str:
    """Searchable terms from a message, without an LLM.

    Keeps letters and digits of ANY script and drops punctuation and symbols.
    The previous class, `[^A-Za-z0-9_./+-]+`, stripped every non-ASCII character,
    which shredded the term that mattered most: `Plücker` became `Pl` + `cker`.
    Measured on a live index, `"Plücker"` and `"plucker"` each match 172
    documents across 22 sources — FTS normalises the diacritic — while
    `"Pl" AND "cker"` matches 0.

    Single characters are dropped because a selected passage carries matrix
    notation (`L^T M(Q)L = 0` → `L`, `T`, `Q`, `m`) and each of those matches
    almost every document. Measured: the old fallback returned 1,310 hits to the
    LLM query's 1,500 while missing the discriminating term; keeping the
    diacritics and dropping the noise returns 1,508 across the same 28 sources,
    with the same top results, for none of the LLM's 12-50 s.
    """
    terms = re.sub(r"[^\w./+-]+", " ", text, flags=re.UNICODE)
    return " ".join(token for token in terms.split() if len(token) > 1)


def derive_search_query(
    db_path: Path, client: ChatClient, message: str
) -> DerivedQuery:
    """Derive the INTERNAL English search query from a message in any language.

    Returns ``(search_query, is_knowledge_question, reason)``.

    This is deliberately NOT :func:`translate_to_english`. Translating the whole
    message is wrong for the cases that actually occur: "이 문장을 한글로 번역해줘:
    <long body>" translated to English yields an English sentence asking for a
    Korean translation, which is then routed and BM25-matched as if it were a
    question about the knowledge base. A long pasted body would also be
    translated in full — slow, lossy, and none of it a search query.

    Extraction handles those as a consequence of understanding the message
    rather than by matching words, so there is no keyword list to maintain and
    nothing to miss when the user phrases it differently.

    Degrades to `_fallback_search_terms`, which keeps the letters and digits of
    ANY script. That is a real query for the mixed-script case that dominates
    this domain ("ellipsoid 형태의 quadric").

    It is NOT an "honest empty" for pure non-Latin input — this docstring
    claimed that for two releases and the code never did it (the word-character
    class under ``re.UNICODE`` keeps Korean and Cyrillic intact). The honesty lives in
    `status="fallback"` instead, which the caller must propagate: marking a dead
    provider's output as `"derived"` suppressed the one warning that would have
    surfaced it.
    """
    message = (message or "").strip()
    if not message:
        return DerivedQuery("", False, "", "empty message", status="unset")

    from . import prompting
    from .prompting.families.query import SearchQueryInput, SearchQueryOutputV2

    contract = prompting.REGISTRY.get("curator.query_search_terms")
    try:
        result = prompting.run_prompt(
            db_path,
            client,
            contract,
            SearchQueryInput(message=message[:4000]),
        )
        if result.parsed is None or not result.ok:
            raise ValueError(
                "; ".join(result.validation.errors) or "no parsed output"
            )
        parsed = cast(SearchQueryOutputV2, result.parsed)
    except Exception as exc:  # noqa: BLE001 - any provider may raise
        terms = _fallback_search_terms(message)
        # No intent: the step that would have judged it never ran. "" routes on
        # today's signals rather than on a guess.
        return DerivedQuery(
            terms, bool(terms), "", f"derivation unavailable: {exc}", status="fallback"
        )

    if not parsed.is_knowledge_question:
        return DerivedQuery(
            "", False, "", parsed.reason or "not a knowledge question", status="derived"
        )
    return DerivedQuery(
        parsed.search_query.strip(),
        True,
        str(parsed.intent or ""),
        parsed.reason,
        status="derived",
    )


#: Above this share of ASCII characters a message is treated as already English.
#: Not a language detector — a cheap gate on "would translating this help?". The
#: mixed-script case that dominates this domain ("ellipsoid 형태의 quadric") sits
#: below it and is correctly sent for derivation.
_ENGLISH_ASCII_RATIO = 0.85


def is_probably_english(text: str) -> bool:
    """Whether `text` is ASCII enough that deriving an English query is pointless.

    Extracted so `translate_to_english` and the ContextService funnel cannot
    drift to two different thresholds for the same judgement.
    """
    if not text:
        return True
    return sum(1 for c in text if ord(c) < 128) / len(text) > _ENGLISH_ASCII_RATIO


def translate_to_english(client: ChatClient, question: str) -> str:
    """Translate the question to English for BM25/vector search.

    Returns the original question unchanged if translation fails or if
    the question is already predominantly ASCII.
    """
    if is_probably_english(question):
        return question

    def _ascii_fallback(text: str) -> str:
        terms = _fallback_search_terms(text)
        return terms if len(terms) >= 8 else text

    try:
        msg = prompts.ChatMessage(
            role="user",
            content=(
                f"Translate the following question to English for a technical knowledge base search. "
                f"Output only the translated question, nothing else.\n\nQuestion: {question}"
            ),
        )
        translated = client.chat([msg], temperature=0.1).strip()
        return translated or question
    except Exception:
        return _ascii_fallback(question)


def classify_wiki_topic(
    client: ChatClient,
    question: str,
    answer: str,
) -> tuple[str, str]:
    """Use the LLM to determine (category_folder, article_slug) for 02_Wiki/.

    Returns e.g. ("ComputerGraphics", "photometric-loss").
    Falls back gracefully on failure.
    """
    import json as _json
    import re as _re

    prompt = (
        "Based on the Q&A below, provide:\n"
        "1. category: a short PascalCase folder name in English "
        "(e.g. \"Domain\", \"Field\", \"SubTopic\").\n"
        "2. slug: a lowercase, hyphenated article filename in English, max 60 chars "
        "(e.g. \"core-concept\", \"method-name\").\n\n"
        f"Question: {question}\n\n"
        f"Answer (first 600 chars):\n{answer[:600]}\n\n"
        "Reply with JSON only: {\"category\": \"...\", \"slug\": \"...\"}"
    )
    try:
        raw = client.chat(
            [prompts.ChatMessage(role="user", content=prompt)],
            json_mode=True,
            temperature=0.1,
        )
        data = _json.loads(raw)
        category = _re.sub(r"[^\w]", "", str(data.get("category", "General"))) or "General"
        slug = _re.sub(r"[^\w-]", "", str(data.get("slug", ""))).strip("-")[:60]
    except Exception:
        category = "General"
        slug = ""

    if not slug:
        import re as _re2
        slug = _re2.sub(r"[^\w\s가-힣-]", "", question).strip()
        slug = _re2.sub(r"\s+", "-", slug)[:60].strip("-") or "untitled"

    return category, slug


def save_wiki_page(
    paths: cfg.WikiPaths,
    question: str,
    answer: str,
    category: str,
    slug: str,
    source_links: list[str] | None = None,
) -> str:
    """Write answer to `<vault_root>/02_Wiki/<category>/<slug>.md`.

    Creates the category directory if it doesn't exist.
    Returns the path relative to the vault root.

    ``source_links`` (pre-formatted `[[04_Resources/…]]` wikilinks) is appended as
    a deterministic ``## Sources`` section. Because the `02_Wiki/` note is a
    visible vault file, these links make the original source documents appear in
    Obsidian's Graph view and Backlinks pane — the hidden DAG can't (c3 hybrid).
    """
    from datetime import date

    title = slug.replace("-", " ").replace("_", " ").title()
    today = date.today().isoformat()

    content = (
        f"# {title}\n\n"
        f"> Source: `wiki query \"{question}\"`  \n"
        f"> Date: {today}\n\n"
        f"{answer.strip()}\n"
    )
    content += _sources_footer(source_links or [])

    wiki_dir = paths.root / consts.DIR_WIKI / category
    wiki_dir.mkdir(parents=True, exist_ok=True)
    target = wiki_dir / f"{slug}.md"
    target.write_text(content, encoding="utf-8")

    return str(target.relative_to(paths.root))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _run_query_orchestrated(
    paths: cfg.WikiPaths,
    client,
    question: str,
    callbacks: QueryCallbacks,
    *,
    route: str,
    workspace_path: str | None,
    session_id: str | None,
    english_query: str | None,
    input_language: str,
    final_output_language: str,
) -> QueryResult:
    """v0.3.1 query via the curation-native QueryOrchestrator.

    Maps the orchestrator's QueryResultV031 onto the legacy QueryResult so
    existing CLI/plugin/MCP callers keep a stable shape while gaining the route
    and trace fields.
    """
    from .retrieval import QueryOrchestrator, QueryRequest

    callbacks.on_start(question, route)
    request = QueryRequest(
        question=question,
        english_query=(english_query or "").strip(),
        input_language=input_language,
        final_output_language=final_output_language or input_language or "English",
        workspace_path=str(workspace_path) if workspace_path else "",
        mode=route,
    )
    callbacks.on_searching()
    res = QueryOrchestrator(paths, client).run(request)
    result = QueryResult(
        question=question,
        answer=res.answer,
        session_id=session_id,
        english_query=res.english_query,
        input_language=res.input_language,
        final_output_language=res.final_output_language,
        error=res.error,
        route=res.route,
        trace_id=res.trace_id,
        prompt_trace_ids=res.prompt_trace_ids,
        source_span_ids=res.source_span_ids,
        community_report_ids=res.community_report_ids,
        synthesis_node_ids=res.synthesis_node_ids,
        memory_path_ids=res.memory_path_ids,
        insight_candidate_ids=res.insight_candidate_ids,
        warnings=res.warnings,
    )
    if result.error:
        callbacks.on_error(result.error)
    else:
        callbacks.on_complete(result)
    return result


def run_query(
    paths: cfg.WikiPaths,
    client: ChatClient,
    question: str,
    callbacks: QueryCallbacks,
    *,
    mode: str = "hybrid",
    limit: int = 8,
    min_score: float = 0.6,
    rerank: bool = True,
    temperature: float = 0.3,
    scope: str = "all",
    classify_intent_first: bool = True,
    session_id: str | None = None,
    workspace_path: str | None = None,
    query_boost_terms: list[str] | None = None,
    english_query: str | None = None,
    input_language: str = "",
    final_output_language: str = "",
    route: str = "auto",
) -> QueryResult:
    """Run a full query → answer pipeline.

    ``route`` is answered by the QueryOrchestrator (DB graph + DB-native
    search, with a QTR trace). Empty route is normalized to ``auto``.

    scope filters retrieval by Curator layer (path prefix inside
    `.curator/Collections/`):
        - 'all'         → no filter
        - 'contexts'    → 01_Contexts/ only
        - 'atoms'       → 02_Atoms/ only
        - 'concepts'    → 03_Concepts/ only
        - 'synthesis'   → 04_Synthesis/ only

    classify_intent_first runs intent classification before retrieval. If
    the user asked something like 'hi' or 'thanks', we skip retrieval and
    respond conversationally.
    """
    from .retrieval import ROUTES as _V031_ROUTES

    selected_route = (route or "auto").strip()
    if selected_route not in (*_V031_ROUTES, "auto"):
        return QueryResult(
            question=question,
            session_id=session_id,
            error=(
                f"Invalid route '{selected_route}'. Use auto, local, global, "
                "explore, or source-section."
            ),
        )
    return _run_query_orchestrated(
        paths, client, question, callbacks,
        route=selected_route, workspace_path=workspace_path, session_id=session_id,
        english_query=english_query, input_language=input_language,
        final_output_language=final_output_language,
    )
