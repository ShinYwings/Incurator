"""Backend-local JSON API used by the Obsidian plugin.

This module has no MCP dependency. Hidden `wiki plugin ...` commands call these
functions, and the MCP server can be migrated to the same functions later.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from . import config as cfg
from . import constants as consts
from . import db, ingest_raw, llm, query, search, source_tools


def source_row(
    paths: cfg.WikiPaths,
    *,
    source_id: int | None = None,
    relpath: str = "",
    source_path: str = "",
) -> dict[str, Any] | None:
    return db.get_source_row(
        paths.state_db,
        paths.root,
        source_id=source_id,
        relpath=relpath,
        source_path=source_path,
    )


def source_dict(
    paths: cfg.WikiPaths,
    row: dict[str, Any],
    config: dict,
    *,
    light: bool = False,
) -> dict[str, Any]:
    source_id = int(row["id"])
    pages = db.list_source_pdf_pages(paths.state_db, source_id)
    generated = db.list_source_pages(paths.state_db, source_id)

    if light:
        out = dict(row)
        expected_hash = str(row.get("content_hash") or "")
        path = source_tools._row_path(paths, row)
        pending_jobs = db.get_pending_jobs_for_source(paths.state_db, source_id)
        out.update(
            {
                "state": source_tools.derive_source_state(row, pending_jobs),
                "message": "Cached status from database.",
                "current_path": str(path),
                "current_hash": expected_hash,
                "requires_rebind": False,
                "registered": True,
                "source_id": source_id,
                "l1_complete": str(row.get("l1_status") or "") == "done",
                "l2_complete": str(row.get("l2_status") or "") == "done",
                "l3_complete": str(row.get("l3_status") or "") == "done",
                "l4_complete": str(row.get("l4_status") or "") == "done",
                "jobs_pending": pending_jobs,
            }
        )
    else:
        out = source_tools.source_status(paths, row, config)

    out["pdf_page_count"] = len(pages)
    out["page_count"] = len(pages)
    out["generated_pages"] = generated
    return out


def source_status(
    paths: cfg.WikiPaths,
    *,
    file_hash: str = "",
    source_id: int | None = None,
    relpath: str = "",
    source_path: str = "",
    file_path: str = "",
    path: str = "",
    status_filter: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    config = cfg.load_config(paths)
    stats = db.get_stats(paths.state_db)

    if file_hash:
        with db.connect(paths.state_db) as conn:
            row = conn.execute(
                "SELECT * FROM sources WHERE content_hash = ? ORDER BY id DESC LIMIT 1",
                (file_hash,),
            ).fetchone()
        if row is None:
            return {
                "registered": False,
                "source_id": None,
                "l1_complete": False,
                "l2_complete": False,
                "l3_complete": False,
                "l4_complete": False,
                "jobs_pending": [],
            }
        source = source_dict(paths, dict(row), config)
        return {
            "registered": True,
            "source_id": int(row["id"]),
            "relpath": row["relpath"],
            "source_path": row["relpath"],
            "l1_complete": source.get("l1_complete", False),
            "l2_complete": source.get("l2_complete", False),
            "l3_complete": source.get("l3_complete", False),
            "l4_complete": source.get("l4_complete", False),
            "jobs_pending": source.get("jobs_pending", []),
            "source": source,
        }

    lookup_path = relpath or source_path or file_path or path
    if source_id is not None or lookup_path:
        row = source_row(paths, source_id=source_id, relpath=relpath, source_path=lookup_path)
        if row is None:
            return {
                "state": "untracked",
                "error": "Source not found",
                "source_path": lookup_path,
                "stats": stats,
            }
        return {"stats": stats, "source": source_dict(paths, row, config)}

    query_sql = "SELECT * FROM sources"
    params: tuple[Any, ...] = ()
    if status_filter:
        query_sql += " WHERE status = ?"
        params = (status_filter,)
    query_sql += " ORDER BY id ASC LIMIT ?"
    params = (*params, max(1, min(int(limit), 500)))

    with db.connect(paths.state_db) as conn:
        rows = conn.execute(query_sql, params).fetchall()
    return {
        "stats": stats,
        "sources": [source_dict(paths, dict(row), config, light=True) for row in rows],
        "count": len(rows),
    }


def import_source(
    paths: cfg.WikiPaths,
    *,
    file_path: str = "",
    zotero_attachment_key: str = "",
    zotero_custom_paths: str = "",
    policy: str = "mirror_03_to_04",
    destination: str = "",
    dry_run: bool = False,
    logical_source_id: str = "",
) -> dict[str, Any]:
    if not file_path and zotero_attachment_key:
        from . import zotero_tools

        resolved = zotero_tools.resolve_pdf(zotero_attachment_key, paths, zotero_custom_paths)
        if not resolved.get("ok") or not resolved.get("path"):
            return {
                "ok": False,
                "state": str(resolved.get("state") or "zotero_pdf_unavailable"),
                "error": str(resolved.get("error") or "Zotero PDF not found"),
                "zotero_attachment_key": zotero_attachment_key,
                "resolution": resolved,
            }
        file_path = str(resolved["path"])
        logical_source_id = logical_source_id or f"zotero:{zotero_attachment_key}"
    if not file_path:
        return {"ok": False, "state": "missing_path", "error": "No source file path or Zotero attachment key provided"}

    outcome = ingest_raw.import_source_file(
        paths,
        Path(file_path),
        policy=policy,
        destination=destination or None,
        dry_run=dry_run,
        logical_source_id=logical_source_id,
    )
    return {
        "ok": outcome.result in {ingest_raw.AddResult.ADDED, ingest_raw.AddResult.DEDUPED},
        "result": outcome.result.value,
        "dry_run": dry_run,
        "policy": policy,
        "source_id": outcome.source_id,
        "relpath": outcome.relpath,
        "source_path": str(outcome.source_path),
        "zotero_attachment_key": zotero_attachment_key,
        "title": outcome.title,
        "file_type": outcome.file_type,
        "bytes": outcome.bytes,
        "word_count": outcome.word_count,
        "message": outcome.message,
    }


def register_source(
    paths: cfg.WikiPaths,
    *,
    source_id: int | None = None,
    relpath: str = "",
    source_path: str = "",
    file_path: str = "",
    path: str = "",
    force: bool = False,
    build: bool = True,
) -> dict[str, Any]:
    lookup_path = relpath or source_path or file_path or path
    row = source_row(paths, source_id=source_id, relpath=relpath, source_path=lookup_path)
    if row is None:
        return {"state": "untracked", "error": "Source not found", "source_path": lookup_path}

    source_id_int = int(row["id"])
    if force:
        with db.connect(paths.state_db) as conn:
            conn.execute(
                "UPDATE sources SET status = 'force_pending', error_reason = NULL, "
                "l1_status = 'pending', l2_status = 'pending', "
                "l3_status = 'pending', l4_status = 'pending', layer_error = NULL "
                "WHERE id = ?",
                (source_id_int,),
            )
        row["context_id"] = None

    context_id = row.get("context_id")
    if force or not context_id or not (paths.contexts / f"{context_id}.md").exists():
        db.set_source_layer_status(paths.state_db, source_id_int, "l1", "running")
        context_id = ingest_raw.generate_l1_structural_context(
            paths,
            source_id=source_id_int,
            relpath=str(row["relpath"]),
            content_hash=str(row["content_hash"]),
            existing_context_id=None if force else row.get("context_id"),
        )
        if not context_id:
            return {"ok": False, "source_id": source_id_int, "error": "L1 generation failed"}

    try:
        search.update_index(paths, embed=False)
    except Exception:
        pass

    job_ids: list[int] = []
    if build:
        from .ingest_worker import enqueue_l2_l3_for_sources

        job_ids = enqueue_l2_l3_for_sources(paths, [source_id_int])

    state = "queued" if job_ids else "l1_ready"
    return {
        "ok": True,
        "state": state,
        "source_id": source_id_int,
        "context_id": context_id,
        "l2_l3_queued": bool(job_ids),
        "job_ids": job_ids,
        "jobs_pending": db.get_pending_jobs_for_source(paths.state_db, source_id_int),
    }


def rebind_source(
    paths: cfg.WikiPaths,
    *,
    source_id: int | None = None,
    logical_source_id: str = "",
    source_path: str = "",
    file_path: str = "",
    path: str = "",
    new_path: str = "",
    apply: bool = False,
    update_hash: bool = True,
) -> dict[str, Any]:
    lookup_path = source_path or file_path or path or logical_source_id
    row = source_row(paths, source_id=source_id, source_path=lookup_path)
    if row is None:
        return {
            "ok": False,
            "state": "untracked",
            "error": "Source not found",
            "source_path": lookup_path,
        }
    if not new_path:
        return {"ok": False, "state": "error", "error": "new_path is required", "source_id": row["id"]}
    try:
        return source_tools.rebind_source(
            paths,
            row,
            Path(new_path),
            apply=apply,
            update_hash=update_hash,
        )
    except Exception as exc:
        return {"ok": False, "state": "error", "error": str(exc), "source_id": row["id"]}


def search_sources(
    paths: cfg.WikiPaths,
    *,
    query_text: str,
    source_id: int | None = None,
    source_path: str = "",
    file_path: str = "",
    path: str = "",
    relpath: str = "",
    limit: int = 8,
) -> dict[str, Any]:
    lookup_path = relpath or source_path or file_path or path
    if source_id is None and lookup_path:
        row = source_row(paths, source_path=lookup_path)
        if row is None:
            return {
                "hits": [],
                "count": 0,
                "state": "untracked",
                "error": "Source not found",
                "source_path": lookup_path,
            }
        source_id = int(row["id"])
    hits = search.search_source_pages(
        paths,
        query_text,
        source_id=source_id,
        limit=max(1, min(int(limit), 50)),
    )
    return {
        "hits": [
            {
                "source_id": hit.source_id,
                "relpath": hit.relpath,
                "file_type": hit.file_type,
                "page": hit.page_number,
                "score": hit.score,
                "title": hit.title,
                "snippet": hit.snippet,
            }
            for hit in hits
        ],
        "count": len(hits),
    }


def _source_row_by_hash(paths: cfg.WikiPaths, file_hash: str) -> dict[str, Any] | None:
    if not file_hash:
        return None
    with db.connect(paths.state_db) as conn:
        row = conn.execute(
            "SELECT * FROM sources WHERE content_hash = ? ORDER BY id DESC LIMIT 1",
            (file_hash,),
        ).fetchone()
    return dict(row) if row else None


def _resolve_pdf_path(
    paths: cfg.WikiPaths,
    *,
    file_path: str = "",
    source_id: int | None = None,
    relpath: str = "",
    source_path: str = "",
    file_hash: str = "",
    zotero_attachment_key: str = "",
    zotero_custom_paths: str = "",
) -> tuple[Path | None, dict[str, Any] | None, str]:
    if file_path:
        resolved = Path(file_path).expanduser().resolve(strict=False)
        return resolved, source_row(paths, source_path=str(resolved)), ""

    if zotero_attachment_key:
        from . import zotero_tools

        result = zotero_tools.resolve_pdf(zotero_attachment_key, paths, zotero_custom_paths)
        if result.get("ok") and result.get("path"):
            resolved = Path(str(result["path"])).expanduser().resolve(strict=False)
            return resolved, source_row(paths, source_path=str(resolved)), ""
        return None, None, str(result.get("error") or "Zotero PDF not found")

    row = source_row(paths, source_id=source_id, relpath=relpath, source_path=source_path)
    if row is None and file_hash:
        row = _source_row_by_hash(paths, file_hash)
    if row is None:
        return None, None, "PDF source not found"
    return source_tools._row_path(paths, row).expanduser().resolve(strict=False), row, ""


def pdf_context(
    paths: cfg.WikiPaths,
    *,
    file_path: str = "",
    source_id: int | None = None,
    relpath: str = "",
    source_path: str = "",
    file_hash: str = "",
    zotero_attachment_key: str = "",
    zotero_custom_paths: str = "",
    query_text: str = "",
    page_num: int = 0,
    radius: int = 2,
    max_pages: int = 8,
) -> dict[str, Any]:
    from .parsers.pdf import _extract_pdf_toc, get_page_count, parse_page_window
    from .search import lexical_score

    resolved, row, resolve_error = _resolve_pdf_path(
        paths,
        file_path=file_path,
        source_id=source_id,
        relpath=relpath,
        source_path=source_path,
        file_hash=file_hash,
        zotero_attachment_key=zotero_attachment_key,
        zotero_custom_paths=zotero_custom_paths,
    )
    if resolved is None:
        return {"ok": False, "error": resolve_error or "PDF source not found"}
    if not resolved.exists():
        return {"ok": False, "error": f"File not found: {resolved}"}
    if resolved.suffix.lower() != ".pdf":
        return {"ok": False, "error": f"Not a PDF file: {resolved}"}

    source_tracked = row is not None
    source_id_val: int | None = int(row["id"]) if row else None

    try:
        if source_tracked and row is not None:
            all_pages: list[dict[str, Any]] = db.list_source_pdf_pages(paths.state_db, source_id_val)
            total_pages = len(all_pages) or get_page_count(resolved)
            if page_num > 0:
                lo = max(1, page_num - radius)
                hi = min(total_pages, page_num + radius)
                window_set = set(range(lo, hi + 1))
            else:
                window_set = set(range(1, min(max_pages * 3, total_pages) + 1))

            page_texts = parse_page_window(resolved, window_set)
            candidates = [
                {
                    "page_num": int(p.get("page_number") or p.get("page") or p.get("page_num") or 0),
                    "text": page_texts.get(int(p.get("page_number") or p.get("page") or p.get("page_num") or 0), ""),
                }
                for p in all_pages
                if int(p.get("page_number") or p.get("page") or p.get("page_num") or 0) in window_set
            ]
            if not candidates:
                candidates = [{"page_num": pn, "text": text} for pn, text in page_texts.items()]
            if query_text.strip():
                scored = [{**p, "_score": lexical_score(str(p.get("text") or ""), query_text)} for p in candidates]
                scored.sort(key=lambda x: x["_score"], reverse=True)
                candidates = scored[:max_pages]
            else:
                candidates = candidates[:max_pages]
            pages_out = [
                {
                    "page_num": int(p.get("page") or p.get("page_num") or 0),
                    "text": str(p.get("text") or ""),
                    "score": float(p.get("_score", 0.0)),
                }
                for p in candidates
            ]
            pages_out.sort(key=lambda x: x["page_num"])
            outline_raw = _extract_pdf_toc(resolved) if resolved.exists() else []
        else:
            total_pages = get_page_count(resolved)
            if total_pages == 0:
                return {"ok": False, "error": "Could not read PDF (encrypted or corrupt)"}
            if page_num > 0:
                lo = max(1, page_num - radius)
                hi = min(total_pages, page_num + radius)
                window_set = set(range(lo, hi + 1))
            else:
                window_set = set(range(1, min(max_pages, total_pages) + 1))

            candidate_set = set(range(1, min(max_pages * 3, total_pages) + 1)) | window_set if query_text.strip() else window_set
            page_texts = parse_page_window(resolved, candidate_set)
            if query_text.strip():
                scored_pages = [(pn, text, lexical_score(text, query_text)) for pn, text in page_texts.items()]
                scored_pages.sort(key=lambda x: x[2], reverse=True)
                top = scored_pages[:max_pages]
            else:
                top = [(pn, text, 0.0) for pn, text in page_texts.items()]
            pages_out = [{"page_num": pn, "text": text, "score": score} for pn, text, score in sorted(top, key=lambda x: x[0])]
            outline_raw = _extract_pdf_toc(resolved)

        outline = [
            {
                "title": str(item.get("title") or ""),
                "page_num": int(item.get("page") or item.get("page_num") or 0),
                "level": int(item.get("level") or 1),
            }
            for item in (outline_raw or [])
        ]
        title = str(row.get("title") or "") if row else ""
        return {
            "ok": True,
            "source_tracked": source_tracked,
            "source_id": source_id_val,
            "total_pages": total_pages,
            "title": title or resolved.stem,
            "pages": pages_out,
            "outline": outline,
            "is_empty_pdf": all(not p["text"].strip() for p in pages_out),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _normalize_link(value: str) -> str:
    return value.strip().strip("[]").removeprefix(".curator/Collections/").removesuffix(".md")


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

    query_boost_terms: list[str] | None = None
    if workspace_path:
        from . import curate_yml

        try:
            spec = curate_yml.load_curate_spec(Path(workspace_path).expanduser().resolve())
        except Exception:
            spec = None
        if spec is not None and spec.persona:
            # A real workspace with curate.yml: apply its persona retrieval boost.
            query_boost_terms = [
                term
                for term in [
                    spec.persona.domain,
                    spec.persona.subdomain,
                    *spec.persona.disambiguation_keywords,
                ]
                if term
            ]
        # Vault-wide chat (no curate.yml) resolves to default with no boost — never
        # error (SYSTEM_BEHAVIOR §9: no ancestor curate.yml → workspace_id=default).

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
            fallback_hits = []
        return {
            "ok": True,
            "answer": "",
            "exhibition_id": "",
            "cache_hit": False,
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

    session_id = f"QRY-{uuid.uuid4().hex[:8]}"

    class _SilentCallbacks(query.QueryCallbacks):
        pass

    try:
        with llm.build_client(config) as client:
            result = query.run_query(
                paths,
                client,
                question,
                _SilentCallbacks(),
                mode="hybrid",
                limit=12,
                min_score=0.35,
                rerank=False,
                temperature=0.3,
                scope="all",
                classify_intent_first=False,
                session_id=session_id,
                workspace_path=workspace_path or None,
                query_boost_terms=query_boost_terms,
                english_query=english_query or None,
                input_language=input_language,
                final_output_language=effective_final_output_language,
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

    matched_concepts: list[str] = []
    source_paths: list[str] = []
    for hit in result.hits:
        if hit.full_path.startswith(f"{consts.LAYER_L3}/"):
            con_id = Path(hit.full_path).stem
            if con_id not in matched_concepts:
                matched_concepts.append(con_id)
        if hit.full_path not in source_paths:
            source_paths.append(hit.full_path)

    # Sessionless: no Exhibition file is written; return the answer + trace only.
    return {
        "ok": True,
        "answer": result.answer,
        "cache_hit": False,
        "question": question,
        "input_language": input_language,
        "english_query": result.english_query,
        "final_output_language": result.final_output_language or effective_final_output_language,
        "trace": {
            "matched_concepts": matched_concepts,
            "source_ids": [],
            "source_paths": source_paths,
            "synthesis_node_ids": result.synthesis_node_ids,
            "community_report_ids": result.community_report_ids,
            "trace_id": result.trace_id,
            "route": result.route,
            "latency_ms": int((time.monotonic() - start) * 1000),
            "l3_complete": l3_complete,
        },
    }


def promote_answer(
    paths: cfg.WikiPaths, *, question: str, answer: str, workspace_path: str = ""
) -> dict[str, Any]:
    """Promote a sessionless Q&A answer into a durable `02_Wiki/` page.

    v0.3.1: queries are sessionless (no Exhibition file), so promotion takes the
    question + answer text directly and writes only `02_Wiki/` (source truth is
    never touched).
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
        pass

    if not slug:
        import re

        slug = re.sub(r"[^\w\s-]", "", question).strip()
        slug = re.sub(r"\s+", "-", slug)[:60].strip("-") or "note"

    try:
        wiki_path = query.save_wiki_page(paths, question, answer, category, slug)
    except Exception as exc:
        return {"ok": False, "error": f"Failed to write wiki page: {exc}"}

    return {"ok": True, "promoted_to": wiki_path}
