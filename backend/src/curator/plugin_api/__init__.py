"""Backend-local function API used by hidden plugin commands."""

from __future__ import annotations

from .. import db, ingest_raw, llm, page_writer, query, search, source_tools
from .context import (
    _normalize_link,
    expand_context,
    feedback_context,
    fetch_context,
    verify_context,
)
from .pdf import (
    _parse_pdf_pages_cached,
    _safe_pdf_page_cache_key,
    durable_l1_section,
    pdf_context,
)
from .query_api import curator_query, promote_answer
from .sources import (
    import_source,
    rebind_source,
    register_source,
    search_sources,
    source_dict,
    source_row,
    source_status,
)

__all__ = [
    "_normalize_link",
    "_parse_pdf_pages_cached",
    "_safe_pdf_page_cache_key",
    "curator_query",
    "db",
    "durable_l1_section",
    "expand_context",
    "feedback_context",
    "fetch_context",
    "import_source",
    "ingest_raw",
    "llm",
    "page_writer",
    "pdf_context",
    "promote_answer",
    "query",
    "rebind_source",
    "register_source",
    "search",
    "search_sources",
    "source_dict",
    "source_row",
    "source_status",
    "source_tools",
    "verify_context",
]
