from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .. import config as cfg
from .. import db, page_writer, source_tools
from .sources import source_row

_CTX_SECTION_RE = re.compile(
    r"(?ms)^<!--\s*section:(?P<id>\S+)\s+page:(?P<page>\d+)\s*-->\s*"
    r"(?P<text>.*?)(?=^<!--\s*section:|\Z)"
)

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
        from .. import zotero_tools

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
    resolved_path = source_tools._row_path(paths, row)
    if resolved_path is None:
        return None, row, "PDF source path is unresolved"
    return resolved_path.expanduser().resolve(strict=False), row, ""


def _durable_l1_projection(
    paths: cfg.WikiPaths,
    row: dict[str, Any],
) -> dict[str, Any] | None:
    if str(row.get("l1_status") or "") != "done":
        return None
    context_id = str(row.get("context_id") or "")
    if not context_id:
        return None
    parsed = page_writer.read_page(paths.contexts / f"{context_id}.md")
    if parsed is None or parsed.is_invalid:
        return None

    toc = parsed.frontmatter.get("toc") or []
    toc_by_id = {
        str(item.get("id") or ""): item
        for item in toc
        if isinstance(item, dict) and str(item.get("id") or "")
    }
    sections: list[dict[str, Any]] = []
    for match in _CTX_SECTION_RE.finditer(parsed.body):
        section_id = match.group("id")
        toc_item = toc_by_id.get(section_id, {})
        text = match.group("text").strip()
        text = re.split(r"(?m)^##\s+Embedded Figures\s*$", text, maxsplit=1)[0].strip()
        sections.append(
            {
                "id": section_id,
                "title": str(toc_item.get("title") or section_id),
                "level": int(toc_item.get("level") or 2),
                "page": int(toc_item.get("page") or match.group("page") or 1),
                "text": text,
            }
        )
    if not sections:
        return None

    outline = [
        {
            "title": str(item.get("title") or ""),
            "page_num": int(item.get("page") or 0),
            "level": int(item.get("level") or 1),
        }
        for item in toc
        if isinstance(item, dict)
    ]
    total_pages = int(parsed.frontmatter.get("source_page_count") or 0)
    if total_pages <= 0:
        total_pages = max((int(section["page"]) for section in sections), default=1)
    return {
        "context_id": context_id,
        "source_text_policy": str(parsed.frontmatter.get("source_text_policy") or ""),
        "sections": sections,
        "outline": outline,
        "total_pages": total_pages,
    }


def durable_l1_section(
    paths: cfg.WikiPaths,
    row: dict[str, Any],
    wanted: str,
) -> dict[str, Any] | None:
    projection = _durable_l1_projection(paths, row)
    if projection is None or projection["source_text_policy"] != "inline":
        return None
    for section in projection["sections"]:
        if section["id"] == wanted or section["title"] == wanted:
            text = str(section["text"])
            return {
                "ok": True,
                "source_id": int(row["id"]),
                "source_key": str(row.get("relpath") or ""),
                "relpath": row.get("relpath"),
                "toc_id": wanted,
                "page": int(section["page"]),
                "page_start": int(section["page"]),
                "page_end": int(section["page"]),
                "page_count": int(projection["total_pages"]),
                "title": str(row.get("title") or Path(str(row.get("relpath") or "")).stem),
                "file_type": str(row.get("file_type") or ""),
                "metadata": {
                    "section_id": section["id"],
                    "section_title": section["title"],
                    "page": int(section["page"]),
                },
                "text": text,
                "char_count": len(text),
                "context_source": "durable_l1_projection",
            }
    return None


def _safe_pdf_page_cache_key(content_hash: str | None) -> str:
    if not isinstance(content_hash, str):
        return ""
    value = content_hash.strip()
    if value and all(c in "0123456789abcdefABCDEF" for c in value):
        return value
    return ""


