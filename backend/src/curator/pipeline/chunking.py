"""Shared prompt chunk-budget helpers for pipeline extractors."""

from __future__ import annotations

from typing import Any

# Overlap allowance the extractors subtract from the reported budget when they
# subdivide or truncate against it.
CHUNK_OVERLAP_CHARS = 500

# Floor for any size DERIVED from the reported budget by subtracting
# `CHUNK_OVERLAP_CHARS`. The budget itself is never floored — see
# `client_optimal_chunk_chars` — but a size computed from it must stay positive,
# and must exceed the overlap so a subdivided chunk still advances.
#
# 1,000 sits an order of magnitude below the smallest budget any real client
# reports (`OllamaClient`'s low-RAM tier: a 4,096-token context -> 13,107
# chars; the CLI clients report 12,000-18,000), so it cannot engage on a
# production configuration. It exists to catch a misconfigured value, not to
# reshape a legitimate one.
MIN_SUBDIVISION_CHARS = 1000


def subdivision_chars(max_chars: int) -> int:
    """Positive size derived from a reported chunk budget.

    `max_chars - CHUNK_OVERLAP_CHARS` had no positivity guarantee at either call
    site. Passed to `_chunk_text` as a size it produced one chunk per character
    position, each holding nearly the whole remaining text — 3,000 chunks
    totalling 810,000 characters for a 3,000-character span, then one LLM call
    per chunk. Used as a slice bound it silently amputated the tail of every
    statement, and erased short ones outright (v0.61.2).
    """
    return max(MIN_SUBDIVISION_CHARS, max_chars - CHUNK_OVERLAP_CHARS)


def client_optimal_chunk_chars(client: Any, default: int = 60000) -> int:
    """The client's reported chunk budget, taken as given.

    Deliberately NOT floored. A small budget is a legitimate report from a
    small-context local model, and substituting a larger default (or clamping
    up to a minimum) would hand that model a prompt several times its context —
    trading a visible cost defect for silent provider-side truncation. A small
    budget is harmless on its own: it produces more, smaller batches, and the
    batch count stays proportional to the document. Sizes DERIVED from it are
    what must be floored; use `subdivision_chars`.
    """
    # Accept both @property (production clients) and regular method (test doubles).
    value: Any = getattr(client, "optimal_chunk_chars", None)
    if value is None:
        return default
    try:
        return int(value() if callable(value) else value)
    except Exception:
        return default
