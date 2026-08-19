"""Parser dispatcher — picks the right parser for a given file extension."""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from .base import ParsedDocument, ParserAccessDenied, ParserError

# Map lowercase extension → module path of the parser
_PARSERS = {
    ".md": "text",
    ".markdown": "text",
    ".txt": "text",
    ".pdf": "pdf",
    ".docx": "docx",
    ".html": "html",
    ".htm": "html",
    # Image formats — described by vision LLM during ingest
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".webp": "image",
    ".bmp": "image",
    ".tiff": "image",
    ".tif": "image",
}

SUPPORTED_EXTENSIONS = frozenset(_PARSERS.keys())


def is_supported(path: Path) -> bool:
    """True if we have a parser for this file extension."""
    return path.suffix.lower() in _PARSERS


def parse(path: Path) -> ParsedDocument:
    """Dispatch to the appropriate parser based on the file extension.

    Raises:
        ParserError: if the extension is unsupported or parsing fails.
    """
    # Reachability first, and at THIS boundary rather than inside each parser.
    # A denial can surface anywhere -- `path.exists()` itself raises when the
    # parent directory is unreadable, while macOS TCC lets `stat` through and
    # refuses only `open`. One check at the dispatch covers both shapes, and
    # `probe` is the only predicate that agrees with reality: `os.access(R_OK)`
    # returns True for a TCC-denied file. See SYSTEM_BEHAVIOR §12.3.
    from .. import file_access

    match file_access.probe(path):
        case file_access.Reachability.DENIED:
            raise ParserAccessDenied(path, file_access.grant_root(path))
        case file_access.Reachability.MISSING:
            raise ParserError(f"File not found: {path}")

    if not path.is_file():
        raise ParserError(f"Not a regular file: {path}")

    ext = path.suffix.lower()
    if ext not in _PARSERS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ParserError(
            f"Unsupported file type '{ext}' for {path.name}. "
            f"Supported: {supported}"
        )

    module_name = _PARSERS[ext]
    if module_name not in {"text", "pdf", "docx", "html", "image"}:
        raise ParserError(f"Internal error: unknown parser '{module_name}'")
    # Lazy import so unused parsers don't force their heavy deps.
    parser_module: Any = importlib.import_module(f"{__name__}.{module_name}")

    return parser_module.parse(path)


__all__ = ["ParsedDocument", "ParserAccessDenied", "ParserError", "parse", "is_supported", "SUPPORTED_EXTENSIONS"]
