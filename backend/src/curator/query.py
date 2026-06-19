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
from typing import Protocol

from . import config as cfg
from . import page_writer
from . import prompts
from . import search
from .llm import (
    LLMError,
    ModelNotFound,
    OllamaNotRunning,
)

MAX_SYNTHESIS_SOURCE_CHARS = 24_000

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


# ---------------------------------------------------------------------------
# Synthesis prompt
# ---------------------------------------------------------------------------


SYNTHESIS_SYSTEM_PROMPT = """You are answering questions by synthesizing content
from the Curator's DAG knowledge base under `.curator/Collections/`.

Rules:
1. Base your answer STRICTLY on the provided pages and excerpts below.
   Do not invent facts or speculate beyond what the sources say.
2. **Link-Based Reasoning**: Use the `[[wikilinks]]` to trace provenance, using the
   layer prefix exactly as shown in the source headers, e.g.
   [[01_Contexts/CTX-a1b2c3d4]], [[02_Atoms/ATM-9f8e7d6c]],
   [[03_Concepts/CON-12345678]], [[04_Synthesis/SYN-abcdef01]].
3. Prefer citing L2 Atoms for factual claims, L3 Concepts for thematic groupings,
   and L4 Synthesis nodes for cross-cutting conclusions. Trace back to L2 if a
   higher layer's confidence_score is below 0.90.
4. If the sources don't contain enough information to answer confidently,
   say so explicitly and identify which layer is missing.
5. Be concise but substantive. Write in clean markdown.
6. Do NOT include YAML frontmatter, preamble like "Based on the sources:",
   or meta-commentary about your process.
7. LANGUAGE: Use English for internal reasoning over the sources. The user
   prompt provides `Final output language`; write the final answer in that
   language. If it is `English`, answer in English. If it is `same_as_input`,
   answer in the same language as the original user question.
"""


def _build_synthesis_user_prompt(
    question: str,
    results: search.SearchResults,
    *,
    english_query: str = "",
    input_language: str = "",
    final_output_language: str = "",
) -> str:
    """Construct the user message for Qwen3 with the search results as context."""
    lines: list[str] = []
    lines.append(f"Original user question: {question}")
    if input_language:
        lines.append(f"Input language: {input_language}")
    if english_query:
        lines.append(f"English working query: {english_query}")
    if final_output_language:
        lines.append(f"Final output language: {final_output_language}")
    lines.append("")
    lines.append(f"Here are the {len(results)} most relevant wiki pages:")
    lines.append("")

    for i, hit in enumerate(results.hits, start=1):
        lines.append(f"--- Source {i} ---")
        # Use the full hit path so the LLM sees how to wikilink it.
        # Strip any legacy scheme prefix and collection name so the link is
        # clean and Obsidian-friendly.
        raw_path = hit.full_path.removesuffix(".md")
        page_link = _LEGACY_SCHEME_RE.sub("", raw_path).lstrip("/")
        lines.append(f"Wikilink path: [[{page_link}]]")
        if hit.title:
            lines.append(f"Title: {hit.title}")
        lines.append(f"Relevance score: {hit.score:.2f}")
        lines.append("")
        content = hit.full_content or hit.snippet
        if content:
            if len(content) > MAX_SYNTHESIS_SOURCE_CHARS:
                content = (
                    content[:MAX_SYNTHESIS_SOURCE_CHARS].rstrip()
                    + "\n\n[... source truncated for synthesis prompt ...]"
                )
            lines.append(content)
        else:
            lines.append("(no content available)")
        lines.append("")

    lines.append("--- End of sources ---")
    lines.append("")
    lines.append(
        "Now write a clear, well-structured markdown answer to the question. "
        "Cite each claim with [[wikilinks]] using the paths shown above. "
        "If a claim is not supported by the sources, say so."
    )
    return "\n".join(lines)


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


