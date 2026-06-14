"""Plan C (v0.9.0) P6 — failing gold tests for CLAIM-GROUNDED REPORTS and
PRECISE SOURCE EDIT/DELETE RECONCILIATION.

TDD red tests written BEFORE the P6 deterministic graph-generation compiler.
They pin the frozen v9 contracts (SCHEMA §21.7, SYSTEM_BEHAVIOR §27.5/§27.8) and
MUST fail for the intended reason — ``db.rebuild_graph_generation`` and
``db.reconcile_source_change`` are not built yet — never via ``ImportError``.
Every forward reference is guarded with an intention-revealing message.

Contracts pinned (plan P6 "Verify"):
  * a community report is built from the EXACT ``active`` relations over canonical
    entities and the eligible verified claim support — the whole-community-span
    fallback is removed (§27.5, Arena decision 12);
  * community identity is content/config-derived: ``community_key`` is a function
    of ``(level, member_hash, support_hash, config_hash)`` (§21.7), so a changed
    active membership/support set yields a NEW key and the superseded community is
    set ``retired_at`` BEFORE synthesis consumes it;
  * an unchanged rebuild is idempotent — no entity/relation/report count
    amplification, same ``community_key``/``REP-`` id reused (§27.8);
  * a one-source edit/delete reconciles ONLY its downstream closure: supports whose
    span basis disappeared retire, relations dropping below 2 independent verified
    source lineages drop out of ``active``, the affected community/report retires,
    and an unrelated community's report id/key is untouched (§27.8);
  * ``dependency_hash`` is computed over the active-canonical-support closure and
    changes when that closure changes (§27.5 fresh dependencies).

P6 API hooks these tests pin (documented in RELAY for the implementer):
  ``db.rebuild_graph_generation(db_path, *, config_hash=None) -> dict`` returning a
  summary with ``communities``/``reports``/``retired``/``community_keys``;
  ``db.reconcile_source_change(db_path, *, source_id, removed_span_ids=None,
  config_hash=None) -> dict`` returning the measured closure.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db


@pytest.fixture()
def vault() -> Path:
    with tempfile.TemporaryDirectory() as t:
        paths = cfg.WikiPaths(Path(t))
        paths.internal.mkdir(parents=True, exist_ok=True)
        db.init_db(paths.state_db)
        yield paths.state_db


def _seed_entity(state_db: Path, name: str, etype: str = "concept") -> str:
    return db.upsert_graph_entity(state_db, canonical_name=name, entity_type=etype)


def _relate(state_db: Path, src: str, tgt: str, rtype: str = "rel") -> str:
    return db.upsert_graph_relation(
        state_db,
        source_entity_id=src,
        target_entity_id=tgt,
        relation_type=rtype,
        confidence=0.9,
    )


def _add_support(
    conn: sqlite3.Connection,
    relation_id: str,
    knu: str,
    lineage: str,
    support_hash: str,
    *,
    span: str,
    status: str = "verified",
) -> None:
    conn.execute(
        "INSERT INTO graph_relation_supports "
        "(relation_id, knowledge_unit_id, source_span_ids, assertion_source, "
        " confidence, support_status, support_hash, source_lineage_hash, "
        " created_at, updated_at) "
        'VALUES (?, ?, ?, "source_states", 0.9, ?, ?, ?, "t", "t")',
        # Serialize spans exactly as production does (json.dumps), so quote/backslash
        # escaping matches the real stored representation.
        (relation_id, knu, json.dumps([span]), status, support_hash, lineage),
    )


def _make_active_edge(
    vault: Path, src: str, tgt: str, *, tag: str
) -> str:
    """A relation with two INDEPENDENT verified supports (distinct lineages) so it
    compiles to ``active`` (§21.5 corroboration floor of >=2)."""
    rel = _relate(vault, src, tgt)
    with db.connect(vault) as conn:
        _add_support(conn, rel, f"KNU-{tag}-1", f"lin-{tag}-1", f"sh-{tag}-1",
                     span=f"SPAN-{tag}-1")
        _add_support(conn, rel, f"KNU-{tag}-2", f"lin-{tag}-2", f"sh-{tag}-2",
                     span=f"SPAN-{tag}-2")
    return rel


def _serving_reports(vault: Path) -> list[dict]:
    return [r for r in db.list_community_reports(vault) if not r.get("retired_at")]


# --------------------------------------------------------------------------- #
# Claim-grounded reports + content/config-derived identity (§27.5 / §21.7)
# --------------------------------------------------------------------------- #


def test_rebuild_builds_report_from_active_relations_only(vault: Path) -> None:
    """A report's grounding is the EXACT active relations + eligible support — a
    quarantined/unsupported relation in the same component never enters it, and
    there is no whole-community-span fallback (§27.5)."""
    rebuild = getattr(db, "rebuild_graph_generation", None)
    assert rebuild is not None, (
        "P6 must define db.rebuild_graph_generation (SYSTEM_BEHAVIOR §27.5/§27.8)"
    )
    a = _seed_entity(vault, "A")
    b = _seed_entity(vault, "B")
    c = _seed_entity(vault, "C")
    active = _make_active_edge(vault, a, b, tag="ab")
    # An UNSUPPORTED edge dangling off the active community: it shares endpoint B
    # but has zero verified support, so it compiles to quarantined/unsupported and
    # must NOT contribute its endpoint C or its spans to the report.
    unsupported = _relate(vault, b, c)

    rebuild(vault)

    reports = _serving_reports(vault)
    assert len(reports) == 1, (
        f"exactly one active community (A-B) must yield one report; got {reports}"
    )
    report = reports[0]
    assert report["relation_ids"] == [active], (
        "the report must cite ONLY the active relation; the unsupported edge "
        f"{unsupported} must be excluded (no broad-span fallback). Got "
        f"{report['relation_ids']}"
    )
    assert set(report["entity_ids"]) == {a, b}, (
        f"members are the active component's canonical entities only; got "
        f"{report['entity_ids']}"
    )
    assert c not in report["entity_ids"], (
        "the quarantined edge's far endpoint C must not be pulled into the report"
    )
    # Span grounding is the eligible verified support closure, not every span of
    # every entity in the component.
    assert set(report["source_span_ids"]) == {"SPAN-ab-1", "SPAN-ab-2"}, (
        f"report spans must be the active-support closure; got "
        f"{report['source_span_ids']}"
    )


def test_community_key_is_content_and_config_derived(vault: Path) -> None:
    """community_key = f(level, member_hash, support_hash, config_hash) (§21.7).
    Adding a new active member changes member_hash → a NEW key, and the superseded
    community is retired (correct restructuring over artificial id stability)."""
    rebuild = getattr(db, "rebuild_graph_generation", None)
    assert rebuild is not None, "P6 must define db.rebuild_graph_generation"
    a = _seed_entity(vault, "A")
    b = _seed_entity(vault, "B")
    _make_active_edge(vault, a, b, tag="ab")
    rebuild(vault)
    first = _serving_reports(vault)
    assert len(first) == 1
    key_before = first[0]["community_key"]
    member_hash_before = first[0]["member_hash"]
    config_hash = first[0]["config_hash"]
    assert member_hash_before, "rebuild must persist a content member_hash (§21.7)"
    assert config_hash, "rebuild must persist a config_hash identity (§21.7)"

    # Grow the active community: A-C becomes active too, so member set {A,B} -> {A,B,C}.
    c = _seed_entity(vault, "C")
    _make_active_edge(vault, a, c, tag="ac")
    rebuild(vault)

    serving = _serving_reports(vault)
    assert len(serving) == 1, (
        "the grown community is one report; the stale {A,B} report must be retired, "
        f"not served alongside it. Got {[r['community_key'] for r in serving]}"
    )
    assert serving[0]["community_key"] != key_before, (
        "a changed active membership must yield a new content-derived community_key "
        "(§21.7), not reuse the stale one"
    )
    assert serving[0]["member_hash"] != member_hash_before, (
        "member_hash must reflect the new member set"
    )
    # The superseded community is RETIRED, not deleted (auditable restructuring).
    all_reports = db.list_community_reports(vault, include_retired=True)
    retired = [r for r in all_reports if r["community_key"] == key_before]
    assert retired and retired[0].get("retired_at"), (
        "the superseded {A,B} community must be set retired_at before synthesis "
        "consumes it (§27.5)"
    )


def test_community_with_no_active_support_emits_no_report(vault: Path) -> None:
    """No broad-span fallback: a component held together only by an unsupported
    relation has no eligible active claim support, so it produces no served
    report (§27.5: a finding without eligible claim support is not emitted)."""
    rebuild = getattr(db, "rebuild_graph_generation", None)
    assert rebuild is not None, "P6 must define db.rebuild_graph_generation"
    a = _seed_entity(vault, "A")
    b = _seed_entity(vault, "B")
    _relate(vault, a, b)  # zero verified support -> unsupported -> not active
    rebuild(vault)
    assert _serving_reports(vault) == [], (
        "a community with no active eligible support must emit no report "
        "(no whole-community-span fallback, §27.5)"
    )


# --------------------------------------------------------------------------- #
# Idempotent rebuild — no count amplification (§27.8)
# --------------------------------------------------------------------------- #


def test_unchanged_rebuild_has_no_count_amplification(vault: Path) -> None:
    rebuild = getattr(db, "rebuild_graph_generation", None)
    assert rebuild is not None, "P6 must define db.rebuild_graph_generation"
    a = _seed_entity(vault, "A")
    b = _seed_entity(vault, "B")
    c = _seed_entity(vault, "C")
    d = _seed_entity(vault, "D")
    _make_active_edge(vault, a, b, tag="ab")
    _make_active_edge(vault, c, d, tag="cd")

    first = rebuild(vault)
    reports_1 = _serving_reports(vault)
    ids_1 = sorted(r["id"] for r in reports_1)
    keys_1 = sorted(r["community_key"] for r in reports_1)
    assert first.get("communities") == 2, (
        f"two disjoint active edges -> two communities; got {first}"
    )

    # Tag every report with a sentinel updated_at. A true no-op rebuild must NOT
    # rewrite the row, so the sentinel survives. (Comparing live timestamps is
    # unreliable: same-second rebuilds share an `_now_iso()` value even when the row
    # IS rewritten, masking the amplification — the sentinel makes the write visible.)
    with db.connect(vault) as conn:
        conn.execute("UPDATE community_reports SET updated_at = 'SENTINEL'")

    second = rebuild(vault)
    reports_2 = _serving_reports(vault)
    ids_2 = sorted(r["id"] for r in reports_2)
    keys_2 = sorted(r["community_key"] for r in reports_2)

    assert ids_2 == ids_1, (
        "an unchanged rebuild must reuse the same REP- ids (no amplification, "
        f"§27.8); {ids_1} -> {ids_2}"
    )
    assert keys_2 == keys_1, "community_key identities must be stable on re-run"
    assert second.get("communities") == first.get("communities"), (
        "no community count amplification on unchanged rebuild"
    )
    assert second.get("retired", 0) == 0, (
        "an unchanged rebuild retires nothing"
    )
    # No write amplification: an unchanged community is NOT rewritten, so the sentinel
    # survives (§27.8 — else INSERT OR REPLACE churns updated_at and downstream sync).
    assert all(r["updated_at"] == "SENTINEL" for r in reports_2), (
        "an unchanged rebuild must skip the write for every unchanged community "
        f"(write amplification); got {[r['updated_at'] for r in reports_2]}"
    )


# --------------------------------------------------------------------------- #
# Fresh dependency hash over the active-support closure (§27.5)
# --------------------------------------------------------------------------- #


def test_dependency_hash_tracks_active_support_closure(vault: Path) -> None:
    rebuild = getattr(db, "rebuild_graph_generation", None)
    assert rebuild is not None, "P6 must define db.rebuild_graph_generation"
    a = _seed_entity(vault, "A")
    b = _seed_entity(vault, "B")
    rel = _make_active_edge(vault, a, b, tag="ab")
    rebuild(vault)
    h1 = _serving_reports(vault)[0]["dependency_hash"]
    assert h1, "rebuild must record a dependency_hash over its inputs (§27.5)"

    # Add a THIRD independent support span to the same active relation: the active
    # membership/support set within {A,B} changes -> the dependency closure (and so
    # the content identity) changes.
    with db.connect(vault) as conn:
        _add_support(conn, rel, "KNU-ab-3", "lin-ab-3", "sh-ab-3", span="SPAN-ab-3")
    rebuild(vault)
    serving = _serving_reports(vault)
    assert len(serving) == 1
    assert serving[0]["dependency_hash"] != h1, (
        "a changed active-support closure must change the dependency_hash (§27.5 "
        "fresh dependencies)"
    )


# --------------------------------------------------------------------------- #
# Precise source edit/delete reconciliation closure (§27.8)
# --------------------------------------------------------------------------- #


def test_reconcile_source_change_touches_only_the_affected_closure(
    vault: Path,
) -> None:
    """Removing one source's spans retires its supports, drops its relation out of
    ``active``, retires its now-empty community/report — and leaves an unrelated
    community's report id/key BYTE-IDENTICAL (§27.8 measured closure)."""
    reconcile = getattr(db, "reconcile_source_change", None)
    rebuild = getattr(db, "rebuild_graph_generation", None)
    assert reconcile is not None, (
        "P6 must define db.reconcile_source_change (SYSTEM_BEHAVIOR §27.8)"
    )
    assert rebuild is not None, "P6 must define db.rebuild_graph_generation"

    a = _seed_entity(vault, "A")
    b = _seed_entity(vault, "B")
    c = _seed_entity(vault, "C")
    d = _seed_entity(vault, "D")
    edge_ab = _make_active_edge(vault, a, b, tag="ab")  # source under edit
    _make_active_edge(vault, c, d, tag="cd")            # unrelated, untouched

    rebuild(vault)
    before = {r["community_key"]: r for r in _serving_reports(vault)}
    assert len(before) == 2
    cd_key = next(
        k for k, r in before.items() if set(r["entity_ids"]) == {c, d}
    )
    cd_report_id = before[cd_key]["id"]
    # Sentinel-tag the unrelated C-D row so a spurious rewrite is detectable
    # regardless of timestamp resolution.
    with db.connect(vault) as conn:
        conn.execute(
            "UPDATE community_reports SET updated_at = 'SENTINEL-CD' WHERE id = ?",
            (cd_report_id,),
        )

    # The A-B edge's support came from spans SPAN-ab-1 / SPAN-ab-2; deleting BOTH
    # removes the relation's entire verified support basis.
    closure = reconcile(
        vault, source_id=1, removed_span_ids=["SPAN-ab-1", "SPAN-ab-2"]
    )

    # The A-B relation lost all verified support -> no longer active.
    with db.connect(vault) as conn:
        status = conn.execute(
            "SELECT lifecycle_status FROM graph_relations WHERE id = ?", (edge_ab,)
        ).fetchone()[0]
    assert status != "active", (
        "an edge that lost its verified support basis must drop out of active "
        f"(§27.8); still {status!r}"
    )

    serving = {r["community_key"]: r for r in _serving_reports(vault)}
    assert cd_key in serving, "the unrelated C-D community must remain served"
    assert serving[cd_key]["id"] == cd_report_id, (
        "the unrelated community's report id must be UNTOUCHED by a different "
        "source's reconciliation (§27.8 precise closure)"
    )
    assert serving[cd_key]["updated_at"] == "SENTINEL-CD", (
        "the unrelated community's row must be byte-stable (its sentinel survives) — a "
        "different source's reconcile must not rewrite it (§27.8 no write amplification)"
    )
    assert all(set(r["entity_ids"]) != {a, b} for r in serving.values()), (
        "the A-B community lost its active basis and must not still serve"
    )
    # The closure summary names the retirement so the change set is measurable.
    assert closure.get("retired", 0) >= 1, (
        f"reconciliation must report the retired A-B community in its closure; "
        f"got {closure}"
    )


