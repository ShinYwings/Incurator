"""Deterministic source-span extraction (L1).

Splits parsed source sections into atomic, hashed ``source_spans`` — the citation
unit of v0.3.1. This runs WITHOUT an LLM (the instant-L1 guarantee): it preserves
structure, it does not refine. Equation (``$$...$$``) and fenced code blocks are
kept as specialized spans with their exact text/delimiters.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import db

__all__ = [
    "SpanRecord",
    "classify_span_loss",
    "spans_from_sections",
    "store_source_spans",
]

_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_EQUATION_BLOCK = re.compile(r"\$\$.*?\$\$", re.DOTALL)
_PREVIEW_CHARS = 200

# What a PDF parser leaves behind where it could not read a rendered region.
# Geometry is optional: some emitters state `[W x H]`, some state nothing.
_PICTURE_OMITTED = re.compile(
    r"\*\*==>\s*picture\s*(?:\[\s*(\d+)\s*x\s*(\d+)\s*\])?[^<]*?intentionally omitted\s*<==\*\*",
    re.IGNORECASE,
)


def classify_span_loss(text: str) -> dict[str, Any] | None:
    """Record that a region could not be read at all (SYSTEM_BEHAVIOR §26.2b).

    This is NOT §26.2 recovery: there is no text to repair and no claim to
    anchor to, so no provider call happens and no ``formula_status`` changes.
    It only makes an otherwise silent deletion observable.

    Returns ``None`` when nothing was lost. Geometry is included only when the
    parser stated it — the placeholder carries no page coordinates, so the
    result is never a crop locator (SCHEMA §20.4a).
    """
    if not text or not text.strip():
        return None
    match = _PICTURE_OMITTED.search(text)
    if match is None:
        return None

    loss: dict[str, Any] = {
        "verdict": "image_only",
        "classified_at": datetime.now(timezone.utc).isoformat(),
    }
    width, height = match.group(1), match.group(2)
    if width and height:
        loss["region"] = {"width": int(width), "height": int(height)}
    return loss


@dataclass
class SpanRecord:
    """A deterministic source span before it is persisted."""

    span_type: str  # heading_section | paragraph | equation | code
    text: str
    content_hash: str
    page_number: int | None = None
    section_title: str | None = None
    toc_id: str | None = None
    loss: dict[str, Any] | None = None

    @property
    def text_preview(self) -> str:
        preview = " ".join(self.text.split())
        return preview[:_PREVIEW_CHARS]

    @property
    def metadata(self) -> dict[str, Any] | None:
        return {"loss": self.loss} if self.loss else None


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _block_spans(
    text: str, *, page: int | None, title: str | None, toc_id: str | None
) -> list[SpanRecord]:
    """Pull fenced code and ``$$`` blocks out as spans, splitting the remaining
    prose into paragraph spans, preserving document order."""
    spans: list[SpanRecord] = []
    # Record (start, end, type) for every special block.
    blocks: list[tuple[int, int, str]] = []
    for m in _CODE_BLOCK.finditer(text):
        blocks.append((m.start(), m.end(), "code"))
    for m in _EQUATION_BLOCK.finditer(text):
        blocks.append((m.start(), m.end(), "equation"))
    blocks.sort()

    cursor = 0

    def _emit_prose(chunk: str) -> None:
        for para in re.split(r"\n\s*\n", chunk):
            para = para.strip()
            if para:
                spans.append(
                    SpanRecord(
                        "paragraph", para, _hash(para), page, title, toc_id,
                        classify_span_loss(para),
                    )
                )

    for start, end, kind in blocks:
        _emit_prose(text[cursor:start])
        block_text = text[start:end].strip()
        if block_text:
            spans.append(
                SpanRecord(
                    kind, block_text, _hash(block_text), page, title, toc_id,
                    classify_span_loss(block_text),
                )
            )
        cursor = end
    _emit_prose(text[cursor:])
    return spans


def spans_from_sections(sections: list[dict]) -> list[SpanRecord]:
    """Turn structural sections ({id, title, page, text}) into source spans.

    A section with no splittable content becomes a single ``heading_section``
    span; otherwise it yields paragraph / equation / code spans.
    """
    out: list[SpanRecord] = []
    for section in sections:
        text = str(section.get("text") or "").strip()
        title = section.get("title")
        toc_id = section.get("id")
        page = section.get("page")
        page_number = int(page) if isinstance(page, (int, str)) and str(page).isdigit() else None
        if not text:
            continue
        sub = _block_spans(text, page=page_number, title=title, toc_id=toc_id)
        if len(sub) <= 1 and not any(s.span_type in ("code", "equation") for s in sub):
            # Treat a single-chunk section as one section-level span.
            out.append(
                SpanRecord(
                    "heading_section", text, _hash(text), page_number, title, toc_id,
                    classify_span_loss(text),
                )
            )
        else:
            out.extend(sub)
    return out


def store_source_spans(
    db_path: Path, source_id: int, relpath: str, spans: list[SpanRecord]
) -> list[str]:
    """Persist spans to the DB. Returns the ordered list of SPAN- ids.

    Re-storing identical (source_id, content_hash) spans is idempotent, so a
    re-parse that produces the same text reuses the same ids."""
    ids: list[str] = []
    for span in spans:
        span_id = db.upsert_source_span(
            db_path,
            source_id=source_id,
            relpath=relpath,
            span_type=span.span_type,
            content_hash=span.content_hash,
            page_number=span.page_number,
            section_title=span.section_title,
            toc_id=span.toc_id,
            text_preview=span.text_preview,
            metadata=span.metadata,
        )
        ids.append(span_id)
    return ids