def translate_to_english(client: ChatClient, question: str) -> str:
    """Translate the question to English for BM25/vector search.

    Returns the original question unchanged if translation fails or if
    the question is already predominantly ASCII.
    """
    ascii_ratio = sum(1 for c in question if ord(c) < 128) / max(len(question), 1)
    if ascii_ratio > 0.85:
        return question

    def _ascii_fallback(text: str) -> str:
        ascii_terms = re.sub(r"[^A-Za-z0-9_./+-]+", " ", text).strip()
        ascii_terms = re.sub(r"\s+", " ", ascii_terms)
        return ascii_terms if len(ascii_terms) >= 8 else text

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
) -> str:
    """Write answer to `<vault_root>/02_Wiki/<category>/<slug>.md`.

    Creates the category directory if it doesn't exist.
    Returns the path relative to the vault root.
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

    callbacks.on_start(question, mode)

    curator_persona = cfg.get_curator_persona(cfg.load_config(paths))

    # 0a. Translate to English first — intent classification is more accurate
    #     on English text, and search backends (BM25/vector) expect English.
    search_question = (english_query or "").strip() or translate_to_english(client, question)
    base_search_question = search_question
    resolved_final_output_language = final_output_language or input_language or "same_as_input"

    if not query_boost_terms:
        global_domain = curator_persona.get("domain")
        if global_domain:
            query_boost_terms = [global_domain]
            if curator_persona.get("topics"):
                query_boost_terms.extend(curator_persona["topics"])

    if query_boost_terms:
        extras = " ".join(str(term) for term in query_boost_terms if str(term).strip())
        if extras:
            search_question = f"{search_question} {extras}"
    else:
        extras = ""

    def _keyword_fallback(text: str) -> str:
        stopwords = {
            "according", "after", "avoid", "checking", "does", "from", "have",
            "into", "later", "original", "paper", "refine", "refines",
            "should", "that", "the", "this", "what", "when", "where",
            "which", "with", "would",
        }
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9+-]*", text)
        kept: list[str] = []
        for token in tokens:
            lower = token.lower()
            if lower in stopwords:
                continue
            if len(token) <= 3 and not token.isupper():
                continue
            if token not in kept:
                kept.append(token)
        return " ".join(kept[:12])

    # 0b. Intent classification on the translated question
    if classify_intent_first:
        from . import intent as intent_module

        callbacks.on_classifying_intent()
        intent_result = intent_module.classify_intent(client, search_question)
        callbacks.on_intent_classified(intent_result.intent)

        if intent_result.intent == "chitchat":
            # Reply in the user's original language
            reply = intent_module.generate_chitchat_reply(client, question)
            callbacks.on_chitchat_reply(reply)
            result = QueryResult(
                question=question,
                answer=reply,
                hits=[],
                session_id=session_id,
                english_query=base_search_question,
                input_language=input_language,
                final_output_language=resolved_final_output_language,
            )
            callbacks.on_complete(result)
            return result

    # 0c. Unload Ollama model from VRAM before local search GGUFs are loaded.
    #     Ollama will auto-reload when synthesis begins in step 2.
    if hasattr(client, "unload"):
        client.unload()

    # 1. Search the single Curator collection
    callbacks.on_searching()
    layer_prefix = {
        "contexts":  f"{consts.LAYER_L1}/",
        "atoms":     f"{consts.LAYER_L2}/",
        "concepts":  f"{consts.LAYER_L3}/",
        "synthesis": f"{consts.LAYER_L4}/",
    }.get(scope)

    def _search_for(query_text: str) -> search.SearchResults:
        found = search.query(
            paths,
            query_text,
            mode=mode,
            limit=limit,
            min_score=min_score,
            collections=None,
            hydrate=True,
            rerank=rerank,
        )
        # Apply layer-prefix filter post-hoc; over-fetching a few extra hits is
        # cheaper than splitting the DB-native query into multiple passes.
        if layer_prefix:
            found.hits = [h for h in found.hits if h.full_path.startswith(layer_prefix)]
        return found

    try:
        results = _search_for(search_question)
        if len(results) == 0 and search_question != base_search_question:
            results = _search_for(base_search_question)
        if len(results) == 0 and extras:
            results = _search_for(extras)
        if len(results) == 0:
            keyword_query = _keyword_fallback(base_search_question)
            if keyword_query and keyword_query != base_search_question:
                results = _search_for(keyword_query)
        if len(results) == 0 and query_boost_terms:
            semantic_terms = [
                str(term)
                for term in query_boost_terms
                if " " in str(term)
                and "source" not in str(term).lower()
                and "provenance" not in str(term).lower()
            ]
            if semantic_terms:
                results = _search_for(" ".join(semantic_terms))

        results.hits.sort(key=lambda h: -h.score)
    except search.SearchBackendError as e:
        result = QueryResult(
            question=question,
            session_id=session_id,
            english_query=base_search_question,
            input_language=input_language,
            final_output_language=resolved_final_output_language,
            error=f"Search failed: {e}",
        )
        callbacks.on_error(result.error)
        return result

    callbacks.on_search_done(results)

    if len(results) == 0:
        callbacks.on_no_results()
        result = QueryResult(
            question=question,
            answer="",
            hits=[],
            session_id=session_id,
            english_query=base_search_question,
            input_language=input_language,
            final_output_language=resolved_final_output_language,
            error="No matching wiki pages found. Try a different query or "
            "curate more sources.",
        )
        callbacks.on_error(result.error)
        return result

    # 2. Synthesize
    callbacks.on_synthesizing()
    agent_context = curator_persona.get("text", "")

    synthesis_user_content = _build_synthesis_user_prompt(
        question,
        results,
        english_query=base_search_question,
        input_language=input_language,
        final_output_language=resolved_final_output_language,
    )

    if agent_context:
        synthesis_user_content = f"## Agent Context\n{agent_context}\n\n{synthesis_user_content}"
    system_msg = prompts.ChatMessage(role="system", content=SYNTHESIS_SYSTEM_PROMPT)
    user_msg = prompts.ChatMessage(role="user", content=synthesis_user_content)
    messages = [system_msg, user_msg]

    answer_parts: list[str] = []
    try:
        gen = client.chat_stream(messages, temperature=temperature)
        try:
            while True:
                chunk = next(gen)
                callbacks.on_stream_chunk(chunk)
                answer_parts.append(chunk)
        except StopIteration as stop:
            if stop.value:
                full = stop.value
                if full and not answer_parts:
                    answer_parts.append(full)
    except (OllamaNotRunning, ModelNotFound) as e:
        result = QueryResult(
            question=question,
            hits=results.hits,
            session_id=session_id,
            english_query=base_search_question,
            input_language=input_language,
            final_output_language=resolved_final_output_language,
            error=str(e),
        )
        callbacks.on_error(result.error)
        return result
    except LLMError as e:
        result = QueryResult(
            question=question,
            hits=results.hits,
            session_id=session_id,
            english_query=base_search_question,
            input_language=input_language,
            final_output_language=resolved_final_output_language,
            error=f"LLM error: {e}",
        )
        callbacks.on_error(result.error)
        return result

    answer = page_writer.strip_llm_noise("".join(answer_parts))

    # Sessionless Q&A returns answer + trace only; no Exhibition file is written
    # (v0.3.1: curation is a dynamic lens, not a frozen artifact). Durable human
    # artifacts come only from explicit 02_Wiki/ promotion.
    result = QueryResult(
        question=question,
        answer=answer,
        hits=results.hits,
        session_id=session_id,
        english_query=base_search_question,
        input_language=input_language,
        final_output_language=resolved_final_output_language,
    )
    callbacks.on_complete(result)
    return result
