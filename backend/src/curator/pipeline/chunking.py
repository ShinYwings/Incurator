"""Shared prompt chunk-budget helpers for pipeline extractors."""

from __future__ import annotations

from typing import Any


def client_optimal_chunk_chars(client: Any, default: int = 60000) -> int:
    """Return a client's chunk budget whether exposed as a method or property."""
    try:
        value = getattr(client, "optimal_chunk_chars")
    except Exception:
        return default
    try:
        return int(value() if callable(value) else value)
    except Exception:
        return default