def test_reconcile_span_prefix_does_not_over_stale(vault: Path) -> None:
    """The SQL pre-filter that narrows reconcile's support scan must not over-stale a
    support whose span id merely SHARES A PREFIX with a removed span — removing
    SPAN-1 must leave SPAN-10 untouched. The exact-set membership check guards the
    LIKE pre-filter (§27.8 precise closure)."""
    reconcile = getattr(db, "reconcile_source_change", None)
    rebuild = getattr(db, "rebuild_graph_generation", None)
    assert reconcile is not None and rebuild is not None, "P6 must define both hooks"
    a = _seed_entity(vault, "A")
    b = _seed_entity(vault, "B")
    rel = _relate(vault, a, b)
    with db.connect(vault) as conn:
        # Two INDEPENDENT supports on prefix-overlapping spans SPAN-1 and SPAN-10.
        _add_support(conn, rel, "KNU-1", "lin-1", "sh-1", span="SPAN-1")
        _add_support(conn, rel, "KNU-2", "lin-2", "sh-2", span="SPAN-10")
    rebuild(vault)
    assert len(_serving_reports(vault)) == 1, "A-B is active (2 lineages)"

    reconcile(vault, source_id=1, removed_span_ids=["SPAN-1"])

    with db.connect(vault) as conn:
        statuses = {
            str(r["knowledge_unit_id"]): str(r["support_status"])
            for r in conn.execute(
                "SELECT knowledge_unit_id, support_status "
                "FROM graph_relation_supports WHERE relation_id = ?",
                (rel,),
            ).fetchall()
        }
    assert statuses["KNU-1"] == "stale", "the exact SPAN-1 support must be staled"
    assert statuses["KNU-2"] == "verified", (
        "removing SPAN-1 must NOT stale the SPAN-10 support — a prefix overlap must "
        "not cause a false-positive match"
    )


