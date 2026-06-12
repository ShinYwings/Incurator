"""Plan E Wave D deterministic conditional formula-recovery comparison.

This provider-free runner reads only the committed synthetic formula corpus. It
separates parser, current extraction, and distillation loss; compares parser-only
and current extraction controls with confidence-gated selective recovery; and
measures provenance safety, cost, and page-hash update invalidation.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from contracts import load_yaml, write_json

MEASURED_PARTITIONS = {"dev", "regression", "adversarial"}


def _measured(fixtures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [fixture for fixture in fixtures if fixture["partition"] in MEASURED_PARTITIONS]


def _ordered_missing(expected: list[str], observed: list[str]) -> list[str]:
    observed_set = set(observed)
    return [formula for formula in expected if formula not in observed_set]


def loss_boundaries(fixtures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    boundaries: list[dict[str, Any]] = []
    for fixture in _measured(fixtures):
        expected = fixture["expected_formulas"]
        parser = fixture["parser_formulas"]
        raw_text = fixture["raw_text_formulas"]
        extraction = fixture["current_extraction_formulas"]
        distillation = fixture["current_distillation_formulas"]
        parser_set = set(parser)
        raw_text_set = set(raw_text)
        extraction_set = set(extraction)
        distillation_set = set(distillation)
        boundaries.append(
            {
                "id": fixture["id"],
                "partition": fixture["partition"],
                "family": fixture["family"],
                "parser_loss": _ordered_missing(expected, parser),
                "raw_fallback_recovery": [
                    formula
                    for formula in expected
                    if formula not in parser_set
                    and formula in raw_text_set
                    and formula in extraction_set
                ],
                "current_extraction_loss": _ordered_missing(expected, extraction),
                "distillation_loss": [
                    formula
                    for formula in expected
                    if formula in extraction_set and formula not in distillation_set
                ],
            }
        )
    return boundaries


def _recovery_record(
    fixture: dict[str, Any], acceptance_confidence: float
) -> dict[str, Any] | None:
    candidate = fixture.get("recovery")
    if not fixture["proven_loss_region"] or not isinstance(candidate, dict):
        return None
    confidence = float(candidate["confidence"])
    return {
        "formulas": list(candidate["formulas"]),
        "confidence": confidence,
        "status": "accepted" if confidence >= acceptance_confidence else "uncertain",
        "source_locator": dict(fixture["source_locator"]),
        "source_page_hash": fixture["source_page_hash"],
        "overwrites_raw": bool(candidate["overwrites_raw"]),
    }


def _formula_recall(observed_by_case: list[set[str]], fixtures: list[dict[str, Any]]) -> float:
    expected_count = sum(len(fixture["expected_formulas"]) for fixture in fixtures)
    if not expected_count:
        return 1.0
    matched = sum(
        len(observed & set(fixture["expected_formulas"]))
        for observed, fixture in zip(observed_by_case, fixtures)
    )
    return matched / expected_count


def policy_comparison(corpus: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    fixtures = _measured(corpus["fixtures"])
    threshold = float(corpus["budgets"]["acceptance_confidence"])
    cases: list[dict[str, Any]] = []
    parser_observed: list[set[str]] = []
    extraction_observed: list[set[str]] = []
    selective_observed: list[set[str]] = []
    recovered_formula_count = 0
    recovery_candidate_errors = 0
    accepted_formula_count = 0
    accepted_recovery_errors = 0
    hallucinated_replacements = 0
    raw_preserved = True

    for fixture in fixtures:
        expected = set(fixture["expected_formulas"])
        parser = set(fixture["parser_formulas"])
        extraction = set(fixture["current_extraction_formulas"])
        recovery = _recovery_record(fixture, threshold)
        accepted_recovery: set[str] = set()
        if recovery is not None:
            recovered = set(recovery["formulas"])
            recovered_formula_count += len(recovered)
            candidate_errors = len(recovered - expected)
            recovery_candidate_errors += candidate_errors
            if recovery["status"] == "accepted":
                accepted_recovery = recovered
                accepted_formula_count += len(recovered)
                accepted_recovery_errors += candidate_errors
            if recovery["overwrites_raw"]:
                hallucinated_replacements += candidate_errors
                raw_preserved = False

        selective = extraction | accepted_recovery
        parser_observed.append(parser)
        extraction_observed.append(extraction)
        selective_observed.append(selective)
        cases.append(
            {
                "id": fixture["id"],
                "partition": fixture["partition"],
                "family": fixture["family"],
                "expected_formulas": fixture["expected_formulas"],
                "parser_only": {"observed_formulas": sorted(parser)},
                "current_extraction": {"observed_formulas": sorted(extraction)},
                "selective_recovery": {
                    "observed_formulas": sorted(selective),
                    "recovery": recovery,
                },
            }
        )

    def _rate(numerator: int, denominator: int) -> float:
        return numerator / denominator if denominator else 0.0

    policy_metrics = {
        "parser_only": {
            "formula_recall": _formula_recall(parser_observed, fixtures),
        },
        "current_extraction": {
            "formula_recall": _formula_recall(extraction_observed, fixtures),
        },
        "selective_recovery": {
            "formula_recall": _formula_recall(selective_observed, fixtures),
            "recovery_candidate_error_rate": _rate(
                recovery_candidate_errors, recovered_formula_count
            ),
            "accepted_recovery_error_rate": _rate(
                accepted_recovery_errors, accepted_formula_count
            ),
            "hallucinated_replacement_rate": _rate(
                hallucinated_replacements, recovered_formula_count
            ),
            "raw_evidence_preservation": 1.0 if raw_preserved else 0.0,
        },
    }
    return cases, policy_metrics


def cost_comparison(corpus: dict[str, Any]) -> dict[str, Any]:
    fixtures = _measured(corpus["fixtures"])
    cost_per_page = int(corpus["budgets"]["recovery_cost_per_page"])
    selective_pages = sum(
        1
        for fixture in fixtures
        if fixture["proven_loss_region"] and isinstance(fixture.get("recovery"), dict)
    )
    whole_corpus_pages = sum(int(fixture["source_page_count"]) for fixture in fixtures)
    return {
        "cost_per_page": cost_per_page,
        "selective_pages": selective_pages,
        "whole_corpus_pages": whole_corpus_pages,
        "selective_cost": selective_pages * cost_per_page,
        "whole_corpus_cost": whole_corpus_pages * cost_per_page,
    }


def update_comparison(corpus: dict[str, Any]) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for update in corpus["updates"]:
        invalidated = update["stored_page_hash"] != update["updated_page_hash"]
        served_page_hash = (
            update["updated_page_hash"] if invalidated else update["stored_page_hash"]
        )
        cases.append(
            {
                "id": update["id"],
                "source_id": update["source_id"],
                "invalidated": invalidated,
                "expected_invalidate": update["expected_invalidate"],
                "served_page_hash": served_page_hash,
                "stale_recovery_served": served_page_hash != update["updated_page_hash"],
                "selective_reprocessed_pages": 1 if invalidated else 0,
                "whole_corpus_reprocessed_pages": int(update["source_page_count"]),
            }
        )
    correct = sum(case["invalidated"] == case["expected_invalidate"] for case in cases)
    return {
        "cases": cases,
        "invalidation_accuracy": correct / len(cases) if cases else 1.0,
        "stale_recovery_served": any(case["stale_recovery_served"] for case in cases),
        "selective_reprocessed_pages": sum(case["selective_reprocessed_pages"] for case in cases),
        "whole_corpus_reprocessed_pages": sum(
            case["whole_corpus_reprocessed_pages"] for case in cases
        ),
    }


def run_wave_d(corpus_path: Path) -> dict[str, Any]:
    corpus = load_yaml(corpus_path)
    cases, policy_metrics = policy_comparison(corpus)
    return {
        "wave": "D",
        "execution_mode": "deterministic-provider-free",
        "corpus_version": corpus["version"],
        "formula_recovery": {
            "holdout_measured": False,
            "acceptance_confidence": corpus["budgets"]["acceptance_confidence"],
            "loss_boundaries": loss_boundaries(corpus["fixtures"]),
            "cases": cases,
            "policy_metrics": policy_metrics,
            "cost": cost_comparison(corpus),
            "update_behavior": update_comparison(corpus),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(__file__).resolve().parent / "corpora" / "formula_recovery.yml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "local" / "results" / "wave_d.json",
    )
    args = parser.parse_args()
    write_json(args.output, run_wave_d(args.corpus))
    print(args.output)


if __name__ == "__main__":
    main()
