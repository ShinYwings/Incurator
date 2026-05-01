"""Parser for plain text and markdown files.

Markdown is treated as text + a title extracted from the first `#` heading
if present. We don't render markdown here — Stage 3's LLM will see the raw
markdown source, which is what we want.
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import (
    ParsedDocument,
    ParserError,
    compute_hash,
    fallback_title_from_path,
    normalize_text,
)

# Supported image extensions (lowercase, with dot)
_IMG_EXT_PAT = r"\.(?:png|jpe?g|gif|webp|bmp|tiff?|svg)"

# ![[path/to/image.png]] or ![[path.png|400]] (Obsidian embed syntax)
_OBSIDIAN_IMG_RE = re.compile(
    r"!\[\[([^\]]+?" + _IMG_EXT_PAT + r")(?:\|[^\]]*)?\]\]",
    re.IGNORECASE,
)
# ![alt text](path/to/image.png) (standard Markdown)
_MARKDOWN_IMG_RE = re.compile(
    r"!\[.*?\]\(([^)]+?" + _IMG_EXT_PAT + r")\)",
    re.IGNORECASE,
)


def _extract_image_links(text: str) -> list[str]:
    """Extract raw image link strings from markdown (Obsidian + standard)."""
    links: list[str] = []
    seen: set[str] = set()
    for m in _OBSIDIAN_IMG_RE.finditer(text):
        raw = m.group(1).strip()
        if raw not in seen:
            seen.add(raw)
            links.append(raw)
    for m in _MARKDOWN_IMG_RE.finditer(text):
        raw = m.group(1).strip()
        if raw not in seen:
            seen.add(raw)
            links.append(raw)
    return links


def _extract_md_title(text: str) -> str | None:
    """Find the first level-1 heading in a markdown document."""
    # Also handle YAML frontmatter's `title:` field
    frontmatter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if frontmatter_match:
        fm = frontmatter_match.group(1)
        title_match = re.search(r"^title:\s*[\"']?(.+?)[\"']?\s*$", fm, re.MULTILINE)
        if title_match:
            return title_match.group(1).strip()

    # First `# heading` (not `##` or deeper)
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()
    return None


def _extract_txt_title(text: str) -> str | None:
    """First non-empty line, if reasonably short, is the title."""
    for line in text.splitlines():
        line = line.strip()
        if line:
            # Only use it as a title if it's plausibly a title (not a paragraph)
            if len(line) <= 120:
                return line
            return None
    return None


def parse(path: Path) -> ParsedDocument:
    """Parse a .md, .markdown, or .txt file."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise ParserError(f"Cannot read {path}: {e}") from e

    ext = path.suffix.lower()
    if ext in {".md", ".markdown"}:
        file_type = "md"
        title = _extract_md_title(raw) or fallback_title_from_path(path)
        linked_images = _extract_image_links(raw)
    else:
        file_type = "txt"
        title = _extract_txt_title(raw) or fallback_title_from_path(path)
        linked_images = []

    text = normalize_text(raw)
    return ParsedDocument(
        source_path=path,
        file_type=file_type,
        title=title,
        text=text,
        content_hash=compute_hash(text),
        bytes=path.stat().st_size,
        metadata={},
        linked_images=linked_images,
    )