def test_reconcile_matches_span_id_with_double_quote(vault: Path) -> None:
    """A span id containing a double quote is stored escaped (``\\"``) inside the JSON
    array, so the LIKE pre-filter needle must be ``json.dumps(sid)`` — a raw
    ``%"sid"%`` needle would never match the escaped string and would silently skip
    the support (false-negative under-staling the Python guard cannot recover)."""
    reconcile = getattr(db, "reconcile_source_change", None)
    rebuild = getattr(db, "rebuild_graph_generation", None)
    assert reconcile is not None and rebuild is not None, "P6 must define both hooks"
    a = _seed_entity(vault, "A")
    b = _seed_entity(vault, "B")
    rel = _relate(vault, a, b)
    quoted = 'SPAN"Q'
    with db.connect(vault) as conn:
        _add_support(conn, rel, "KNU-1", "lin-1", "sh-1", span=quoted)
        _add_support(conn, rel, "KNU-2", "lin-2", "sh-2", span="SPAN-2")
    rebuild(vault)

    reconcile(vault, source_id=1, removed_span_ids=[quoted])

    with db.connect(vault) as conn:
        status = str(
            conn.execute(
                "SELECT support_status FROM graph_relation_supports "
                "WHERE knowledge_unit_id = 'KNU-1'"
            ).fetchone()[0]
        )
    assert status == "stale", (
        "a span id containing a double quote must be matched and staled via the "
        "json.dumps needle, not silently skipped"
    )


