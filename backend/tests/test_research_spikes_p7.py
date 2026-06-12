"""Plan E P7 untouched-holdout, red-team, and decision-synthesis contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPIKES = REPO_ROOT / "backend" / "research_spikes"
sys.path.insert(0, str(SPIKES))

import contracts  # noqa: E402
import p7_holdout  # noqa: E402

CORPORA = SPIKES / "corpora"

EXPECTED_DECISION_IDS = {
    "fine-grained-rag-diagnostics",
    "context-enriched-chunks",
    "passage-entity-ppr",
    "denoised-hierarchy",
    "query-relevant-global",
    "kg-guided-expansion",
    "complexity-aware-routing",
    "retrieval-sufficiency-gate",
    "bounded-iterative-retrieval",
    "progressive-context-disclosure",
    "selective-formula-recovery",
    "formula-preserving-distillation",
}


@pytest.fixture(scope="module")
def result() -> dict:
    return p7_holdout.run_p7(CORPORA)


def test_p7_measures_exactly_the_four_holdout_items_once(result: dict) -> None:
    holdout = result["holdout"]
    assert result["run_count"] == 1
    retrieval_ids = [
        case["id"] for run in holdout["retrieval_units"]["runs"] for case in run["cases"]
    ]
    assert set(retrieval_ids) == {"RUQ05"}
    assert len(holdout["retrieval_units"]["runs"]) == 9
    assert [case["id"] for case in holdout["graph"]["cases"]] == ["GQ07"]
    assert [case["id"] for case in holdout["serving"]["cases"]] == ["HQ01"]
    assert [case["id"] for case in holdout["formula"]["cases"]] == ["FR05"]
    assert all(section["holdout_measured"] is True for section in holdout.values())


def test_p7_does_not_consume_the_failure_atlas_holdout(result: dict) -> None:
    leakage = result["red_team"]["benchmark_leakage"]
    assert leakage["failure_atlas_holdout_consumed"] is False
    assert leakage["failure_atlas_holdout_reserved_for"] == "plan-d2"
    serialized = json.dumps(result)
    assert "ATM-fc000007" not in serialized
    assert "mangrove" not in serialized.lower()


def test_p7_graph_holdout_exposes_the_confidence_filter_tradeoff(result: dict) -> None:
    case = result["holdout"]["graph"]["cases"][0]
    assert case["seeds"] == ["N06"]
    assert case["memory_path_recall"] == 1.0
    assert case["ppr_recall"] == 1.0
    # The true N07->N08 ecology-link edge (confidence 0.25) sits below the
    # frozen 0.5 filter, so bounded filtered expansion honestly misses N08.
    assert case["expansion_recall"] == 0.5
    assert [item["node"] for item in case["expansion"]["additions"]] == ["N05", "N07"]
    # Unfiltered PPR reaches N08 but again surfaces the noisy-bridge node N14.
    assert "N14" in [item["node"] for item in case["ppr"]]
    assert case["expansion_within_budget"] is True
    assert case["expansion_traversed_edges"] < case["ppr_edge_update_budget"]
    for addition in case["expansion"]["additions"]:
        assert addition["provenance"].startswith("SPAN-")
        assert addition["seed"] == "N06"
        assert addition["path"][0] == "N06"


def test_p7_fine_grained_diagnostics_expose_the_blind_probe_failure(result: dict) -> None:
    for run in result["holdout"]["retrieval_units"]["runs"]:
        case = run["cases"][0]
        assert case["recall_at_1"] == 0.0
        assert case["provenance_resolution_rate"] == 1.0
        if run["mode"] in {"vec", "hybrid"}:
            # Aggregate Recall@5 alone would report success on the blind probe;
            # top-1 citation correctness and hard-negative outranks expose it.
            assert case["recall_at_5"] == 1.0
            assert case["citation_correctness"] == 0.0
            assert case["hard_negative_outranks"] == 2
        else:
            assert case["ranked"] == []


def test_p7_routing_probe_routes_correctly_under_frozen_classifier(result: dict) -> None:
    case = result["holdout"]["serving"]["cases"][0]
    assert case["expected_route"] == "local"
    assert case["classified_route"] == "local"
    assert case["policies"]["always_complex"]["route"] == "iterative"
    assert case["policies"]["complexity_aware"]["tokens"] == 1


def test_p7_formula_holdout_fabricates_nothing_under_total_loss(result: dict) -> None:
    case = result["holdout"]["formula"]["cases"][0]
    assert case["proven_loss_region"] is True
    assert case["recovery"] is None
    assert case["fabricated_formulas"] == []
    assert case["distillation_added_formulas"] == []
    assert case["loss_remains_explicit"] is True
    assert case["policy_formula_recall"] == {
        "parser_only": 0.0,
        "current_extraction": 0.0,
        "selective_recovery": 0.0,
    }
    assert case["selective_recovery_cost"] == 0
    assert case["whole_corpus_recovery_cost"] == 10


def test_p7_red_team_audits_all_pass(result: dict) -> None:
    red_team = result["red_team"]
    assert red_team["all_passed"] is True
    for name in ("provenance", "benchmark_leakage", "framework_bias", "cost", "update_delete"):
        assert red_team[name]["passed"] is True, name
    assert red_team["framework_bias"]["candidate_framework_imports"] == []
    assert red_team["update_delete"]["formula_invalidation_accuracy"] == 1.0
    assert red_team["update_delete"]["formula_stale_recovery_served"] is False


def test_p7_decisions_are_scoped_and_never_authorize_production(result: dict) -> None:
    decisions = result["decisions"]
    assert {record["candidate_id"] for record in decisions} == EXPECTED_DECISION_IDS
    for record in decisions:
        assert record["final_decision"] in contracts.DECISIONS
        assert record["production_implementation_authorized"] is False
        assert record["downstream_owner"] in contracts.DOWNSTREAM_OWNERS
        assert record["holdout_evidence"].strip()
    adopted = {
        record["candidate_id"]: record["downstream_owner"]
        for record in decisions
        if record["final_decision"] == "adopt-contract"
    }
    assert adopted == {
        "fine-grained-rag-diagnostics": "plan-d2",
        "query-relevant-global": "program-3",
        "progressive-context-disclosure": "program-3",
        "formula-preserving-distillation": "program-2",
    }
    rejected = {
        record["candidate_id"]
        for record in decisions
        if record["final_decision"] == "reject-default"
    }
    assert rejected == {"passage-entity-ppr"}


def test_p7_corpora_are_hash_guarded_and_unchanged(result: dict) -> None:
    assert result["corpus_unchanged_after_run"] is True
    for name, recorded in result["corpus_hashes"].items():
        assert contracts.sha256_file(CORPORA / f"{name}.yml") == recorded


def test_p7_manifest_freezes_inputs_and_disposable_output() -> None:
    manifest = contracts.load_yaml(SPIKES / "manifests" / "p7.yml")
    assert manifest["partitions"]["holdout_accessed"] is True
    assert manifest["partitions"]["holdout_run_count"] == 1
    assert manifest["provider_model"]["provider_calls"] == 0
    assert manifest["raw_results"]["committed"] is False
    for fixture in manifest["fixtures"].values():
        assert contracts.sha256_file(REPO_ROOT / fixture["path"]) == fixture["sha256"]
    assert manifest["failure_atlas_holdout"]["consumed"] is False
