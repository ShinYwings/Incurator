"""Parser for PDF files using Math-Aware hybrid pipeline (pymupdf4llm).

Handles text-based PDFs. Scanned/image PDFs will extract to near-empty text
and be flagged via ParsedDocument.is_empty — the caller decides whether to
skip or still register them.
"""

from __future__ import annotations

from pathlib import Path

from .base import (
    ParsedDocument,
    ParserError,
    compute_hash,
    fallback_title_from_path,
    normalize_text,
)

_MAX_PDF_IMAGES = 10  # cap per document to avoid memory blow-up


def _extract_pdf_toc(path: Path) -> list[dict]:
    """Extract PDF outline using PyMuPDF when available."""
    try:
        import fitz  # pymupdf
    except ImportError:
        return []
    try:
        doc = fitz.open(str(path))
        toc = [
            {"level": int(level), "title": str(title).strip(), "page": int(page)}
            for level, title, page in doc.get_toc(simple=True)
            if str(title).strip() and int(page) > 0
        ]
        doc.close()
        return toc
    except Exception:
        return []


def _extract_pdf_images(path: Path) -> list[dict]:
    """Extract embedded images from a PDF using pymupdf (optional dep).

    Returns list of {"page": int, "data": bytes, "ext": str}.
    Returns [] silently if pymupdf is not installed or extraction fails.
    """
    try:
        import fitz  # pymupdf
    except ImportError:
        return []

    images: list[dict] = []
    try:
        doc = fitz.open(str(path))
        for page_num in range(len(doc)):
            if len(images) >= _MAX_PDF_IMAGES:
                break
            page = doc[page_num]
            for img_info in page.get_images(full=True):
                if len(images) >= _MAX_PDF_IMAGES:
                    break
                xref = img_info[0]
                try:
                    base_img = doc.extract_image(xref)
                    data = base_img.get("image")
                    if data and len(data) > 1024:  # skip tiny icons
                        images.append({
                            "page": page_num + 1,
                            "data": data,
                            "ext": base_img.get("ext", "png"),
                        })
                except Exception:
                    continue
        doc.close()
    except Exception:
        pass
    return images


def _first_nonempty_line(text: str) -> str | None:
    for line in text.splitlines():
        line = line.strip()
        if line and len(line) <= 200:
            return line
    return None


def _chunk_page_number(chunk: dict) -> int:
    """Return the 1-based page number from pymupdf4llm chunk metadata."""
    metadata = chunk.get("metadata") or {}
    raw = metadata.get("page_number", metadata.get("page", 1))
    try:
        page_num = int(raw)
    except (TypeError, ValueError):
        return 1
    return max(page_num, 1)


def _merge_raw_text_fallback(markdown_text: str, raw_text: str) -> str:
    """Append PDF text-layer lines that pymupdf4llm omitted."""
    if not raw_text.strip():
        return markdown_text

    normalized_markdown = normalize_text(markdown_text).lower()
    missing: list[str] = []
    mathish = set("=+{}()[]\\")
    for line in raw_text.splitlines():
        candidate = line.strip()
        if len(candidate) < 20 and not any(ch in candidate for ch in mathish):
            continue
        if normalize_text(candidate).lower() not in normalized_markdown:
            missing.append(candidate)

    if not missing:
        return markdown_text
    fallback = "\n".join(missing)
    if markdown_text.strip():
        return f"{markdown_text.rstrip()}\n\n### Raw PDF Text Fallback\n\n{fallback}"
    return fallback