def test_reconcile_handles_more_removed_spans_than_var_limit(vault: Path) -> None:
    """``removed_span_ids`` longer than SQLITE_MAX_VARIABLE_NUMBER must not crash the
    LIKE query — it is chunked. The real removed span is still staled across the chunk
    boundary, and an unrelated span is untouched."""
    reconcile = getattr(db, "reconcile_source_change", None)
    rebuild = getattr(db, "rebuild_graph_generation", None)
    assert reconcile is not None and rebuild is not None, "P6 must define both hooks"
    a = _seed_entity(vault, "A")
    b = _seed_entity(vault, "B")
    rel = _relate(vault, a, b)
    with db.connect(vault) as conn:
        _add_support(conn, rel, "KNU-1", "lin-1", "sh-1", span="SPAN-real")
        _add_support(conn, rel, "KNU-2", "lin-2", "sh-2", span="SPAN-keep")
    rebuild(vault)

    # 1500 dummy spans + the real one forces multiple LIKE chunks (chunk size 900).
    removed = [f"SPAN-dummy-{i}" for i in range(1500)] + ["SPAN-real"]
    reconcile(vault, source_id=1, removed_span_ids=removed)

    with db.connect(vault) as conn:
        statuses = {
            str(r["knowledge_unit_id"]): str(r["support_status"])
            for r in conn.execute(
                "SELECT knowledge_unit_id, support_status FROM graph_relation_supports"
            ).fetchall()
        }
    assert statuses["KNU-1"] == "stale", (
        "the real removed span must be staled even past the chunk boundary"
    )
    assert statuses["KNU-2"] == "verified", "an unrelated span must be untouched"
