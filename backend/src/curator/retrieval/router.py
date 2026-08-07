"""Deterministic query routing (v0.3.1).

Routing is deterministic-first (SYSTEM_BEHAVIOR.md §17). An explicit
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

# Route signals, per language.
#
# These were English-only ASCII regexes until v0.47.0, which made routing
# silently language-bound: a Korean question could never match, so every
# non-English query fell through to `local` and the distilled L3/L4 layers were
# unreachable in the user's own language. The identical question in English
# routed `global`. USER_GUIDE documents Korean, English, Chinese, Japanese and
# Russian as supported, so the signal set covers those.
#
# `\b` is deliberately NOT used around CJK alternatives: Python's `\b` is
# defined on `\w` boundaries and does not fire between a Han/Hangul character
# and its neighbours, so a word-boundary-anchored CJK pattern silently never
# matches. Latin alternatives keep their boundaries to avoid matching inside
# longer words.
_EXPLORE_SIGNALS = re.compile(
    # English
    r"\b(what else|find connections?|new insight|explore|brainstorm|related ideas?|"
    r"how (?:might|could)|connections? between)\b"
    # Korean
    r"|또 (?:뭐|무엇)|관련(?:된)? ?(?:아이디어|생각)|연결(?:점|고리)?|탐색|브레인스토밍"
    r"|어떤 관련|무슨 관련"
    # Japanese
    r"|他に何|関連(?:する)?(?:アイデア|考え)|つながり|探索"
    # Chinese
    r"|还有什么|相关(?:的)?想法|联系|探索"
    # Russian
    r"|что ещё|что еще|связи между|исследовать",
    re.IGNORECASE,
)
_GLOBAL_SIGNALS = re.compile(
    # English
    r"\b(overall|summar(?:y|ize|ise)|across (?:all|the)|in general|big picture|"
    r"themes?|landscape|state of)\b"
    # Korean — includes the natural phrasing for "synthesize across papers"
    r"|전반(?:적|적으로)?|요약|종합(?:해|하여|적)?|전체(?:적)?|큰 ?그림|주제(?:들)?"
    r"|여러 ?(?:논문|문서|자료).{0,6}(?:종합|정리|비교)|통틀어"
    # Japanese
    r"|全体(?:的)?|要約|まとめ|総合|概観"
    # Chinese
    r"|总体|总结|综合|概览|整体"
    # Russian
    r"|в целом|обобщ|сводк|итог",
    re.IGNORECASE,
)


def graph_status(db_path: Path) -> GraphStatus:
    with db.connect(db_path) as conn:
        ent = conn.execute(
            "SELECT COUNT(*) FROM graph_entities "
            "WHERE resolution_state = 'canonical'"
        ).fetchone()[0]
        rel = conn.execute(
            "SELECT COUNT(*) FROM graph_relations "
            "WHERE lifecycle_status = 'active'"
        ).fetchone()[0]
        rep = conn.execute(
            "SELECT COUNT(*) FROM community_reports WHERE retired_at IS NULL"
        ).fetchone()[0]
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
        return _pick("local", "graph incomplete → local DB-native retrieval")
    return _pick("local", "entity/fact question")
