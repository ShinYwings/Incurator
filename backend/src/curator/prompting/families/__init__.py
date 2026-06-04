"""Prompt families. Importing this package registers every prompt contract.

Each module registers its contract(s) into the global ``REGISTRY`` at import
time, so importing ``curator.prompting`` makes all prompts available.
"""

from __future__ import annotations

from . import (  # noqa: F401  (imported for registration side effects)
    backprop,
    community_reports,
    curation_plan,
    entities,
    explore,
    knowledge_units,
    note_writing,
    query,
    source_map,
    synthesis,
)

__all__ = [
    "backprop",
    "community_reports",
    "curation_plan",
    "entities",
    "explore",
    "knowledge_units",
    "note_writing",
    "query",
    "source_map",
    "synthesis",
]
