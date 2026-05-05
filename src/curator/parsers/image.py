"""Parser for standalone image files.

Returns a ParsedDocument with no extractable text — the image content is
described by a vision-capable LLM during the ingest phase (generate_l1_summary).
"""

from __future__ import annotations

import base64
from pathlib import Path

from .base import ParsedDocument, ParserError, fallback_title_from_path

SUPPORTED_IMAGE_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif",
})


def parse(path: Path) -> ParsedDocument:
    """Parse a standalone image file."""
    try:
        image_data = path.read_bytes()
    except OSError as e:
        raise ParserError(f"Cannot read image {path}: {e}") from e

    title = fallback_title_from_path(path)
    # Placeholder text — actual description comes from vision LLM in ingest_raw
    text = f"[Image: {path.name}]"
    content_hash = __import__("hashlib").sha256(image_data).hexdigest()

    return ParsedDocument(
        source_path=path,
        file_type="image",
        title=title,
        text=text,
        content_hash=content_hash,
        bytes=path.stat().st_size,
        metadata={
            "image_data": base64.b64encode(image_data).decode(),
            "requires_vision": True,
        },
    )
