"""Claim support ranks and labels knowledge; it does not hide it.

`support_status` used to gate the search index: `materializer.py` selected only
`support_status = 'verified'` units. Validating an `uncertain` claim needs a
calibrated secondary validator, and when none is configured the unit stays
`unchecked` forever — so a missing config silently deleted knowledge from every
route, every ranker, and every reranker.

Measured on a real 36-source vault before this change: 1,701 of 2,799 live
units (61%) were unreachable, and only 1,149 of those were formula-related at
all. The user's own question — how an ellipsoid quadric is written as a matrix —
had its exact answer sitting in the database at confidence 1.0, invisible.

Same defect shape as the v0.43.0 relation-corroboration gate, same fix: the
signal becomes ranking and labelling instead of admission.
"""

from __future__ import annotations

from pathlib import Path

from curator import config as cfg
from curator import db
from curator.retrieval import materializer


def _vault(tmp_path: Path) -> cfg.WikiPaths:
    paths = cfg.WikiPaths(tmp_path)
    for layer_dir in (paths.contexts, paths.atoms, paths.concepts, paths.synthesis):
        layer_dir.mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    return paths


def _seed_unit(
    paths: cfg.WikiPaths,
    unit_id: str,
    statement: str,
    support_status: str,
    *,
    source_id: int = 1,
) -> None:
    """Insert one live unit on an authoritative generation."""
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO sources "
            "(id, relpath, content_hash, file_type, bytes, added_at, status) "
            "VALUES (?, ?, 'h', 'md', 1, '2026-08-07T00:00:00Z', 'curated')",
            (source_id, f"03_Notes/s{source_id}.md"),
        )
        conn.execute(
            "INSERT OR IGNORE INTO compiler_generations "
            "(id, source_id, status, prompt_contract_version, created_at, "
            " audit_json, updated_at) "
            "VALUES (?, ?, 'authoritative', '1', '2026-08-07T00:00:00Z', '{}', "
            "'2026-08-07T00:00:00Z')",
            (f"GEN-{source_id:04d}", source_id),
        )
        conn.execute(
            "INSERT INTO knowledge_units "
            "(id, unit_type, canonical_name, statement, source_span_ids, source_id, "
            " confidence, truth_status, atom_node_id, created_at, updated_at, "
            " semantic_hash, support_status, generation_id) "
            "VALUES (?, 'fact', ?, ?, '[]', ?, 1.0, 'source_supported', ?, "
            "'2026-08-07T00:00:00Z', '2026-08-07T00:00:00Z', ?, ?, ?)",
            (unit_id, unit_id, statement, source_id, f"ATM-{unit_id[-8:]}",
             f"sem-{unit_id}", support_status, f"GEN-{source_id:04d}"),
        )


def _indexed(paths: cfg.WikiPaths) -> dict[str, str]:
    """record_id -> support_status, for indexed knowledge units."""
    with db.connect(paths.state_db) as conn:
        rows = conn.execute(
            "SELECT record_id, json_extract(provenance_json,'$.support_status') AS s "
            "FROM search_documents WHERE record_type = 'knowledge_unit'"
        ).fetchall()
    return {str(r["record_id"]): str(r["s"] or "") for r in rows}


def test_unverified_knowledge_is_indexed_not_hidden(tmp_path: Path) -> None:
    """The regression that mattered: 61% of a real vault was unreachable."""
    paths = _vault(tmp_path)
    _seed_unit(paths, "KNU-verified1", "A verified claim about quadrics.", "verified")
    _seed_unit(paths, "KNU-unchecked", "$Q^* = Z \\breve{Q}^* Z^T$", "unchecked")
    _seed_unit(paths, "KNU-uncertain", "An uncertain claim.", "uncertain")
    _seed_unit(paths, "KNU-failed001", "A claim whose support check failed.", "failed")

    materializer.materialize_search_documents(paths.state_db)

    indexed = _indexed(paths)
    assert set(indexed) == {"KNU-verified1", "KNU-unchecked", "KNU-uncertain"}, (
        "never-validated knowledge must be reachable"
    )
    assert "KNU-failed001" not in indexed, (
        "`failed` is not a weaker tier — the support check RAN and found the "
        "cited span does not support the claim. Serving it would reintroduce "
        "ungrounded content that the compile pipeline already refuses to turn "
        "into an atom or feed to graph extraction."
    )


def test_the_index_carries_the_support_label(tmp_path: Path) -> None:
    """Serving unverified claims without saying so would trade one silence for another."""
    paths = _vault(tmp_path)
    _seed_unit(paths, "KNU-verified1", "Verified.", "verified")
    _seed_unit(paths, "KNU-unchecked", "Unchecked.", "unchecked")

    materializer.materialize_search_documents(paths.state_db)

    indexed = _indexed(paths)
    assert indexed["KNU-verified1"] == "verified"
    assert indexed["KNU-unchecked"] == "unchecked"


