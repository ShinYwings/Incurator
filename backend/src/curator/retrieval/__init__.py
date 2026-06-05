"""Incurator v0.3.1 query retrieval/orchestration package.

The query path: resolve curate.yml policy -> route
(auto/local/global/explore/source-section) -> evidence pack
(DB graph + qmd derived corpus) ->
registered query prompt with tracing → QueryResultV031 with the full QTR trace.

See ``docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.3.1.md`` §17.
"""

from __future__ import annotations

from .models import (
    EvidenceItem,
    EvidencePack,
    GraphStatus,
    QueryRequest,
    QueryResultV031,
    ROUTES,
)
from .orchestrator import QueryOrchestrator
from .router import choose_route, graph_status

__all__ = [
    "QueryOrchestrator",
    "QueryRequest",
    "QueryResultV031",
    "EvidenceItem",
    "EvidencePack",
    "GraphStatus",
    "ROUTES",
    "choose_route",
    "graph_status",
]
