"""Plan E Wave B graph, hierarchy, global, and expansion contracts."""

from __future__ import annotations

import sys
import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPIKES = REPO_ROOT / "backend" / "research_spikes"
sys.path.insert(0, str(SPIKES))

import contracts  # noqa: E402
import wave_b  # noqa: E402


@pytest.fixture(scope="module")
def corpus() -> dict:
    return wave_b.load_yaml(SPIKES / "corpora" / "graph_stress.yml")


@pytest.fixture(scope="module")
def result(corpus: dict) -> dict:
    return wave_b.run_wave_b(SPIKES / "corpora" / "graph_stress.yml")


def test_connected_components_and_denoising_are_deterministic(corpus: dict) -> None:
    first = wave_b.connected_components(corpus, min_confidence=0.5)
    second = wave_b.connected_components(corpus, min_confidence=0.5)
    assert first == second
    assert wave_b.giant_component_ratio(first) < wave_b.giant_component_ratio(
        wave_b.connected_components(corpus)
    )


def test_ppr_and_expansion_are_bounded_and_explainable(corpus: dict) -> None:
    ppr = wave_b.personalized_pagerank(corpus, ["N01"], limit=4)
    expansion = wave_b.graph_guided_expansion(corpus, ["N01"], min_confidence=0.5, max_edges=4)
    assert len(ppr) <= 4
    assert expansion["traversed_edges"] <= 4
    for item in [*ppr, *expansion["additions"]]:
        assert item["seed"] == "N01"
        assert item["path"][0] == "N01"
        assert item["path"][-1] == item["node"]
        assert len(item["edges"]) == len(item["path"]) - 1
    assert all(item["provenance"].startswith("SPAN-") for item in expansion["additions"])


def test_wave_b_keeps_holdout_inaccessible(result: dict) -> None:
    assert result["stress"]["holdout_measured"] is False
    assert all(case["id"] != "GQ07" for case in result["stress"]["cases"])


def test_wave_b_manifest_freezes_inputs_and_disposable_output() -> None:
    manifest = contracts.load_yaml(SPIKES / "manifests" / "wave_b.yml")
    assert manifest["partitions"]["holdout_accessed"] is False
    assert manifest["provider_model"]["provider_calls"] == 0
    assert manifest["raw_results"]["committed"] is False
    for name in ("graph_stress", "evaluation_protocol"):
        fixture = manifest["fixtures"][name]
        assert contracts.sha256_file(REPO_ROOT / fixture["path"]) == fixture["sha256"]


def test_wave_b_reports_associative_and_global_separately(result: dict) -> None:
    families = {case["family"] for case in result["stress"]["cases"]}
    assert {"associative", "global", "direct-factual"} <= families


def test_wave_b_ppr_and_filtered_expansion_improve_associative_recall(result: dict) -> None:
    associative = [case for case in result["stress"]["cases"] if case["family"] == "associative"]
    assert associative
    assert sum(case["ppr_recall"] for case in associative) >= sum(
        case["memory_path_recall"] for case in associative
    )
    assert all(case["expansion_forbidden_rate"] == 0.0 for case in associative)
    assert all(case["ppr_edge_update_budget"] > case["expansion"]["traversed_edges"] for case in associative)


def test_wave_b_query_relevant_global_beats_all_report_control(result: dict) -> None:
    global_cases = [case for case in result["stress"]["cases"] if case["family"] == "global"]
    assert global_cases
    assert all(case["query_relevant_precision"] > case["all_report_precision"] for case in global_cases)
    assert all(case["query_relevant_count"] < case["all_report_count"] for case in global_cases)


def test_wave_b_direct_factual_non_regression(result: dict) -> None:
    direct = [case for case in result["stress"]["cases"] if case["family"] == "direct-factual"]
    assert direct
    assert all(
        case["graph_direct_factual_recall_at_2"] >= case["lexical_direct_factual_recall_at_2"]
        for case in direct
    )
    assert all(case["graph_direct_factual_recall_at_2"] == 1.0 for case in direct)
    assert all(case["hard_negative_outranks"] == 0 for case in direct)


def test_wave_b_measures_edit_delete_churn(result: dict) -> None:
    stress = result["stress"]
    assert stress["denoised_seed_stability"] is True
    assert stress["low_confidence_delete_churn"] == 0.0
    assert stress["high_confidence_delete_churn"] > 0.0


def test_wave_b_is_repeatable(corpus: dict, result: dict) -> None:
    assert result["stress"] == wave_b.run_wave_b(SPIKES / "corpora" / "graph_stress.yml")["stress"]


def test_production_scale_reader_does_not_mutate_source(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            "CREATE TABLE schema_version(version INTEGER NOT NULL);"
            "INSERT INTO schema_version VALUES (7);"
            "CREATE TABLE graph_entities("
            "id TEXT PRIMARY KEY, canonical_name TEXT, description TEXT, source_span_ids TEXT);"
            "CREATE TABLE graph_relations("
            "source_entity_id TEXT, target_entity_id TEXT, relation_type TEXT, confidence REAL);"
            "INSERT INTO graph_entities VALUES ('A','Alpha','', '[\"SPAN-a\"]');"
            "INSERT INTO graph_entities VALUES ('B','Beta','', '[\"SPAN-b\"]');"
            "INSERT INTO graph_relations VALUES ('A','B','supports',0.9);"
        )
    before = contracts.sha256_file(db_path)
    summary = wave_b.production_scale_summary(db_path)
    assert contracts.sha256_file(db_path) == before
    assert summary["raw_giant_component_ratio"] == 1.0
