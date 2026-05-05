"""Parser for PDF files using pypdf.

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


def parse(path: Path) -> ParsedDocument:
    """Parse a .pdf file."""
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise ParserError(
            "pypdf is not installed. Run `uv pip install -e .` to install dependencies."
        ) from e

    try:
        reader = PdfReader(str(path))
    except Exception as e:
        raise ParserError(f"Cannot open PDF {path.name}: {e}") from e

    if reader.is_encrypted:
        raise ParserError(
            f"PDF is password-protected and cannot be read: {path.name}"
        )

    # Extract text from all pages
    page_texts: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            page_texts.append(page.extract_text() or "")
        except Exception:
            # Individual page extraction can fail on malformed PDFs; keep going
            page_texts.append("")

    full_text = "\n\n".join(p for p in page_texts if p.strip())
    text = normalize_text(full_text)

    # Title extraction: metadata first, then first non-empty line, then filename
    title: str | None = None
    try:
        meta = reader.metadata
        if meta and getattr(meta, "title", None):
            meta_title = str(meta.title).strip()
            if meta_title:
                title = meta_title
    except Exception:
        pass
    if not title:
        title = _first_nonempty_line(text)
    if not title:
        title = fallback_title_from_path(path)

    # Collect useful metadata
    metadata: dict = {"page_count": len(reader.pages)}
    try:
        meta = reader.metadata
        if meta:
            if getattr(meta, "author", None):
                metadata["author"] = str(meta.author)
            if getattr(meta, "creation_date", None):
                metadata["creation_date"] = str(meta.creation_date)
    except Exception:
        pass

    metadata["pdf_images"] = _extract_pdf_images(path)

    return ParsedDocument(
        source_path=path,
        file_type="pdf",
        title=title,
        text=text,
        content_hash=compute_hash(text),
        bytes=path.stat().st_size,
        metadata=metadata,
    )