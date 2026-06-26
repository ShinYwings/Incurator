"""Shared prompt chunk-budget helpers for pipeline extractors."""

from __future__ import annotations

from typing import Any


def client_optimal_chunk_chars(client: Any, default: int = 60000) -> int:
    # Accept both @property (production clients) and regular method (test doubles).
    value: Any = getattr(client, "optimal_chunk_chars", None)
    if value is None:
        return default
    try:
        return int(value() if callable(value) else value)
    except Exception:
        return default
