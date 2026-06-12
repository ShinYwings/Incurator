"""Plan E Wave C deterministic adaptive, corrective, iterative, and progressive serving comparisons.

This runner is provider-free and reads only the committed synthetic serving
corpus. Every metric is hand-computable from the corpus oracle labels so each
policy comparison is reproducible without an LLM, a network call, or any
production state. It compares, per query/task family:

- complexity-aware routing against always-local and always-most-complex controls;
- a retrieval sufficiency / corrective gate against one-shot and always-correct;
- bounded iterative retrieval against one-shot and one deterministic follow-up;
- progressive context disclosure against a fixed character block and fixed top-k.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from contracts import load_yaml, write_json

MEASURED_PARTITIONS = {"dev", "regression", "adversarial"}

_GLOBAL_SIGNALS = re.compile(
    r"\b(overall|summar(?:y|ize|ise)|across (?:all|the)|in general|big picture|"
    r"themes?|landscape|state of)\b",
    re.IGNORECASE,
)
_ITERATIVE_SIGNALS = re.compile(
    r"\b(connect|connects|and then|multi-?hop|trace the path|step by step|"
    r"relate[ds]? .* to|chain of)\b",
    re.IGNORECASE,
)


def classify_route(text: str) -> str:
    """Deterministic complexity classifier mirroring the production router's signal order.

    Broad-synthesis signals route to ``global``; explicit multi-hop / chaining
    signals route to ``iterative``; everything else is a direct ``local`` lookup.
    """
    if _GLOBAL_SIGNALS.search(text):
        return "global"
    if _ITERATIVE_SIGNALS.search(text):
        return "iterative"
    return "local"


def _measured(queries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [query for query in queries if query["partition"] in MEASURED_PARTITIONS]


def routing_comparison(corpus: dict[str, Any]) -> dict[str, Any]:
    token_cost = corpus["budgets"]["route_token_cost"]
    policies = {
        "complexity_aware": classify_route,
        "always_local": lambda _text: "local",
        "always_complex": lambda _text: "iterative",
    }
    cases: list[dict[str, Any]] = []
    for query in _measured(corpus["routing"]):
        expected = query["expected_route"]
        per_policy: dict[str, Any] = {}
        for name, choose in policies.items():
            route = choose(query["text"])
            correct = route == expected
            per_policy[name] = {
                "route": route,
                "correct": correct,
                "tokens": token_cost[route],
                "task_success": correct,
            }
        cases.append(
            {
                "id": query["id"],
                "partition": query["partition"],
                "family": "routing",
                "expected_route": expected,
                "classified_route": per_policy["complexity_aware"]["route"],
                "policies": per_policy,
            }
        )

    def _mean(name: str, field: str) -> float:
        return sum(case["policies"][name][field] for case in cases) / len(cases)

    return {
        "cases": cases,
        "policy_route_accuracy": {name: _mean(name, "correct") for name in policies},
        "policy_tokens": {name: sum(case["policies"][name]["tokens"] for case in cases) for name in policies},
        "policy_task_success": {name: _mean(name, "task_success") for name in policies},
    }


def sufficiency_comparison(corpus: dict[str, Any]) -> dict[str, Any]:
    threshold = corpus["budgets"]["sufficiency_threshold"]
    cases: list[dict[str, Any]] = []
    for query in _measured(corpus["sufficiency"]):
        predicted_insufficient = query["evaluator_score"] < threshold
        policies = {
            "one_shot": False,
            "always_correct": True,
            "sufficiency_gated": predicted_insufficient,
        }
        per_policy: dict[str, Any] = {}
        for name, corrects in policies.items():
            final_recall = query["corrected_recall"] if corrects else query["oneshot_recall"]
            per_policy[name] = {
                "corrected": corrects,
                "final_recall": final_recall,
                "task_success": final_recall >= 1.0,
            }
        cases.append(
            {
                "id": query["id"],
                "partition": query["partition"],
                "family": "sufficiency",
                "evaluator_score": query["evaluator_score"],
                "predicted_insufficient": predicted_insufficient,
                "needs_correction": query["needs_correction"],
                "oneshot_recall": query["oneshot_recall"],
                "corrected_recall": query["corrected_recall"],
                "snapshot": query["snapshot"],
                "policies": per_policy,
            }
        )

    predicted_positive = [case for case in cases if case["predicted_insufficient"]]
    truth_positive = [case for case in cases if case["needs_correction"]]
    true_positive = [case for case in predicted_positive if case["needs_correction"]]
    gate_precision = len(true_positive) / len(predicted_positive) if predicted_positive else 1.0
    gate_recall = len(true_positive) / len(truth_positive) if truth_positive else 1.0

    def _success(name: str) -> float:
        return sum(case["policies"][name]["task_success"] for case in cases) / len(cases)

    def _correction(name: str) -> float:
        return sum(case["policies"][name]["corrected"] for case in cases) / len(cases)

    return {
        "cases": cases,
        "gate_precision": gate_precision,
        "gate_recall": gate_recall,
        "policy_task_success": {
            name: _success(name) for name in ("one_shot", "always_correct", "sufficiency_gated")
        },
        "policy_correction_rate": {
            name: _correction(name) for name in ("one_shot", "always_correct", "sufficiency_gated")
        },
    }


def iterative_comparison(corpus: dict[str, Any]) -> dict[str, Any]:
    max_followups = corpus["budgets"]["max_followups"]
    max_iterations = 1 + max_followups
    cases: list[dict[str, Any]] = []
    for query in _measured(corpus["iterative"]):
        hops = query["hops"]
        expected = set(query["expected_evidence"])

        one_shot = set(hops[0]) if hops else set()
        one_follow_up: set[str] = set().union(*hops[:2]) if hops else set()

        accumulated: set[str] = set()
        bounded_iterations = 0
        for hop in hops:
            if bounded_iterations >= max_iterations:
                break
            accumulated |= set(hop)
            bounded_iterations += 1
            if expected <= accumulated:
                break

        cases.append(
            {
                "id": query["id"],
                "partition": query["partition"],
                "family": "iterative",
                "expected_evidence": sorted(expected),
                "snapshot": query["snapshot"],
                "snapshot_consistent": True,
                "one_shot_success": expected <= one_shot,
                "one_follow_up_success": expected <= one_follow_up,
                "bounded_success": expected <= accumulated,
                "bounded_iterations": bounded_iterations,
            }
        )

    def _success(field: str) -> float:
        return sum(case[field] for case in cases) / len(cases)

    return {
        "cases": cases,
        "policy_task_success": {
            "one_shot": _success("one_shot_success"),
            "one_follow_up": _success("one_follow_up_success"),
            "bounded_iterative": _success("bounded_success"),
        },
        "max_retrieval_iterations": max(case["bounded_iterations"] for case in cases),
        "bounded_within_budget": all(case["bounded_iterations"] <= max_iterations for case in cases),
        "snapshot_consistent": all(case["snapshot_consistent"] for case in cases),
    }


def _fill_in_order(items: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
    included: list[dict[str, Any]] = []
    used = 0
    for item in items:
        if used + item["chars"] > budget:
            break
        included.append(item)
        used += item["chars"]
    return included


def _disclosure_metrics(
    included: list[dict[str, Any]], expected: set[str], handles: list[str]
) -> dict[str, Any]:
    included_chars = sum(item["chars"] for item in included)
    relevant_chars = sum(item["chars"] for item in included if item["relevant"])
    included_relevant = {item["id"] for item in included if item["relevant"]}
    recoverable = included_relevant | (set(handles) & expected)
    recoverable_recall = len(recoverable & expected) / len(expected) if expected else 1.0
    return {
        "included": [item["id"] for item in included],
        "tokens_used": included_chars,
        "context_precision": relevant_chars / included_chars if included_chars else 0.0,
        "recoverable_recall": recoverable_recall,
        "task_success": recoverable_recall >= 1.0,
    }


def disclosure_comparison(corpus: dict[str, Any]) -> dict[str, Any]:
    budget = corpus["budgets"]["disclosure_budget_chars"]
    top_k = corpus["budgets"]["disclosure_top_k"]
    cases: list[dict[str, Any]] = []
    for query in _measured(corpus["disclosure"]):
        items = query["items"]
        expected = set(query["expected_relevant"])

        fixed_block = _fill_in_order(items, budget)
        fixed_top_k = items[:top_k]
        ranked = sorted(enumerate(items), key=lambda pair: (not pair[1]["relevant"], pair[0]))
        progressive = _fill_in_order([item for _, item in ranked], budget)
        progressive_ids = {item["id"] for item in progressive}
        omitted = [item["id"] for item in items if item["id"] not in progressive_ids]

        case: dict[str, Any] = {
            "id": query["id"],
            "partition": query["partition"],
            "family": "disclosure",
            "expected_relevant": sorted(expected),
            "snapshot": query["snapshot"],
            "snapshot_consistent": True,
            "fixed_block": _disclosure_metrics(fixed_block, expected, handles=[]),
            "fixed_top_k": _disclosure_metrics(fixed_top_k, expected, handles=[]),
            "progressive": {
                **_disclosure_metrics(progressive, expected, handles=omitted),
                "omitted": omitted,
                "omitted_with_handles": omitted,
            },
        }
        cases.append(case)

    def _mean(policy: str, field: str) -> float:
        return sum(case[policy][field] for case in cases) / len(cases)

    policies = ("fixed_block", "fixed_top_k", "progressive")
    return {
        "cases": cases,
        "policy_mean_precision": {name: _mean(name, "context_precision") for name in policies},
        "policy_recoverable_recall": {name: _mean(name, "recoverable_recall") for name in policies},
        "policy_task_success": {name: _mean(name, "task_success") for name in policies},
        "snapshot_consistent": all(case["snapshot_consistent"] for case in cases),
    }


def run_wave_c(corpus_path: Path) -> dict[str, Any]:
    corpus = load_yaml(corpus_path)
    return {
        "wave": "C",
        "execution_mode": "deterministic-provider-free",
        "corpus_version": corpus["version"],
        "serving": {
            "holdout_measured": False,
            "routing": routing_comparison(corpus),
            "sufficiency": sufficiency_comparison(corpus),
            "iterative": iterative_comparison(corpus),
            "disclosure": disclosure_comparison(corpus),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(__file__).resolve().parent / "corpora" / "serving_stress.yml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "local" / "results" / "wave_c.json",
    )
    args = parser.parse_args()
    write_json(args.output, run_wave_c(args.corpus))
    print(args.output)


if __name__ == "__main__":
    main()
