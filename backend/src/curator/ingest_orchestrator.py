"""DAG downstream-expansion helper.

The v0.2.x batch L2 extraction machinery that used to live here was removed in
the v0.3.1 cutover (the compile pipeline in ``pipeline/`` replaced it). The only
piece still used is the SQL downstream expansion over ``dag_edges``, consumed by
``sync``.
"""

from __future__ import annotations

from collections import deque

from . import config as cfg
from . import db


def _expand_downstream_via_sql(paths: cfg.WikiPaths, node_ids: list[str]) -> set[str]:
    """Return node_ids plus all transitive downstream DAG nodes from dag_edges."""
    if not node_ids:
        return set()
    affected = set(node_ids)
    queue: deque[str] = deque(node_ids)
    with db.connect(paths.state_db) as conn:
        while queue:
            current = queue.popleft()
            rows = conn.execute(
                "SELECT to_id FROM dag_edges WHERE from_id = ?",
                (current,),
            ).fetchall()
            for row in rows:
                to_id = str(row["to_id"])
                if to_id not in affected:
                    affected.add(to_id)
                    queue.append(to_id)
    return affected