def _parse_pdf_pages_cached(
    paths: cfg.WikiPaths,
    pdf_path: Path,
    page_numbers: set[int],
    content_hash: str | None,
) -> dict[int, str]:
    from ..parsers.pdf import parse_page_window

    pages_needed = {int(page) for page in page_numbers if int(page) > 0}
    if not pages_needed:
        return {}

    cache_key = _safe_pdf_page_cache_key(content_hash)
    if not cache_key:
        return parse_page_window(pdf_path, pages_needed)

    cache_dir = paths.pdf_pages / cache_key
    out: dict[int, str] = {}
    missing: set[int] = set()
    for page_num in pages_needed:
        cache_file = cache_dir / f"{page_num}.txt"
        try:
            if cache_file.exists():
                out[page_num] = cache_file.read_text(encoding="utf-8")
            else:
                missing.add(page_num)
        except OSError:
            missing.add(page_num)

    if missing:
        fetched = parse_page_window(pdf_path, missing)
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            for page_num, text in fetched.items():
                (cache_dir / f"{page_num}.txt").write_text(text, encoding="utf-8")
        except OSError:
            pass
        out.update(fetched)

    return out


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
    from ..parsers.pdf import _extract_pdf_toc, get_page_count
    from ..search import lexical_score

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
    if resolved.suffix.lower() != ".pdf":
        return {"ok": False, "error": f"Not a PDF file: {resolved}"}

    source_tracked = row is not None
    source_id_val: int | None = int(row["id"]) if row else None
    degraded_reason = ""
    pages_out: list[dict[str, Any]] = []

    try:
        if source_tracked and row is not None:
            projection = _durable_l1_projection(paths, row)
            if projection is not None:
                sections: list[dict[str, Any]] = list(projection["sections"])
                total_pages = int(projection["total_pages"])
                if page_num > 0:
                    lo = max(1, page_num - radius)
                    hi = min(total_pages, page_num + radius)
                    candidates: list[dict[str, Any]] = [
                        section for section in sections if lo <= int(section["page"]) <= hi
                    ]
                    if not candidates:
                        prior = [section for section in sections if int(section["page"]) <= page_num]
                        candidates = prior[-1:] or sections[:1]
                else:
                    candidates = sections[: max_pages * 3]
                if query_text.strip():
                    candidates = [
                        {**section, "_score": lexical_score(str(section["text"]), query_text)}
                        for section in candidates
                    ]
                    candidates.sort(key=lambda item: float(item["_score"]), reverse=True)
                candidates = candidates[:max_pages]
                pages_out = [
                    {
                        "page_num": int(section["page"]),
                        "text": str(section["text"]),
                        "score": float(section.get("_score", 0.0)),
                    }
                    for section in candidates
                ]
                pages_out.sort(key=lambda item: int(item["page_num"]))
                outline = list(projection["outline"])
                return {
                    "ok": True,
                    "source_tracked": True,
                    "source_id": source_id_val,
                    "total_pages": total_pages,
                    "title": str(row.get("title") or "") or resolved.stem,
                    "pages": pages_out,
                    "outline": outline,
                    "is_empty_pdf": all(not page["text"].strip() for page in pages_out),
                    "context_source": "durable_l1_projection",
                    "degraded_reason": (
                        "projection_preview_only"
                        if projection["source_text_policy"] != "inline"
                        else None
                    ),
                }

            if not resolved.exists():
                return {"ok": False, "error": f"File not found: {resolved}"}
            if str(row.get("l1_status") or "") == "done":
                degraded_reason = "missing_l1_projection"
            else:
                degraded_reason = "l1_incomplete"
            assert source_id_val is not None
            all_pages: list[dict[str, Any]] = db.list_source_pdf_pages(paths.state_db, source_id_val)
            total_pages = len(all_pages) or get_page_count(resolved)
            if page_num > 0:
                lo = max(1, page_num - radius)
                hi = min(total_pages, page_num + radius)
                window_set = set(range(lo, hi + 1))
            else:
                window_set = set(range(1, min(max_pages * 3, total_pages) + 1))

            page_texts = _parse_pdf_pages_cached(
                paths,
                resolved,
                window_set,
                str(row.get("content_hash") or file_hash or ""),
            )
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
            if not resolved.exists():
                return {"ok": False, "error": f"File not found: {resolved}"}
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
            page_texts = _parse_pdf_pages_cached(paths, resolved, candidate_set, file_hash)
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
            "context_source": "ephemeral_parse",
            "degraded_reason": degraded_reason or None,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

