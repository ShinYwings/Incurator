from __future__ import annotations

import logging
import time
from typing import Any

from .. import config as cfg
from .. import constants as consts
from .. import db, llm, query, search


_log = logging.getLogger(__name__)

def curator_query(
    paths: cfg.WikiPaths,
    *,
    question: str,
    workspace_path: str = "",
    force_new: bool = False,
    input_language: str = "",
    english_query: str = "",
    final_output_language: str = "",
) -> dict[str, Any]:
    start = time.monotonic()
    effective_final_output_language = final_output_language or input_language or "same_as_input"

    try:
        config = cfg.load_config(paths)
    except Exception as exc:
        return {"ok": False, "question": question, "error": f"Config error: {exc}"}

    l3_complete = paths.concepts.exists() and any(paths.concepts.glob(f"{consts.PREFIX_L3}-*.md"))
    if not l3_complete:
        try:
            fallback_query = english_query or question
            raw_results = search.query(paths, fallback_query, mode="lex", limit=8, min_score=0.0, hydrate=False, rerank=False)
            fallback_hits = [
                {"path": hit.full_path, "title": hit.title, "score": hit.score, "snippet": hit.snippet}
                for hit in raw_results.hits
            ]
        except Exception:
            _log.debug("L3-incomplete lexical fallback search failed", exc_info=True)
            fallback_hits = []
        return {
            "ok": True,
            "answer": "",
            "question": question,
            "input_language": input_language,
            "english_query": english_query,
            "final_output_language": effective_final_output_language,
            "fallback": "l3_incomplete",
            "fallback_hits": fallback_hits,
            "trace": {
                "matched_concepts": [],
                "source_ids": [],
                "source_paths": [hit.get("path", "") for hit in fallback_hits],
                "latency_ms": int((time.monotonic() - start) * 1000),
                "l3_complete": False,
            },
        }

    try:
        from ..retrieval import QueryOrchestrator, QueryRequest

        with llm.build_client(config) as client:
            result = QueryOrchestrator(paths, client).run(
                QueryRequest(
                    question=question,
                    english_query=english_query,
                    input_language=input_language,
                    final_output_language=effective_final_output_language,
                    workspace_path=workspace_path,
                    mode="auto",
                )
            )
    except Exception as exc:
        return {
            "ok": False,
            "question": question,
            "input_language": input_language,
            "english_query": english_query,
            "final_output_language": effective_final_output_language,
            "error": f"Query pipeline error: {exc}",
        }

    if not result.ok:
        return {
            "ok": False,
            "question": question,
            "input_language": input_language,
            "english_query": result.english_query or english_query,
            "final_output_language": result.final_output_language or effective_final_output_language,
            "error": result.error or "Query returned no answer",
        }

    trace = db.get_query_trace(paths.state_db, result.trace_id)
    context_trace = {}
    if trace is not None:
        context_trace = (trace.get("retrieval_trace") or {}).get("context_service", {})
    context_pack_id = context_trace.get("pack_id", None) or None
    context_snapshot = context_trace.get("snapshot", None) if context_pack_id is not None else None
    context_budget = context_trace.get("budget", None) if context_pack_id is not None else None
    source_paths: list[str] = []
    if result.source_span_ids:
        for span in db.get_source_spans_by_ids(paths.state_db, result.source_span_ids):
            relpath = span.get("relpath", "")
            if relpath and relpath not in source_paths:
                source_paths.append(relpath)

    # Sessionless: no generated L4 file is written; return the answer + trace only.
    return {
        "ok": True,
        "answer": result.answer,
        "question": question,
        "input_language": input_language,
        "english_query": result.english_query or english_query,
        "final_output_language": result.final_output_language or effective_final_output_language,
        "route": result.route,
        "trace_id": result.trace_id,
        "pack_id": context_pack_id,
        "snapshot": context_snapshot,
        "budget": context_budget,
        "prompt_trace_ids": result.prompt_trace_ids,
        "source_span_ids": result.source_span_ids,
        "synthesis_node_ids": result.synthesis_node_ids,
        "community_report_ids": result.community_report_ids,
        "memory_path_ids": result.memory_path_ids,
        "insight_candidate_ids": result.insight_candidate_ids,
        "warnings": result.warnings,
        "trace": {
            "matched_concepts": [],
            "source_ids": [],
            "source_paths": source_paths,
            "synthesis_node_ids": result.synthesis_node_ids,
            "community_report_ids": result.community_report_ids,
            "memory_path_ids": result.memory_path_ids,
            "insight_candidate_ids": result.insight_candidate_ids,
            "prompt_trace_ids": result.prompt_trace_ids,
            "source_span_ids": result.source_span_ids,
            "trace_id": result.trace_id,
            "route": result.route,
            "pack_id": context_pack_id,
            "snapshot": context_snapshot,
            "budget": context_budget,
            "latency_ms": int((time.monotonic() - start) * 1000),
            "l3_complete": l3_complete,
        },
    }


def promote_answer(
    paths: cfg.WikiPaths,
    *,
    question: str,
    answer: str,
    workspace_path: str = "",
    source_span_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Promote a sessionless Q&A answer into a durable `02_Wiki/` page.

    v0.3.1: queries are sessionless (no generated L4 file), so promotion takes the
    question + answer text directly and writes only `02_Wiki/` (source truth is
    never touched). When ``source_span_ids`` from the answer's trace are provided,
    a deterministic ``## Sources`` section of `[[04_Resources/…]]` links is
    appended so the original source documents appear in Obsidian's Graph view and
    Backlinks pane (c3 hybrid: native links only via the visible `02_Wiki/` note).
    """
    if not (question.strip() and answer.strip()):
        return {"ok": False, "error": "question and answer are required"}

    category = "General"
    slug = ""
    try:
        config = cfg.load_config(paths)
        with llm.build_client(config) as client:
            category, slug = query.classify_wiki_topic(client, question, answer)
    except Exception:
        _log.debug("Wiki topic classification unavailable; using deterministic slug", exc_info=True)

    if not slug:
        import re

        slug = re.sub(r"[^\w\s-]", "", question).strip()
        slug = re.sub(r"\s+", "-", slug)[:60].strip("-") or "note"

    source_links = query.resolve_source_links(paths, source_span_ids or [])
    try:
        wiki_path = query.save_wiki_page(
            paths, question, answer, category, slug, source_links=source_links
        )
    except Exception as exc:
        return {"ok": False, "error": f"Failed to write wiki page: {exc}"}

    return {"ok": True, "promoted_to": wiki_path}
