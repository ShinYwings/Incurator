"""Query pipeline: search → synthesize → (optionally) save back as a page.

Flow:
  1. Call search.query() to get top-K matching Curator pages.
  2. Build a synthesis prompt with the matches as context.
  3. Stream the LLM's answer via the active client.
  4. Provide a streaming answer using markdown citations.
  5. Optionally save the answer as
     `.curator/Collections/04_Exhibitions/EXH-<UUID8>.md` and update
     index.md + log.md.

Callbacks let the CLI render progress (search phase, synthesis streaming).
"""

from __future__ import annotations
from . import constants as consts

import uuid
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import config as cfg
from . import constants as consts
from . import db
from . import page_writer
from . import prompts
from . import search
from .llm import (
    LLMError,
    ModelNotFound,
    OllamaClient,
    OllamaNotRunning,
)

MAX_SYNTHESIS_SOURCE_CHARS = 24_000


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class QueryResult:
    """The outcome of a single `wiki query` invocation."""

    question: str
    answer: str = ""
    hits: list[search.SearchHit] = field(default_factory=list)
    saved_path: str | None = None   # if --save-as was used
    session_id: str | None = None
    error: str | None = None

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

    def on_saved(self, saved_path: str) -> None: ...

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
3. **Exhibition Authority**: Nodes prefixed with `EXH-` (Exhibitions) represent human-verified or agent-refined "final truths." If information in an `EXH-` node conflicts with data in a `CTX-`, `ATM-`, or `CON-` node, **ALWAYS prioritize the Exhibition's content** as the most authoritative.
4. **Link-Based Reasoning**: Use the `[[wikilinks]]` to trace provenance. If a Concept (`CON-`) is used, mention its supporting Exhibition if available.
   layer prefix exactly as shown in the source headers, e.g.
   [[01_Contexts/CTX-a1b2c3d4]], [[02_Atoms/ATM-9f8e7d6c]],
   [[03_Concepts/CON-12345678]], [[04_Exhibitions/EXH-abcdef01]].
3. Prefer citing L2 Atoms for factual claims, L3 Concepts for thematic groupings,
   and L4 Exhibitions for cross-domain conclusions. Trace back to L2 if a higher
   layer's confidence_score is below 0.90.
4. If the sources don't contain enough information to answer confidently,
   say so explicitly and identify which layer is missing.
5. Be concise but substantive. Write in clean markdown.
6. Do NOT include YAML frontmatter, preamble like "Based on the sources:",
   or meta-commentary about your process.