def test_support_status_change_re_materializes_the_document(tmp_path: Path) -> None:
    """Support drives ranking and the served label, so a stale copy misreports it."""
    paths = _vault(tmp_path)
    _seed_unit(paths, "KNU-unchecked", "A claim.", "unchecked")
    materializer.materialize_search_documents(paths.state_db)
    assert _indexed(paths)["KNU-unchecked"] == "unchecked"

    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE knowledge_units SET support_status = 'verified' WHERE id = ?",
            ("KNU-unchecked",),
        )
    materializer.materialize_search_documents(paths.state_db)

    assert _indexed(paths)["KNU-unchecked"] == "verified", (
        "the indexed label must follow the unit, not lag it"
    )


def test_retired_and_non_authoritative_units_are_still_excluded(tmp_path: Path) -> None:
    """Removing the support gate must not weaken the gates that are correct.

    §26.3 requires that staged/discarded generations never reach search, and a
    retired unit is not live knowledge. Only the support filter was wrong.
    """
    paths = _vault(tmp_path)
    _seed_unit(paths, "KNU-live0001", "Live.", "unchecked")
    _seed_unit(paths, "KNU-retired1", "Retired.", "verified")
    with db.connect(paths.state_db) as conn:
        conn.execute(
            "UPDATE knowledge_units SET retired_at = '2026-08-07T00:00:00Z' WHERE id = ?",
            ("KNU-retired1",),
        )
        conn.execute(
            "INSERT INTO compiler_generations (id, source_id, status, "
            "prompt_contract_version, created_at, audit_json, updated_at) "
            "VALUES ('GEN-staged', 2, 'staged', '1', '2026-08-07T00:00:00Z', "
            "'{}', '2026-08-07T00:00:00Z')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO sources "
            "(id, relpath, content_hash, file_type, bytes, added_at, status) "
            "VALUES (2, '03_Notes/s2.md', 'h2', 'md', 1, '2026-08-07T00:00:00Z', 'curated')"
        )
        conn.execute(
            "INSERT INTO knowledge_units "
            "(id, unit_type, canonical_name, statement, source_span_ids, source_id, "
            " confidence, truth_status, atom_node_id, created_at, updated_at, "
            " semantic_hash, support_status, generation_id) "
            "VALUES ('KNU-staged01', 'fact', 'S', 'Staged.', '[]', 2, 1.0, "
            "'source_supported', 'ATM-staged01', '2026-08-07T00:00:00Z', "
            "'2026-08-07T00:00:00Z', 'sem-staged', 'verified', 'GEN-staged')"
        )

    materializer.materialize_search_documents(paths.state_db)

    indexed = _indexed(paths)
    assert "KNU-live0001" in indexed
    assert "KNU-retired1" not in indexed, "retired knowledge is not live"
    assert "KNU-staged01" not in indexed, "§26.3: staged generations never serve"


def test_verified_outranks_unverified_at_equal_relevance() -> None:
    """The demotion has to reorder, not just relabel.

    Applied before ranking so the penalty affects the returned order; a
    strongly-matching unverified claim can still beat a weak verified one,
    because the alternative to that is the user getting nothing.
    """
    from curator.retrieval.engine import _SUPPORT_RANK_FACTORS

    assert _SUPPORT_RANK_FACTORS["verified"] == 1.0
    for weaker in ("unchecked", "uncertain"):
        assert _SUPPORT_RANK_FACTORS[weaker] < 1.0, f"{weaker} must rank below verified"
    assert _SUPPORT_RANK_FACTORS["uncertain"] < _SUPPORT_RANK_FACTORS["unchecked"], (
        "worse support must rank lower"
    )
    # Gentle enough that relevance still dominates: a unit twice as relevant
    # must win regardless of support state.
    assert min(_SUPPORT_RANK_FACTORS.values()) > 0.5


def test_a_search_hit_over_synthesis_keeps_its_layer_identity() -> None:
    """L3/L4 reached through search must not arrive anonymous.

    `EngineHit.record_type` was discarded when building the public `SearchHit`,
    so real synthesis content surfaced as a bare `search_hit` with an empty
    `synthesis_node_id` — invisible to the pack's own L3/L4 counters while
    being served in the pack.
    """
    from curator.search import SearchHit

    hit = SearchHit(full_path="x", docid="SYN-abc12345", record_type="synthesis_node")
    assert hit.record_type == "synthesis_node"
    assert hit.support_status == ""
