"""Every table-wide read of `knowledge_units` must decide about partials.

Since v0.62.0 an interrupted L2 extraction leaves DURABLE rows with
`generation_id IS NULL` so a re-run can adopt them (SYSTEM_BEHAVIOR L2 item 4).
Before that, such a row existed only inside one function's transaction and was
gone before anyone could observe it — so no query had to think about it.

Auditing the 27 readers at plan time found 15 that do not filter on
`generation_id`, and the codebase's habit is real: `synthesis_audit` read the
whole table with no filter at all. This test does not try to decide safety
automatically — it cannot. It forces the decision to be WRITTEN DOWN: a new
table-wide reader either filters, or lands in the allowlist below with a reason.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src" / "curator"

# (module, sql-prefix) -> why this reader may see a generation-less row.
# Verified individually at v0.62.0 P4; a bare entry with no reason is a bug.
ALLOWLIST: dict[tuple[str, str], str] = {
    ("db/_entities.py", "select * from knowledge_units where retired_at is null and support"):
        "list_eligible_knowledge_units: requires support_status='verified', which "
        "validate_claim_support sets only AFTER compile.py stamps generation_id. "
        "A partial defaults to 'unchecked' and cannot qualify. No production caller.",
    ("db/_entities.py", "select * from knowledge_units where source_id = ? order by"):
        "list_knowledge_units_for_source: the deliberately generation-agnostic "
        "helper. Tests and inspection use it precisely to SEE unpublished rows.",
    ("db/sources.py", "select id, atom_node_id, updated_at from knowledge_units where"):
        "sync-revision watermark: collects ids/timestamps to compute a successor "
        "revision. Including a partial can only move the watermark forward, which "
        "is what a new row should do.",
    ("pipeline/claim_support.py", "select distinct cs.knowledge_unit_id as uid from claim_supports"):
        "the dangling-support scan. A partial's supports point at rows that exist "
        "(its own units and live spans), so it produces no dangling finding; "
        "conditional discard deletes supports before units.",
    ("pipeline/claim_support.py", "select id, statement, source_span_ids, semantic_hash, support"):
        "reconcile_source: safe by ORDERING, not by the query. compile.py stamps "
        "generation_id onto every returned unit before reconcile runs, and an "
        "adopted partial is in candidate_unit_ids, which reconcile skips.",
    ("pipeline/compile.py", "select atom_node_id from knowledge_units where source_id = ? and"):
        "requires atom_node_id IS NOT NULL AND != ''. _persist_units never sets "
        "atom_node_id, so a partial is excluded by that clause.",
    ("pipeline/compile.py", "select id from knowledge_units where source_id = ?"):
        "_persist_source_projection_state: ids NOT in the authoritative set are "
        "used only to delete their artifact_dependencies rows. A partial has none, "
        "so the delete matches nothing.",
    ("pipeline/compile.py", "select id from knowledge_units where source_id = ? and retired_at is null order"):
        "recompile_source: re-validates the source's active units inside the "
        "publish transaction. A partial would have its support_status refreshed, "
        "which is harmless; the publish gate excludes it by generation_id.",
}

_ID_SCOPED = re.compile(r"\b(?:ku\.)?id (?:=|in) [(?]")


def _sql_literals(tree: ast.AST):
    """Every string constant, with f-string literal parts joined."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value
        elif isinstance(node, ast.JoinedStr):
            parts = "".join(
                v.value for v in node.values
                if isinstance(v, ast.Constant) and isinstance(v.value, str)
            )
            if parts:
                yield node.lineno, parts


def test_table_wide_knowledge_unit_readers_filter_or_are_justified() -> None:
    unjustified: list[str] = []
    seen: set[tuple[str, str]] = set()

    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        module = path.relative_to(SRC).as_posix()
        for lineno, raw in _sql_literals(tree):
            sql = " ".join(raw.lower().split())
            if "from knowledge_units" not in sql and "join knowledge_units" not in sql:
                continue
            if "generation_id" in sql or _ID_SCOPED.search(sql):
                continue
            # Longest prefix wins: two compile.py entries share an opening,
            # and matching the shorter one first would leave the other unseen.
            candidates = [
                k for k in ALLOWLIST if k[0] == module and sql.startswith(k[1])
            ]
            match = max(candidates, key=lambda k: len(k[1])) if candidates else None
            if match is None:
                unjustified.append(f"{module}:{lineno}\n    {sql[:150]}")
            else:
                seen.add(match)

    assert not unjustified, (
        "table-wide read(s) of knowledge_units with no generation_id filter and no "
        "recorded reason. Since v0.62.0 such a query can observe a durable "
        "unpublished row from an interrupted extraction. Either add "
        "`generation_id IS NOT NULL`, or add an ALLOWLIST entry in this file "
        "saying why a partial is harmless here:\n\n" + "\n\n".join(unjustified)
    )
    stale = set(ALLOWLIST) - seen
    assert not stale, (
        "ALLOWLIST entries that no longer match any query — the reader was "
        "changed or removed, so drop the entry: " + repr(sorted(stale))
    )