7. LANGUAGE: You MUST answer the question in the SAME language that the user used to ask the question. If the user asks in Korean, answer in Korean.
"""


def _build_synthesis_user_prompt(
    question: str, results: search.SearchResults
) -> str:
    """Construct the user message for Qwen3 with the search results as context."""
    lines: list[str] = []
    lines.append(f"Question: {question}")
    lines.append("")
    lines.append(f"Here are the {len(results)} most relevant wiki pages:")
    lines.append("")

    for i, hit in enumerate(results.hits, start=1):
        lines.append(f"--- Source {i} ---")
        # Use the full hit path so the LLM sees how to wikilink it.
        # Strip the qmd:// URI prefix and collection name so the link is
        # clean and Obsidian-friendly.
        import re as _re
        raw_path = hit.full_path.removesuffix(".md")
        page_link = _re.sub(r"^/?qmd://[^/]+/", "", raw_path).lstrip("/")
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
    cleaned = target.removesuffix(".md")
    if cleaned.startswith("[[") and cleaned.endswith("]]"):
        cleaned = cleaned[2:-2]
    cleaned = cleaned.split("|", 1)[0].strip()
    import re as _re
    return _re.sub(r"^/?qmd://[^/]+/", "", cleaned).lstrip("/")


def _concept_paths_for_atom(paths: cfg.WikiPaths, atom_id: str) -> list[str]:
    found: list[str] = []
    if not paths.concepts.exists():
        return found
    for concept_path in sorted(paths.concepts.glob(f"{consts.PREFIX_L3}-*.md")):
        page = page_writer.read_page(concept_path)
        if not page:
            continue
        targets = page_writer.extract_relation_targets(page.body, prefix=f"{consts.LAYER_L2}/")
        if f"{consts.LAYER_L2}/{atom_id}" in targets:
            found.append(f"{consts.LAYER_L3}/{concept_path.stem}")
    return found


def _atom_ids_for_context(paths: cfg.WikiPaths, context_id: str) -> list[str]:
    found: list[str] = []
    if not paths.atoms.exists():
        return found
    for atom_path in sorted(paths.atoms.glob(f"{consts.PREFIX_L2}-*.md")):
        page = page_writer.read_page(atom_path)
        if not page:
            continue
        raw_parent = page.frontmatter.get("parent_source", [])
        parents = raw_parent if isinstance(raw_parent, list) else [raw_parent]
        parent_ids = {
            _node_path_from_target(str(parent)).rsplit("/", 1)[-1]
            for parent in parents
            if parent
        }
        if context_id in parent_ids:
            found.append(atom_path.stem)
    return found


def _derive_core_concepts(paths: cfg.WikiPaths, answer: str, hits: list[search.SearchHit]) -> list[str]:
    """Resolve query citations/hits to L3 Concept paths for valid L4 metadata."""
    core_concepts: list[str] = []
    atom_ids: list[str] = []
    context_ids: list[str] = []

    targets = [hit.full_path for hit in hits]
    targets.extend(page_writer.extract_wikilink_targets(answer))

    for target in targets:
        cleaned = _node_path_from_target(target)
        if cleaned.startswith(f"{consts.LAYER_L3}/") and cleaned not in core_concepts:
            core_concepts.append(cleaned)
        elif cleaned.startswith(f"{consts.LAYER_L2}/"):
            atom_id = cleaned.rsplit("/", 1)[-1]
            if atom_id not in atom_ids:
                atom_ids.append(atom_id)
        elif cleaned.startswith(f"{consts.LAYER_L1}/"):
            context_id = cleaned.rsplit("/", 1)[-1]
            if context_id not in context_ids:
                context_ids.append(context_id)

    for context_id in context_ids:
        for atom_id in _atom_ids_for_context(paths, context_id):
            if atom_id not in atom_ids:
                atom_ids.append(atom_id)

    for atom_id in atom_ids:
        for concept_path in _concept_paths_for_atom(paths, atom_id):
            if concept_path not in core_concepts:
                core_concepts.append(concept_path)

    return core_concepts


def _save_curation_page(
    paths: cfg.WikiPaths,
    question: str,
    answer: str,
    title: str,
    hits: list[search.SearchHit],
    session_id: str | None = None,
    workspace_project: str | None = None,
    workspace_path: str | None = None,
    workspace_id: str = "default",
    cache_key: str | None = None,
    ephemeral: bool = False,
) -> str:
    """Write the answer to `.curator/Collections/04_Exhibitions/EXH-<UUID8>.md`,
    rebuild index, append log.

    Returns the relative path (relative to `.curator/Collections/`) of the
    saved page.
    """
    import hashlib as _hashlib

    exh_id = f"{consts.PREFIX_L4}-{uuid.uuid4().hex[:8]}"
    qry_id = session_id if session_id else f"QRY-{uuid.uuid4().hex[:8]}"
    today = page_writer.today_iso()

    core_concepts = _derive_core_concepts(paths, answer, hits)
    if not core_concepts:
        raise ValueError("Cannot save query Exhibition: no related L3 Concepts were found.")

    if cache_key is None:
        cache_key = _hashlib.sha256(question.encode()).hexdigest()[:16]

    display_title = (title or question).strip()
    if len(display_title) > 80:
        display_title = display_title[:77] + "..."

    parsed = page_writer.parse_page(answer.strip())
    base_frontmatter: dict = {
        "id": exh_id,
        "type": consts.TYPE_L4,
        "core_concepts": core_concepts,
        "confidence_score": 0.70,
        "last_updated": today,
        "workspace_id": workspace_id,
        "query_session": qry_id,
        "exhibition_origin": "query_gen",
        "ephemeral": ephemeral,
        "question": question,
        "cache_key": cache_key,
        "is_verified_by_human": False,
    }
    if workspace_path:
        base_frontmatter["workspace_path"] = workspace_path
    if workspace_project:
        base_frontmatter["workspace"] = workspace_project

    if not parsed.frontmatter:
        parsed.frontmatter = base_frontmatter
        parsed.body = f"# {display_title}\n\n{answer.strip()}"
    else:
        parsed.frontmatter.update(base_frontmatter)

    final_path = paths.exhibitions / f"{exh_id}.md"
    page_writer.write_page(final_path, parsed.to_markdown())

    page_writer.rebuild_index(paths, today)
    page_writer.append_log_entry(
        paths,
        today,
        "query",
        display_title,
        [
            f"saved: [[{consts.LAYER_L4}/{exh_id}]]",
            f"query_session: {session_id}" if session_id else "query_session: none",
            f"consulted: {len(hits)} page(s)",
        ],
    )

    return f"{consts.LAYER_L4}/{exh_id}.md"


def update_curation_page(
    paths: cfg.WikiPaths,
    exh_path: Path,
    question: str,
    answer: str,
    hits: list[search.SearchHit],
) -> None:
    """Append a new Q&A turn to an existing session Exhibition and refresh metadata."""
    today = page_writer.today_iso()
    page = page_writer.read_page(exh_path)
    if page is None:
        return
    new_concepts = _derive_core_concepts(paths, answer, hits)
    existing = page.frontmatter.get("core_concepts") or []
    merged = list(dict.fromkeys(existing + new_concepts))
    page.frontmatter["core_concepts"] = merged
    page.frontmatter["last_updated"] = today
    if answer.strip():
        page.body = page.body.rstrip() + f"\n\n## Follow-up: {question}\n\n{answer.strip()}"
    page_writer.write_page(exh_path, page.to_markdown())
    page_writer.rebuild_index(paths, today)


def translate_to_english(client: OllamaClient, question: str) -> str:
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
    client: OllamaClient,
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


def run_query(
    paths: cfg.WikiPaths,
    client: OllamaClient,
    question: str,
    callbacks: QueryCallbacks,
    *,
    mode: str = "hybrid",
    limit: int = 8,
    min_score: float = 0.6,
    rerank: bool = True,
    save_as: str | None = None,
    temperature: float = 0.3,
    scope: str = "all",
    classify_intent_first: bool = True,
    session_id: str | None = None,
    workspace_project: str | None = None,
    query_boost_terms: list[str] | None = None,
    pinned_exhibition_id: str | None = None,
    ephemeral_exhibition: bool = False,
) -> QueryResult:
    """Run a full query → answer pipeline.

    scope filters retrieval by Curator layer (path prefix inside
    `.curator/Collections/`):
        - 'all'         → no filter
        - 'contexts'    → 01_Contexts/ only
        - 'atoms'       → 02_Atoms/ only
        - 'concepts'    → 03_Concepts/ only
        - 'exhibitions' → 04_Exhibitions/ only

    classify_intent_first runs intent classification before retrieval. If
    the user asked something like 'hi' or 'thanks', we skip retrieval and
    respond conversationally.
    """
    callbacks.on_start(question, mode)

    curator_persona = cfg.get_curator_persona(cfg.load_config(paths))

    # 0a. Translate to English first — intent classification is more accurate
    #     on English text, and search backends (BM25/vector) expect English.
    search_question = translate_to_english(client, question)
    base_search_question = search_question

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
            result = QueryResult(question=question, answer=reply, hits=[], session_id=session_id)
            callbacks.on_complete(result)
            return result

    # 0c. Unload Ollama model from VRAM before qmd runs.
    #     qmd's local llama-cpp model needs GPU memory for query expansion;
    #     if Ollama is still loaded the two models compete for the same VRAM.
    #     Ollama will auto-reload when synthesis begins in step 2.
    if hasattr(client, "unload"):
        client.unload()

    # 1. Search the single Curator collection
    callbacks.on_searching()
    layer_prefix = {
        "contexts":    f"{consts.LAYER_L1}/",
        "atoms":       f"{consts.LAYER_L2}/",
        "concepts":    f"{consts.LAYER_L3}/",
        "exhibitions": f"{consts.LAYER_L4}/",
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
        # Apply layer-prefix filter post-hoc — qmd has no native path filter,
        # and over-fetching a few extra hits is cheaper than splitting into
        # multiple collections.
        if layer_prefix:
            found.hits = [h for h in found.hits if h.full_path.startswith(layer_prefix)]
        return found

    try:
        results = _search_for(search_question)
        if len(results) == 0 and search_question != base_search_question:
            results = _search_for(base_search_question)

        # Prioritize Exhibitions (L4) as the primary source of truth in the synthesis context
        results.hits.sort(key=lambda h: (not h.full_path.startswith(f"{consts.LAYER_L4}/"), -h.score))
    except search.QmdNotInstalled as e:
        result = QueryResult(question=question, session_id=session_id, error=str(e))
        callbacks.on_error(result.error)
        return result
    except search.SearchBackendError as e:
        result = QueryResult(question=question, session_id=session_id, error=f"Search failed: {e}")
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
            error="No matching wiki pages found. Try a different query or "
            "curate more sources.",
        )
        callbacks.on_error(result.error)
        return result

    # 2. Synthesize
    callbacks.on_synthesizing()
    agent_context = curator_persona.get("text", "")

    pinned_content = ""
    if pinned_exhibition_id:
        pinned_path = paths.exhibitions / f"{pinned_exhibition_id}.md"
        if pinned_path.exists():
            page = page_writer.read_page(pinned_path)
            if page:
                pinned_content = f"## Pinned Workspace Exhibition ({pinned_exhibition_id})\n{page.body}\n\n"

    synthesis_user_content = _build_synthesis_user_prompt(question, results)
    if pinned_content:
        synthesis_user_content = f"{pinned_content}{synthesis_user_content}"

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
            question=question, hits=results.hits, session_id=session_id, error=str(e)
        )
        callbacks.on_error(result.error)
        return result
    except LLMError as e:
        result = QueryResult(
            question=question, hits=results.hits, session_id=session_id, error=f"LLM error: {e}"
        )
        callbacks.on_error(result.error)
        return result

    answer = page_writer.strip_llm_noise("".join(answer_parts))

    # 3. Optionally save as a synthesis page
    saved_path: str | None = None
    if save_as:
        try:
            saved_path = _save_curation_page(
                paths,
                question,
                answer,
                save_as,
                results.hits,
                session_id=session_id,
                workspace_project=workspace_project,
                ephemeral=ephemeral_exhibition,
            )
            callbacks.on_saved(saved_path)
        except OSError as e:
            result = QueryResult(
                question=question,
                answer=answer,
                hits=results.hits,
                session_id=session_id,
                error=f"Failed to save synthesis page: {e}",
            )
            callbacks.on_error(result.error)
            return result
        except ValueError:
            # Skip saving silently if no L3 Concepts were found, preserving the query answer.
            pass

    result = QueryResult(
        question=question,
        answer=answer,
        hits=results.hits,
        saved_path=saved_path,
        session_id=session_id,
    )
    callbacks.on_complete(result)
    return result
