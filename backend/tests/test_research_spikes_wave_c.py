"""Plan E Wave C adaptive, corrective, iterative, and progressive serving contracts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPIKES = REPO_ROOT / "backend" / "research_spikes"
sys.path.insert(0, str(SPIKES))

import contracts  # noqa: E402
import wave_c  # noqa: E402

CORPUS = SPIKES / "corpora" / "serving_stress.yml"


@pytest.fixture(scope="module")
def corpus() -> dict:
    return wave_c.load_yaml(CORPUS)


@pytest.fixture(scope="module")
def result() -> dict:
    return wave_c.run_wave_c(CORPUS)


def test_route_classifier_is_deterministic_and_matches_labels(corpus: dict) -> None:
    for query in corpus["routing"]:
        if query["partition"] == "holdout":
            continue
        first = wave_c.classify_route(query["text"])
        assert first == wave_c.classify_route(query["text"])
        assert first == query["expected_route"]


def test_wave_c_keeps_holdout_inaccessible(result: dict) -> None:
    serving = result["serving"]
    assert serving["holdout_measured"] is False
    for family in ("routing", "sufficiency", "iterative", "disclosure"):
        assert all(case["id"] != "HQ01" for case in serving[family]["cases"])


def test_wave_c_reports_each_family_separately(result: dict) -> None:
    serving = result["serving"]
    assert {"routing", "sufficiency", "iterative", "disclosure"} <= serving.keys()
    for family in ("routing", "sufficiency", "iterative", "disclosure"):
        families = {case["family"] for case in serving[family]["cases"]}
        assert families == {family}


def test_complexity_routing_beats_fixed_controls_on_accuracy(result: dict) -> None:
    routing = result["serving"]["routing"]
    accuracy = routing["policy_route_accuracy"]
    assert accuracy["complexity_aware"] == 1.0
    assert accuracy["complexity_aware"] > accuracy["always_local"]
    assert accuracy["complexity_aware"] > accuracy["always_complex"]
    # Adaptive routing must not be the most expensive policy.
    tokens = routing["policy_tokens"]
    assert tokens["complexity_aware"] < tokens["always_complex"]


def test_sufficiency_gate_beats_one_shot_at_lower_cost_than_always_correct(result: dict) -> None:
    suff = result["serving"]["sufficiency"]
    success = suff["policy_task_success"]
    correction = suff["policy_correction_rate"]
    assert success["sufficiency_gated"] > success["one_shot"]
    assert correction["sufficiency_gated"] < correction["always_correct"]
    # The honest false negative keeps the gate below perfect recall.
    assert suff["gate_recall"] < 1.0
    assert 0.0 <= suff["gate_precision"] <= 1.0


def test_bounded_iterative_is_capped_and_snapshot_consistent(result: dict) -> None:
    iterative = result["serving"]["iterative"]
    max_followups = 2
    assert iterative["max_retrieval_iterations"] <= 1 + max_followups
    assert iterative["snapshot_consistent"] is True
    success = iterative["policy_task_success"]
    assert success["bounded_iterative"] > success["one_shot"]
    assert success["bounded_iterative"] >= success["one_follow_up"]
    # The over-budget adversarial case must fail rather than loop unbounded.
    over_budget = next(case for case in iterative["cases"] if case["id"] == "IT03")
    assert over_budget["bounded_success"] is False
    assert over_budget["bounded_iterations"] == 1 + max_followups


def test_iterative_comparison_handles_query_without_hops() -> None:
    corpus = {
        "budgets": {"max_followups": 2},
        "iterative": [
            {
                "id": "IT_EMPTY",
                "partition": "adversarial",
                "hops": [],
                "expected_evidence": ["missing"],
                "snapshot": "snapshot-empty",
            }
        ],
    }

    iterative = wave_c.iterative_comparison(corpus)

    assert iterative["cases"][0]["bounded_iterations"] == 0
    assert iterative["policy_task_success"] == {
        "one_shot": 0.0,
        "one_follow_up": 0.0,
        "bounded_iterative": 0.0,
    }


def test_progressive_disclosure_recovers_omissions_without_silent_loss(result: dict) -> None:
    disclosure = result["serving"]["disclosure"]
    recall = disclosure["policy_recoverable_recall"]
    success = disclosure["policy_task_success"]
    assert recall["progressive"] == 1.0
    assert recall["progressive"] > recall["fixed_block"]
    assert recall["progressive"] > recall["fixed_top_k"]
    assert success["progressive"] == 1.0
    assert disclosure["snapshot_consistent"] is True
    # Every omitted item under progressive disclosure carries a stable handle.
    for case in disclosure["cases"]:
        progressive = case["progressive"]
        assert set(progressive["omitted_with_handles"]) == set(progressive["omitted"])


def test_disclosure_metrics_treats_empty_expected_set_as_fully_recoverable() -> None:
    metrics = wave_c._disclosure_metrics([], expected=set(), handles=[])

    assert metrics["recoverable_recall"] == 1.0
    assert metrics["task_success"] is True


def test_wave_c_is_repeatable(result: dict) -> None:
    assert result["serving"] == wave_c.run_wave_c(CORPUS)["serving"]


def test_wave_c_manifest_freezes_inputs_and_disposable_output() -> None:
    manifest = contracts.load_yaml(SPIKES / "manifests" / "wave_c.yml")
    assert manifest["partitions"]["holdout_accessed"] is False
    assert manifest["provider_model"]["provider_calls"] == 0
    assert manifest["raw_results"]["committed"] is False
    for name in ("serving_stress", "evaluation_protocol"):
        fixture = manifest["fixtures"][name]
        assert contracts.sha256_file(REPO_ROOT / fixture["path"]) == fixture["sha256"]
