"""Plan E P2 metric contracts and Wave A deterministic spike tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SPIKES = REPO_ROOT / "backend" / "research_spikes"
sys.path.insert(0, str(SPIKES))

import metrics  # noqa: E402
import wave_a  # noqa: E402


def _load(name: str) -> dict:
    value = yaml.safe_load((SPIKES / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_p2_hand_computable_metric_contracts() -> None:
    ranked = ["B", "A", "C"]
    assert metrics.recall_at(ranked, {"A", "C"}, 1) == 0.0
    assert metrics.recall_at(ranked, {"A", "C"}, 3) == 1.0
    assert metrics.mrr_at(ranked, {"A"}, 3) == 0.5
    assert metrics.hard_negative_outranks(ranked, {"A"}, {"B", "C"}) == 1
    assert metrics.set_correctness({"S1", "BAD"}, {"S1", "S2"}) == 0.5
    assert metrics.set_coverage({"S1", "BAD"}, {"S1", "S2"}) == 0.5
    with pytest.raises(ValueError):
        metrics.recall_at(ranked, set(), 1)
    with pytest.raises(ValueError):
        metrics.recall_at(ranked, {"A"}, -1)
    with pytest.raises(ValueError):
        metrics.mrr_at(ranked, {"A"}, -1)


def test_p2_protocol_freezes_holdout_and_disables_wave_a_judges() -> None:
    protocol = _load("evaluation_protocol.yml")
    assert protocol["partitions"]["holdout"]["accessible_before_p7"] is False
    assert protocol["model_judges"]["enabled_for_wave_a"] is False
    assert protocol["mutation_policy"]["production_mutations_allowed"] is False


def test_wave_a_manifest_freezes_inputs_and_records_disposable_output() -> None:
    manifest = _load("manifests/wave_a.yml")
    assert manifest["partitions"]["holdout_accessed"] is False
    assert manifest["provider_model"]["provider_calls"] == 0
    assert manifest["raw_results"]["committed"] is False
    for fixture in manifest["fixtures"].values():
        assert fixture["sha256"]
        assert (REPO_ROOT / fixture["path"]).is_file()


@pytest.fixture(scope="module")
def result() -> dict:
    return wave_a.run_wave_a(SPIKES / "corpora" / "retrieval_units.yml")


def test_wave_a_never_measures_holdout(result: dict) -> None:
    assert all(run["holdout_measured"] is False for run in result["runs"])
    assert all(case["id"] != "RUQ05" for run in result["runs"] for case in run["cases"])


def test_wave_a_preserves_provenance_for_every_variant_and_mode(result: dict) -> None:
    assert all(
        case["provenance_resolution_rate"] == 1.0
        for run in result["runs"]
        for case in run["cases"]
    )


def test_wave_a_context_beats_heading_control_on_source_scoped_lexical(result: dict) -> None:
    runs = {(run["variant"], run["mode"]): run for run in result["runs"]}

    def source_scoped_recall(run: dict) -> float:
        cases = [case for case in run["cases"] if case["family"] == "source-scoped"]
        return sum(case["recall_at_1"] for case in cases) / len(cases)

    assert source_scoped_recall(runs["context", "lex"]) > source_scoped_recall(runs["heading", "lex"])


def test_wave_a_direct_factual_non_regression(result: dict) -> None:
    for run in result["runs"]:
        direct = [case for case in run["cases"] if case["family"] == "direct-factual"]
        assert direct and all(case["recall_at_1"] == 1.0 for case in direct)
