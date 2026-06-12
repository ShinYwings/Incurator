"""Plan E Wave D conditional formula-recovery contracts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPIKES = REPO_ROOT / "backend" / "research_spikes"
sys.path.insert(0, str(SPIKES))

import contracts  # noqa: E402
import wave_d  # noqa: E402

CORPUS = SPIKES / "corpora" / "formula_recovery.yml"


@pytest.fixture(scope="module")
def corpus() -> dict:
    return wave_d.load_yaml(CORPUS)


@pytest.fixture(scope="module")
def result() -> dict:
    return wave_d.run_wave_d(CORPUS)


def test_wave_d_keeps_holdout_inaccessible(result: dict) -> None:
    formula = result["formula_recovery"]
    assert formula["holdout_measured"] is False
    assert all(case["id"] != "FR05" for case in formula["cases"])


def test_wave_d_proves_parser_and_distillation_loss_boundaries(result: dict) -> None:
    boundaries = result["formula_recovery"]["loss_boundaries"]
    fr01 = next(case for case in boundaries if case["id"] == "FR01")
    assert fr01["parser_loss"] == ["h_{k+1} = h_k + F_k(h_k)"]
    assert fr01["raw_fallback_recovery"] == ["h_{k+1} = h_k + F_k(h_k)"]
    assert fr01["current_extraction_loss"] == []
    assert fr01["distillation_loss"] == ["h_{k+1} = h_k + F_k(h_k)"]

    fr02 = next(case for case in boundaries if case["id"] == "FR02")
    assert len(fr02["parser_loss"]) == 2
    assert len(fr02["current_extraction_loss"]) == 2
    assert fr02["distillation_loss"] == []


def test_selective_recovery_improves_recall_without_hallucinated_replacement(result: dict) -> None:
    metrics = result["formula_recovery"]["policy_metrics"]
    assert metrics["selective_recovery"]["formula_recall"] > metrics["current_extraction"]["formula_recall"]
    assert metrics["current_extraction"]["formula_recall"] > metrics["parser_only"]["formula_recall"]
    assert metrics["selective_recovery"]["hallucinated_replacement_rate"] == 0.0
    assert metrics["selective_recovery"]["raw_evidence_preservation"] == 1.0
    assert metrics["selective_recovery"]["recovery_candidate_error_rate"] > 0.0
    assert metrics["selective_recovery"]["accepted_recovery_error_rate"] == 0.0


def test_low_confidence_recovery_is_explicitly_uncertain(result: dict) -> None:
    cases = result["formula_recovery"]["cases"]
    ambiguous = next(case for case in cases if case["id"] == "FR03")
    recovery = ambiguous["selective_recovery"]["recovery"]
    assert recovery["status"] == "uncertain"
    assert recovery["confidence"] < result["formula_recovery"]["acceptance_confidence"]
    assert recovery["source_locator"]["region"] == "eq-2"
    assert recovery["source_page_hash"] == "PAGE-FR03-V1"
    assert ambiguous["selective_recovery"]["observed_formulas"] == []


def test_selective_recovery_is_separately_costed_from_whole_corpus(result: dict) -> None:
    cost = result["formula_recovery"]["cost"]
    assert cost["selective_pages"] == 2
    assert cost["whole_corpus_pages"] == 14
    assert cost["selective_cost"] < cost["whole_corpus_cost"]


def test_recovered_content_invalidates_on_source_page_change_only(result: dict) -> None:
    update = result["formula_recovery"]["update_behavior"]
    assert update["invalidation_accuracy"] == 1.0
    changed = next(case for case in update["cases"] if case["id"] == "FU01")
    unchanged = next(case for case in update["cases"] if case["id"] == "FU02")
    assert changed["invalidated"] is True
    assert changed["stale_recovery_served"] is False
    assert changed["selective_reprocessed_pages"] == 1
    assert unchanged["invalidated"] is False
    assert unchanged["selective_reprocessed_pages"] == 0
    assert update["selective_reprocessed_pages"] < update["whole_corpus_reprocessed_pages"]


def test_wave_d_is_repeatable(result: dict) -> None:
    assert result["formula_recovery"] == wave_d.run_wave_d(CORPUS)["formula_recovery"]


def test_wave_d_manifest_freezes_inputs_and_disposable_output() -> None:
    manifest = contracts.load_yaml(SPIKES / "manifests" / "wave_d.yml")
    assert manifest["partitions"]["holdout_accessed"] is False
    assert manifest["provider_model"]["provider_calls"] == 0
    assert manifest["raw_results"]["committed"] is False
    for name in ("formula_recovery", "evaluation_protocol"):
        fixture = manifest["fixtures"][name]
        assert contracts.sha256_file(REPO_ROOT / fixture["path"]) == fixture["sha256"]
