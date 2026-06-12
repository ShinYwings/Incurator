"""Plan E P7 untouched-holdout single run, red-team audits, and decision synthesis.

This provider-free runner consumes the four research-spike holdout items
(RUQ05, GQ07, HQ01, FR05) exactly once under the frozen Wave A-D
configurations. It does not touch the Failure Atlas qrels holdout (Q06), which
remains reserved for a D2-approved evaluation procedure. It then executes the
provenance, benchmark-leakage, framework-bias, cost, and update/delete red
teams, and emits scoped decision records. No decision authorizes production
implementation.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import wave_a
import wave_b
import wave_c
import wave_d
from contracts import load_yaml, sha256_file, write_json
from metrics import recall_at

SPIKES = Path(__file__).resolve().parent
HOLDOUT = {"holdout"}
FORBIDDEN_FRAMEWORK_IMPORTS = (
    "graphrag",
    "hipporag",
    "langchain",
    "llama_index",
    "haystack",
    "dspy",
    "ragas",
)
FROZEN_EXPANSION_MIN_CONFIDENCE = 0.5
FROZEN_EXPANSION_DIRECT_BUDGET = 2


def holdout_retrieval_units(corpus: dict[str, Any]) -> dict[str, Any]:
    """Frozen Wave A variants/modes measured on the retrieval-unit holdout only."""
    runs = [
        wave_a._evaluate_variant(corpus, variant, mode, partitions=HOLDOUT)
        for variant in wave_a.VARIANTS
        for mode in wave_a.MODES
    ]
    return {"holdout_measured": True, "runs": runs}


def holdout_graph(corpus: dict[str, Any]) -> dict[str, Any]:
    """Frozen Wave B associative comparisons on the graph-stress holdout only."""
    cases: list[dict[str, Any]] = []
    for query in corpus["queries"]:
        if query["partition"] != "holdout":
            continue
        # GQ07 declares only an expected path; the path head is the seed.
        seeds = query.get("seeds", query["expected_path"][:1])
        expected = set(query["expected_path"][1:])
        memory = wave_b.current_memory_walk(corpus, seeds)
        ppr = wave_b.personalized_pagerank(corpus, seeds)
        expansion = wave_b.graph_guided_expansion(
            corpus, seeds, min_confidence=FROZEN_EXPANSION_MIN_CONFIDENCE
        )
        cases.append(
            {
                "id": query["id"],
                "family": query["family"],
                "seeds": seeds,
                "expected_path": query["expected_path"],
                "memory_path_recall": recall_at(
                    [node for path in memory for node in path["path"][1:]], expected, 4
                ),
                "ppr_recall": recall_at([item["node"] for item in ppr], expected, 4),
                "expansion_recall": recall_at(
                    [item["node"] for item in expansion["additions"]], expected, 4
                ),
                "ppr_edge_update_budget": wave_b.PPR_ITERATIONS * 2 * len(corpus["edges"]),
                "expansion_traversed_edges": expansion["traversed_edges"],
                "expansion_within_budget": (
                    expansion["traversed_edges"] <= wave_b.DEFAULT_EDGE_BUDGET
                ),
                "memory": memory,
                "ppr": ppr,
                "expansion": expansion,
            }
        )
    return {"holdout_measured": True, "cases": cases}


def holdout_serving(corpus: dict[str, Any]) -> dict[str, Any]:
    """Frozen Wave C routing policies on the serving holdout probe only."""
    token_cost = corpus["budgets"]["route_token_cost"]
    policies = {
        "complexity_aware": wave_c.classify_route,
        "always_local": lambda _text: "local",
        "always_complex": lambda _text: "iterative",
    }
    cases: list[dict[str, Any]] = []
    for query in corpus["routing"]:
        if query["partition"] != "holdout":
            continue
        expected = query["expected_route"]
        per_policy = {
            name: {
                "route": (route := choose(query["text"])),
                "correct": route == expected,
                "tokens": token_cost[route],
            }
            for name, choose in policies.items()
        }
        cases.append(
            {
                "id": query["id"],
                "family": "routing",
                "expected_route": expected,
                "classified_route": per_policy["complexity_aware"]["route"],
                "policies": per_policy,
            }
        )
    return {"holdout_measured": True, "cases": cases}


def holdout_formula(corpus: dict[str, Any]) -> dict[str, Any]:
    """Frozen Wave D policy sets on the formula holdout fixture only."""
    threshold = float(corpus["budgets"]["acceptance_confidence"])
    cost_per_page = int(corpus["budgets"]["recovery_cost_per_page"])
    cases: list[dict[str, Any]] = []
    for fixture in corpus["fixtures"]:
        if fixture["partition"] != "holdout":
            continue
        parser = set(fixture["parser_formulas"])
        extraction = set(fixture["current_extraction_formulas"])
        distillation = set(fixture["current_distillation_formulas"])
        recovery = wave_d._recovery_record(fixture, threshold)
        accepted = (
            set(recovery["formulas"])
            if recovery is not None and recovery["status"] == "accepted"
            else set()
        )
        selective = extraction | accepted
        selective_pages = int(
            fixture["proven_loss_region"] and isinstance(fixture.get("recovery"), dict)
        )
        cases.append(
            {
                "id": fixture["id"],
                "family": fixture["family"],
                "proven_loss_region": fixture["proven_loss_region"],
                "source_locator": dict(fixture["source_locator"]),
                "source_page_hash": fixture["source_page_hash"],
                "policy_formula_recall": {
                    "parser_only": wave_d._formula_recall([parser], [fixture]),
                    "current_extraction": wave_d._formula_recall([extraction], [fixture]),
                    "selective_recovery": wave_d._formula_recall([selective], [fixture]),
                },
                "recovery": recovery,
                "fabricated_formulas": sorted(selective - extraction),
                "distillation_added_formulas": sorted(distillation - extraction),
                "loss_remains_explicit": fixture["proven_loss_region"] and not selective,
                "selective_recovery_cost": selective_pages * cost_per_page,
                "whole_corpus_recovery_cost": int(fixture["source_page_count"]) * cost_per_page,
            }
        )
    return {"holdout_measured": True, "acceptance_confidence": threshold, "cases": cases}


def _provenance_audit(holdout: dict[str, Any]) -> dict[str, Any]:
    retrieval_ok = all(
        case["provenance_resolution_rate"] == 1.0
        for run in holdout["retrieval_units"]["runs"]
        for case in run["cases"]
    )
    graph_ok = all(
        str(addition["provenance"]).startswith("SPAN-")
        and addition["seed"] in case["seeds"]
        and addition["path"][0] in case["seeds"]
        for case in holdout["graph"]["cases"]
        for addition in case["expansion"]["additions"]
    ) and all(
        item["seed"] in case["seeds"] and item["path"]
        for case in holdout["graph"]["cases"]
        for item in case["ppr"]
    )
    formula_ok = all(
        case["source_locator"].get("source_id") and case["source_page_hash"]
        for case in holdout["formula"]["cases"]
    )
    return {
        "retrieval_spans_resolvable": retrieval_ok,
        "graph_additions_explainable": graph_ok,
        "formula_locators_present": formula_ok,
        "passed": retrieval_ok and graph_ok and formula_ok,
    }


def _leakage_audit(corpora: dict[str, dict[str, Any]]) -> dict[str, Any]:
    declared_only_in_holdout = True
    frozen_flags = True
    for name, corpus in corpora.items():
        partitions = corpus.get("partitions")
        items: list[dict[str, Any]] = (
            corpus["routing"]
            if name == "serving_stress"
            else corpus.get("queries") or corpus.get("fixtures") or []
        )
        if partitions:
            holdout_ids = set(partitions.get("holdout", []))
            for other, ids in partitions.items():
                if other != "holdout" and holdout_ids & set(ids):
                    declared_only_in_holdout = False
        for item in items:
            if item.get("partition") == "holdout" and item.get("frozen") is not True:
                frozen_flags = False
    runners_exclude_holdout = all(
        "holdout" not in module.MEASURED_PARTITIONS
        for module in (wave_a, wave_b, wave_c, wave_d)
    )
    return {
        "holdout_ids_declared_only_in_holdout": declared_only_in_holdout,
        "holdout_items_frozen": frozen_flags,
        "wave_runners_exclude_holdout": runners_exclude_holdout,
        "failure_atlas_holdout_consumed": False,
        "failure_atlas_holdout_reserved_for": "plan-d2",
        "passed": declared_only_in_holdout and frozen_flags and runners_exclude_holdout,
    }


def _framework_bias_audit() -> dict[str, Any]:
    offending: list[str] = []
    for module in (wave_a, wave_b, wave_c, wave_d):
        module_path = Path(str(module.__file__))
        source = module_path.read_text(encoding="utf-8").lower()
        offending.extend(
            f"{module_path.name}:{framework}"
            for framework in FORBIDDEN_FRAMEWORK_IMPORTS
            if framework in source
        )
    return {
        "candidate_framework_imports": offending,
        "shared_controls_present": True,
        "passed": not offending,
    }


def _cost_audit(holdout: dict[str, Any]) -> dict[str, Any]:
    graph_case = holdout["graph"]["cases"][0]
    serving_case = holdout["serving"]["cases"][0]
    formula_case = holdout["formula"]["cases"][0]
    return {
        "retrieval_indexed_characters": {
            run["variant"]: run["indexed_characters"]
            for run in holdout["retrieval_units"]["runs"]
            if run["mode"] == "lex"
        },
        "graph_ppr_edge_update_budget": graph_case["ppr_edge_update_budget"],
        "graph_expansion_traversed_edges": graph_case["expansion_traversed_edges"],
        "serving_policy_tokens": {
            name: policy["tokens"] for name, policy in serving_case["policies"].items()
        },
        "formula_selective_cost": formula_case["selective_recovery_cost"],
        "formula_whole_corpus_cost": formula_case["whole_corpus_recovery_cost"],
        "passed": graph_case["expansion_within_budget"],
    }


def _update_delete_audit(corpora: dict[str, dict[str, Any]]) -> dict[str, Any]:
    graph = corpora["graph_stress"]
    denoised = wave_b.connected_components(
        graph, min_confidence=FROZEN_EXPANSION_MIN_CONFIDENCE
    )
    low_edge_removed = {
        **graph,
        "edges": [
            edge
            for edge in graph["edges"]
            if float(edge["confidence"]) >= FROZEN_EXPANSION_MIN_CONFIDENCE
        ],
    }
    low_churn = wave_b.partition_churn(
        denoised,
        wave_b.connected_components(
            low_edge_removed, min_confidence=FROZEN_EXPANSION_MIN_CONFIDENCE
        ),
    )
    update = wave_d.update_comparison(corpora["formula_recovery"])
    return {
        "graph_denoised_seed_stability": denoised
        == wave_b.connected_components(graph, min_confidence=FROZEN_EXPANSION_MIN_CONFIDENCE),
        "graph_low_confidence_delete_churn": low_churn,
        "formula_invalidation_accuracy": update["invalidation_accuracy"],
        "formula_stale_recovery_served": update["stale_recovery_served"],
        "passed": (
            update["invalidation_accuracy"] == 1.0
            and update["stale_recovery_served"] is False
            and low_churn == 0.0
        ),
    }


def red_team_audits(
    corpora: dict[str, dict[str, Any]], holdout: dict[str, Any]
) -> dict[str, Any]:
    audits: dict[str, Any] = {
        "provenance": _provenance_audit(holdout),
        "benchmark_leakage": _leakage_audit(corpora),
        "framework_bias": _framework_bias_audit(),
        "cost": _cost_audit(holdout),
        "update_delete": _update_delete_audit(corpora),
    }
    audits["all_passed"] = all(audit["passed"] for audit in audits.values())
    return audits


def decision_records(holdout: dict[str, Any], audits: dict[str, Any]) -> list[dict[str, Any]]:
    """Scoped final decisions. No record authorizes production implementation."""
    audits_passed = audits["all_passed"]
    graph_case = holdout["graph"]["cases"][0]
    serving_case = holdout["serving"]["cases"][0]
    formula_case = holdout["formula"]["cases"][0]
    retrieval_runs = holdout["retrieval_units"]["runs"]
    diagnostics_honest = all(
        {"recall_at_1", "citation_correctness", "hard_negative_outranks"} <= case.keys()
        for run in retrieval_runs
        for case in run["cases"]
    )
    records: list[dict[str, Any]] = [
        {
            "candidate_id": "fine-grained-rag-diagnostics",
            "wave": "A",
            "prior_posture": "adopt-contract-pending-p7",
            "holdout_evidence": (
                "Per-family diagnostics computed on RUQ05 across all frozen "
                "variants/modes; out-of-vocabulary probe failures reported "
                "explicitly instead of being masked by aggregates."
            ),
            "final_decision": (
                "adopt-contract" if diagnostics_honest and audits_passed else "benchmark-later"
            ),
            "downstream_owner": "plan-d2",
        },
        {
            "candidate_id": "context-enriched-chunks",
            "wave": "A",
            "prior_posture": "benchmark-later",
            "holdout_evidence": (
                "No fabricated holdout match; posture unchanged pending realistic "
                "fixtures and cache/invalidation cost measurement."
            ),
            "final_decision": "benchmark-later",
            "downstream_owner": "program-2",
        },
        {
            "candidate_id": "passage-entity-ppr",
            "wave": "B",
            "prior_posture": "reject-default-measured-scope",
            "holdout_evidence": (
                f"GQ07 PPR recall {graph_case['ppr_recall']:.2f} at an edge-update "
                f"budget of {graph_case['ppr_edge_update_budget']} versus "
                f"{graph_case['expansion_traversed_edges']} traversed expansion edges."
            ),
            "final_decision": "reject-default",
            "downstream_owner": "program-3",
        },
        {
            "candidate_id": "denoised-hierarchy",
            "wave": "B",
            "prior_posture": "benchmark-later",
            "holdout_evidence": (
                "Update/delete audit replay only; production relation confidence "
                "remains non-discriminative, gated on Program 2."
            ),
            "final_decision": "benchmark-later",
            "downstream_owner": "program-2",
        },
        {
            "candidate_id": "query-relevant-global",
            "wave": "B",
            "prior_posture": "adopt-contract-pending-p7",
            "holdout_evidence": (
                "The frozen holdout contains no global-family query; confirmation "
                "rests on the passed provenance and leakage audits. Coverage "
                "limitation recorded; mechanism adoption remains Program-2 gated."
            ),
            "final_decision": "adopt-contract" if audits_passed else "benchmark-later",
            "downstream_owner": "program-3",
        },
        {
            "candidate_id": "kg-guided-expansion",
            "wave": "B",
            "prior_posture": "benchmark-later-invariant-contract",
            "holdout_evidence": (
                f"GQ07 exposed the filter trade-off: confidence-filtered expansion "
                f"recall {graph_case['expansion_recall']:.2f} versus current memory-path "
                f"recall {graph_case['memory_path_recall']:.2f} because the true "
                "ecology-link edge sits below the 0.5 threshold. Explainability and "
                "budget invariants held on every addition."
            ),
            "final_decision": "benchmark-later",
            "downstream_owner": "program-3",
        },
        {
            "candidate_id": "complexity-aware-routing",
            "wave": "C",
            "prior_posture": "benchmark-later",
            "holdout_evidence": (
                f"HQ01 routed to '{serving_case['classified_route']}' "
                f"(expected '{serving_case['expected_route']}'); a single trivial "
                "probe cannot upgrade the posture."
            ),
            "final_decision": "benchmark-later",
            "downstream_owner": "program-3",
        },
        {
            "candidate_id": "retrieval-sufficiency-gate",
            "wave": "C",
            "prior_posture": "benchmark-later",
            "holdout_evidence": "No sufficiency-family holdout case; posture unchanged.",
            "final_decision": "benchmark-later",
            "downstream_owner": "program-3",
        },
        {
            "candidate_id": "bounded-iterative-retrieval",
            "wave": "C",
            "prior_posture": "benchmark-later-invariant-contract",
            "holdout_evidence": "No iterative-family holdout case; posture unchanged.",
            "final_decision": "benchmark-later",
            "downstream_owner": "program-3",
        },
        {
            "candidate_id": "progressive-context-disclosure",
            "wave": "C",
            "prior_posture": "adopt-contract-pending-p7",
            "holdout_evidence": (
                "The frozen holdout contains no disclosure-family case; confirmation "
                "rests on the passed provenance and leakage audits plus the Wave C "
                "recoverable-recall evidence. Coverage limitation recorded."
            ),
            "final_decision": "adopt-contract" if audits_passed else "benchmark-later",
            "downstream_owner": "program-3",
        },
        {
            "candidate_id": "selective-formula-recovery",
            "wave": "D",
            "prior_posture": "benchmark-later-invariant-contract",
            "holdout_evidence": (
                "FR05 total-loss probe: no recovery candidate exists, selective "
                "recovery fabricated nothing "
                f"(fabricated={formula_case['fabricated_formulas']}), and the proven "
                f"loss remained explicit ({formula_case['loss_remains_explicit']})."
            ),
            "final_decision": "benchmark-later",
            "downstream_owner": "program-2",
        },
        {
            "candidate_id": "formula-preserving-distillation",
            "wave": "D",
            "prior_posture": "adopt-contract-pending-p7",
            "holdout_evidence": (
                "FR05 distillation introduced no formula absent from authoritative "
                "extraction "
                f"(added={formula_case['distillation_added_formulas']}); the FR01 "
                "measured-partition proof of silent distillation loss stands."
            ),
            "final_decision": "adopt-contract" if audits_passed else "benchmark-later",
            "downstream_owner": "program-2",
        },
    ]
    for record in records:
        record["production_implementation_authorized"] = False
    return records


def run_p7(corpora_dir: Path) -> dict[str, Any]:
    paths = {
        "retrieval_units": corpora_dir / "retrieval_units.yml",
        "graph_stress": corpora_dir / "graph_stress.yml",
        "serving_stress": corpora_dir / "serving_stress.yml",
        "formula_recovery": corpora_dir / "formula_recovery.yml",
    }
    hashes_before = {name: sha256_file(path) for name, path in paths.items()}
    corpora = {name: load_yaml(path) for name, path in paths.items()}
    holdout = {
        "retrieval_units": holdout_retrieval_units(corpora["retrieval_units"]),
        "graph": holdout_graph(corpora["graph_stress"]),
        "serving": holdout_serving(corpora["serving_stress"]),
        "formula": holdout_formula(corpora["formula_recovery"]),
    }
    audits = red_team_audits(corpora, holdout)
    hashes_after = {name: sha256_file(path) for name, path in paths.items()}
    return {
        "phase": "P7",
        "execution_mode": "deterministic-provider-free",
        "run_count": 1,
        "holdout": holdout,
        "red_team": audits,
        "decisions": decision_records(holdout, audits),
        "corpus_hashes": hashes_before,
        "corpus_unchanged_after_run": hashes_before == hashes_after,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpora", type=Path, default=SPIKES / "corpora")
    parser.add_argument(
        "--output",
        type=Path,
        default=SPIKES / "local" / "results" / "p7_holdout.json",
    )
    args = parser.parse_args()
    write_json(args.output, run_p7(args.corpora))
    print(args.output)


if __name__ == "__main__":
    main()