def parse(path: Path) -> ParsedDocument:
    """Parse a .pdf file using Math-Aware hybrid pipeline (pymupdf4llm default)."""
    try:
        import pymupdf4llm
        import fitz
    except ImportError as e:
        raise ParserError(
            "pymupdf4llm is not installed. Run `./setup.sh` from the repository root, "
            "or `uv pip install -e './backend` for a backend-only repair."
        ) from e

    try:
        # Hybrid Pipeline placeholder: if config enables VLM for this file, we would route here.
        # For now, default to fast pymupdf4llm which preserves tables and some math layout.
        page_chunks = pymupdf4llm.to_markdown(str(path), page_chunks=True)
        doc = fitz.open(str(path))
    except Exception as e:
        raise ParserError(f"Cannot parse PDF {path.name}: {e}") from e

    if doc.is_encrypted:
        doc.close()
        raise ParserError(
            f"PDF is password-protected and cannot be read: {path.name}"
        )

    # Extract Markdown from all pages
    page_texts_dict: dict[int, list[str]] = {}
    
    for chunk in page_chunks:
        page_num = _chunk_page_number(chunk)
        text_chunk = chunk.get("text", "")
        if page_num not in page_texts_dict:
            page_texts_dict[page_num] = []
        page_texts_dict[page_num].append(text_chunk)
        
    page_texts: list[str] = []
    pdf_pages: list[dict] = []
    
    for page_num in range(1, doc.page_count + 1):
        page_chunks_text = page_texts_dict.get(page_num, [])
        markdown_text = "\n\n".join(page_chunks_text)
        raw_text = doc[page_num - 1].get_text("text")
        page_text = normalize_text(_merge_raw_text_fallback(markdown_text, raw_text))
        page_texts.append(page_text)
        pdf_pages.append(
            {
                "page": page_num,
                "char_count": len(page_text),
                "word_count": len(page_text.split()) if page_text else 0,
                "content_hash": compute_hash(page_text),
                "text": page_text,
            }
        )

    full_text = "\n\n".join(p for p in page_texts if p.strip())
    text = normalize_text(full_text)

    # Title extraction: metadata first, then first non-empty line, then filename
    title: str | None = None
    try:
        meta = doc.metadata
        if meta and meta.get("title"):
            meta_title = str(meta.get("title")).strip()
            if meta_title:
                title = meta_title
    except Exception:
        pass
    if not title:
        title = _first_nonempty_line(text)
    if not title:
        title = fallback_title_from_path(path)

    # Collect useful metadata
    metadata: dict = {
        "page_count": doc.page_count,
        "pdf_pages": pdf_pages,
        "pdf_toc": _extract_pdf_toc(path),
        "parser_used": "pymupdf4llm",
    }
    try:
        meta = doc.metadata
        if meta:
            if meta.get("author"):
                metadata["author"] = str(meta.get("author"))
            if meta.get("creationDate"):
                metadata["creation_date"] = str(meta.get("creationDate"))
    except Exception:
        pass

    metadata["pdf_images"] = _extract_pdf_images(path)
    doc.close()

    return ParsedDocument(
        source_path=path,
        file_type="pdf",
        title=title,
        text=text,
        content_hash=compute_hash(text),
        bytes=path.stat().st_size,
        metadata=metadata,
    )


def get_page_count(path: Path) -> int:
    """Return total page count without extracting text."""
    try:
        import fitz
        with fitz.open(str(path)) as doc:
            return doc.page_count
    except Exception:
        return 0


def parse_page_window(path: Path, page_nums: set[int]) -> dict[int, str]:
    """Extract Markdown text from specific pages only (1-based page numbers).

    Passes the ``pages`` argument to pymupdf4llm so only the requested pages
    are decoded — avoids loading the entire PDF when only a few pages are needed
    (G12-2 bounded-parse fix).
    """
    try:
        import pymupdf4llm
    except ImportError:
        return {}

    result: dict[int, str] = {}
    if not page_nums:
        return result
    try:
        total = get_page_count(path)
        # Clamp to valid 1-based range so an out-of-range page does not cause
        # pymupdf4llm to raise and silently discard the entire valid batch.
        valid_nums = page_nums if total == 0 else {n for n in page_nums if 1 <= n <= total}
        if not valid_nums:
            return result
        # pymupdf4llm uses 0-based page indices; valid_nums is 1-based.
        zero_based = [n - 1 for n in valid_nums]
        page_chunks = pymupdf4llm.to_markdown(
            str(path), pages=zero_based, page_chunks=True
        )
        for chunk in page_chunks:
            pn = _chunk_page_number(chunk)
            if pn in valid_nums:
                result[pn] = normalize_text(chunk.get("text", ""))
    except Exception:
        pass
    return result
