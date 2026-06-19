"""Incurator v0.3.1 compile pipeline.

Stage modules for the curation-native compile model (see
``docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`` §22):

- ``source_spans`` — deterministic L1: source -> source_spans DB records.
- ``knowledge_units`` — LLM L2: source_spans -> knowledge_units DB records.
- ``projection`` — emit derived ``.curator/Collections`` markdown from DB records.

The DB is the single source of truth; markdown pages are a derived, disposable
derived search projection emitted from these records.

Submodules are imported explicitly (``from .pipeline import source_spans``) rather
than eagerly here, so the LLM-free instant-L1 path (``source_spans``) does not pull
in the prompt subsystem that ``knowledge_units`` needs.
"""

from __future__ import annotations

__all__ = ["source_spans", "knowledge_units", "projection"]
