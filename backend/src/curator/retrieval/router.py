"""Deterministic query routing (v0.3.1).

Routing is deterministic-first (SYSTEM_BEHAVIOR_v0.3.1.md §17). An explicit
``--mode`` wins when the policy allows it; otherwise simple signals choose the
route. The LLM router contract (curator.query_router) exists for the ambiguous
case but deterministic routing covers the common paths first.
"""

from __future__ import annotations

import re
from pathlib import Path

from .. import db
from ..curate_yml import CurationPolicy
from .models import GraphStatus, QueryRequest

__all__ = ["graph_status", "choose_route"]

_EXPLORE_SIGNALS = re.compile(
    r"\b(what else|find connections?|new insight|explore|brainstorm|related ideas?|"
    r"how (?:might|could)|connections? between)\b",
    re.IGNORECASE,
)
_GLOBAL_SIGNALS = re.compile(
    r"\b(overall|summar(?:y|ize|ise)|across (?:all|the)|in general|big picture|"
    r"themes?|landscape|state of)\b",
    re.IGNORECASE,
)


def graph_status(db_path: Path) -> GraphStatus:
    with db.connect(db_path) as conn:
        ent = conn.execute("SELECT COUNT(*) FROM graph_entities").fetchone()[0]
        rel = conn.execute("SELECT COUNT(*) FROM graph_relations").fetchone()[0]
        rep = conn.execute("SELECT COUNT(*) FROM community_reports").fetchone()[0]
    return GraphStatus(has_entities=ent > 0, has_relations=rel > 0, has_reports=rep > 0)


def choose_route(
    request: QueryRequest, policy: CurationPolicy, status: GraphStatus
) -> tuple[str, str]:
    """Return (route, reason). Falls back to allowed routes / local when needed."""
    # source-section is a precise, always-safe scoped lookup of a named source, so
    # it is permitted regardless of the workspace's reasoning allowed_modes.
    allowed = policy.allowed_routes | {"source-section"}

    def _pick(route: str, reason: str) -> tuple[str, str]:
        if route in allowed:
            return route, reason
        # Honor policy: degrade to a permitted route.
        if "local" in allowed:
            return "local", f"{reason}; '{route}' not allowed by curate.yml → local"
        return next(iter(allowed)), f"{reason}; '{route}' not allowed → policy default"

    # 1. Explicit mode (not auto) wins when allowed.
    if request.mode and request.mode != "auto":
        if request.mode in allowed:
            return request.mode, "explicit --mode"
        return _pick(request.mode, "explicit --mode not allowed")

    # 2. Source-scoped question.
    if request.source_key:
        return _pick("source-section", "question scoped to a specific source")

    q = request.working_query

    # 3. Discovery signals → explore (only if exploration enabled + graph exists).
    if _EXPLORE_SIGNALS.search(q) and policy.exploration_enabled and status.has_relations:
        return _pick("explore", "discovery signal in question")

    # 4. Broad synthesis → global (needs community reports).
    if _GLOBAL_SIGNALS.search(q) and status.has_reports:
        return _pick("global", "broad-synthesis signal in question")

    # 5. Default: local entity/fact answer.
    if not status.has_entities:
        return _pick("local", "graph incomplete → local with qmd fallback")
    return _pick("local", "entity/fact question")
