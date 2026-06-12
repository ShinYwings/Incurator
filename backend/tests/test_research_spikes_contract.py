"""Plan E P0/P1 safety, corpus, and candidate-dossier contracts."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SPIKES = REPO_ROOT / "backend" / "research_spikes"
ATLAS = REPO_ROOT / "docs" / "specs" / "failure_atlas"

sys.path.insert(0, str(SPIKES))
SPEC = importlib.util.spec_from_file_location("research_contracts", SPIKES / "contracts.py")
assert SPEC and SPEC.loader
contracts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contracts)


def _load(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_p0_frozen_failure_atlas_hashes_match_ledger() -> None:
    ledger = _load(SPIKES / "manifests" / "p0_baseline_ledger.yml")
    atlas = ledger["corpora"]["failure_atlas"]
    assert contracts.sha256_file(REPO_ROOT / atlas["fixture"]) == atlas["fixture_sha256"]
    assert contracts.sha256_file(REPO_ROOT / atlas["qrels"]) == atlas["qrels_sha256"]


def test_p0_failure_atlas_baseline_has_no_holdout_measurement() -> None:
    qrels = _load(ATLAS / "qrels.yml")
    holdout = [q for q in qrels["queries"] if q["partition"] == "holdout"]
    assert holdout and all(q.get("frozen") is True for q in holdout)


def test_p0_graph_stress_corpus_is_provenance_complete_and_partitioned() -> None:
    corpus = _load(SPIKES / "corpora" / "graph_stress.yml")
    nodes = {node["id"]: node for node in corpus["nodes"]}
    assert len(nodes) == len(corpus["nodes"])
    assert all(node["provenance"].startswith("SPAN-") for node in nodes.values())
    query_ids = {query["id"] for query in corpus["queries"]}
    declared = {qid for ids in corpus["partitions"].values() for qid in ids}
    assert query_ids == declared
    for query in corpus["queries"]:
        if query["partition"] == "holdout":
            assert query.get("frozen") is True


def test_p0_graph_stress_expected_paths_resolve_to_declared_edges() -> None:
    corpus = _load(SPIKES / "corpora" / "graph_stress.yml")
    edges = {
        (edge["source"], edge["target"]) for edge in corpus["edges"]
    } | {
        (edge["target"], edge["source"]) for edge in corpus["edges"]
    }
    for query in corpus["queries"]:
        path = query.get("expected_path", [])
        assert all((left, right) in edges for left, right in zip(path, path[1:]))


def test_p0_sqlite_snapshot_copy_is_read_only_and_source_unchanged(tmp_path: Path) -> None:
    import prepare_inputs

    source = tmp_path / "source.sqlite"
    destination = tmp_path / "copy.sqlite"
    import sqlite3

    with sqlite3.connect(source) as conn:
        conn.executescript(
            "CREATE TABLE schema_version(version INTEGER NOT NULL);"
            "INSERT INTO schema_version VALUES (7);"
            "CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT);"
            "INSERT INTO sample(value) VALUES ('synthetic');"
        )
    before = contracts.sha256_file(source)
    summary = prepare_inputs.copy_sqlite_snapshot(source, destination)
    assert contracts.sha256_file(source) == before == summary["source_sha256_after"]
    assert summary["schema_version"] == 7
    assert summary["table_counts"]["sample"] == 1


def test_p1_all_required_candidate_dossiers_are_complete_and_scoped() -> None:
    expected = set(_load(SPIKES / "manifests" / "p0_baseline_ledger.yml")["candidate_targets"])
    atlas_ids = {f"F{int(path.stem[1:])}" for path in (ATLAS / "cases").glob("F*.yml")}
    dossiers = {}
    for path in sorted((SPIKES / "dossiers").glob("*.yml")):
        dossier = _load(path)
        dossiers[dossier["candidate_id"]] = dossier
        assert contracts.validate_dossier(dossier) == [], path.name
        assert all(source["url"].startswith("https://") for source in dossier["primary_sources"])
        assert dossier["spike"]["metrics"] == dossier["metrics"]
        if dossier["target"]["kind"] == "failure-atlas":
            assert set(dossier["target"]["failure_ids"]) <= atlas_ids
    assert set(dossiers) == expected


def test_p1_validate_dossier_guards_malformed_shapes_without_crashing() -> None:
    dossier = {
        "spike": None,
        "target": {"kind": "failure-atlas"},
        "primary_sources": ["not-a-mapping"],
    }
    errors = contracts.validate_dossier(dossier)
    assert "spike.independent_variable must isolate the mechanism" in errors
    assert "failure-atlas target requires failure_ids" in errors
    assert "target requires a scoped question" in errors
    assert "every primary source needs title, url, and claim_boundary" in errors


def test_p0_sqlite_readonly_summary_handles_missing_schema_version(tmp_path: Path) -> None:
    import sqlite3

    legacy = tmp_path / "legacy.sqlite"
    with sqlite3.connect(legacy) as conn:
        conn.executescript("CREATE TABLE sample(id INTEGER PRIMARY KEY);")
    summary = contracts.sqlite_readonly_summary(legacy)
    assert summary["schema_version"] is None
    assert summary["table_counts"]["sample"] == 0


def test_p1_no_dossier_authorizes_production_implementation() -> None:
    prohibited = {"implement-now", "adopt-framework", "production-approved"}
    for path in (SPIKES / "dossiers").glob("*.yml"):
        dossier = _load(path)
        text = path.read_text(encoding="utf-8").lower()
        assert dossier["preliminary_decision"] in contracts.DECISIONS
        assert not any(term in text for term in prohibited)


def test_research_spikes_are_not_imported_by_production() -> None:
    for path in (REPO_ROOT / "backend" / "src" / "curator").rglob("*.py"):
        assert "research_spikes" not in path.read_text(encoding="utf-8"), path


def test_p0_p1_roles_are_separated() -> None:
    ledger = _load(SPIKES / "manifests" / "p0_baseline_ledger.yml")
    roles = ledger["role_separation"]
    assert len({roles["dossier_author"], roles["spike_executor"], roles["decision_reviewer"]}) == 3
