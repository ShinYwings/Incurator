"""Plan E Wave B deterministic graph, hierarchy, and global comparisons."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import deque
from pathlib import Path
from typing import Any

from contracts import load_yaml, sqlite_readonly_summary, write_json
from metrics import hard_negative_outranks, recall_at

MEASURED_PARTITIONS = {"dev", "regression", "adversarial"}
DEFAULT_EDGE_BUDGET = 8
PPR_ITERATIONS = 30


def _adjacency(corpus: dict[str, Any], *, min_confidence: float = 0.0) -> dict[str, list[dict[str, Any]]]:
    adjacency: dict[str, list[dict[str, Any]]] = {node["id"]: [] for node in corpus["nodes"]}
    for edge in corpus["edges"]:
        if float(edge["confidence"]) < min_confidence:
            continue
        adjacency[edge["source"]].append({**edge, "to": edge["target"]})
        adjacency[edge["target"]].append({**edge, "to": edge["source"]})
    for edges in adjacency.values():
        edges.sort(key=lambda edge: (-float(edge["confidence"]), edge["to"], edge["kind"]))
    return adjacency


def connected_components(corpus: dict[str, Any], *, min_confidence: float = 0.0) -> list[list[str]]:
    adjacency = _adjacency(corpus, min_confidence=min_confidence)
    components: list[list[str]] = []
    # Mirror the current production detector: isolated entities do not produce
    # global community reports.
    unseen = {node for node, edges in adjacency.items() if edges}
    while unseen:
        start = min(unseen)
        queue = [start]
        component: list[str] = []
        unseen.remove(start)
        while queue:
            current = queue.pop(0)
            component.append(current)
            for edge in adjacency[current]:
                if edge["to"] in unseen:
                    unseen.remove(edge["to"])
                    queue.append(edge["to"])
        components.append(sorted(component))
    return sorted(components, key=lambda component: (-len(component), component))


def giant_component_ratio(components: list[list[str]]) -> float:
    total = sum(len(component) for component in components)
    return 0.0 if not total else max(len(component) for component in components) / total


def partition_churn(before: list[list[str]], after: list[list[str]]) -> float:
    def memberships(components: list[list[str]]) -> dict[str, frozenset[str]]:
        return {node: frozenset(component) for component in components for node in component}

    before_map, after_map = memberships(before), memberships(after)
    nodes = set(before_map) | set(after_map)
    return sum(before_map.get(node) != after_map.get(node) for node in nodes) / len(nodes)


def current_memory_walk(
    corpus: dict[str, Any], seeds: list[str], *, max_depth: int = 2, max_paths: int = 4
) -> list[dict[str, Any]]:
    """Mirror the current depth-limited confidence/path-length control."""
    adjacency = _adjacency(corpus)
    paths: list[dict[str, Any]] = []

    def walk(current: str, depth: int, visited: set[str], path: list[str], edges: list[dict]) -> None:
        if depth == 0 or len(paths) >= max_paths:
            return
        for edge in adjacency[current]:
            if len(paths) >= max_paths:
                return
            if edge["to"] in visited:
                continue
            next_path = [*path, edge["to"]]
            next_edges = [*edges, edge]
            avg_confidence = sum(float(item["confidence"]) for item in next_edges) / len(next_edges)
            score = (0.35 + 0.25 * avg_confidence + 0.20) / len(next_edges)
            paths.append(
                {
                    "seed": path[0],
                    "path": next_path,
                    "edges": [item["kind"] for item in next_edges],
                    "score": score,
                }
            )
            walk(edge["to"], depth - 1, visited | {edge["to"]}, next_path, next_edges)

    for seed in seeds:
        walk(seed, max_depth, {seed}, [seed], [])
    return sorted(paths, key=lambda item: (-item["score"], item["path"]))[:max_paths]


def personalized_pagerank(
    corpus: dict[str, Any],
    seeds: list[str],
    *,
    min_confidence: float = 0.0,
    damping: float = 0.85,
    iterations: int = PPR_ITERATIONS,
    limit: int = 4,
) -> list[dict[str, Any]]:
    adjacency = _adjacency(corpus, min_confidence=min_confidence)
    nodes = sorted(adjacency)
    restart = {node: (1.0 / len(seeds) if node in seeds else 0.0) for node in nodes}
    ranks = dict(restart)
    for _ in range(iterations):
        next_ranks = {node: (1.0 - damping) * restart[node] for node in nodes}
        for node in nodes:
            total_weight = sum(float(edge["confidence"]) for edge in adjacency[node])
            if not total_weight:
                next_ranks[node] += damping * ranks[node]
                continue
            for edge in adjacency[node]:
                next_ranks[edge["to"]] += (
                    damping * ranks[node] * float(edge["confidence"]) / total_weight
                )
        ranks = next_ranks
    ranked = [node for node in sorted(nodes, key=lambda node: (-ranks[node], node)) if node not in seeds]
    return [
        {
            "node": node,
            "score": ranks[node],
            "seed": explanation["seed"],
            "path": explanation["path"],
            "edges": explanation["edges"],
        }
        for node in ranked[:limit]
        if (explanation := shortest_explanation(adjacency, seeds, node)) is not None
    ]


def shortest_explanation(
    adjacency: dict[str, list[dict[str, Any]]], seeds: list[str], target: str
) -> dict[str, Any] | None:
    queue: deque[tuple[str, list[str], list[dict[str, Any]]]] = deque(
        (seed, [seed], []) for seed in sorted(seeds)
    )
    visited = set(seeds)
    while queue:
        current, path, edges = queue.popleft()
        if current == target:
            return {"seed": path[0], "path": path, "edges": edges}
        for edge in adjacency[current]:
            if edge["to"] not in visited:
                visited.add(edge["to"])
                queue.append((edge["to"], [*path, edge["to"]], [*edges, edge["kind"]]))
    return None


def graph_guided_expansion(
    corpus: dict[str, Any],
    seeds: list[str],
    *,
    min_confidence: float,
    max_edges: int = DEFAULT_EDGE_BUDGET,
) -> dict[str, Any]:
    adjacency = _adjacency(corpus, min_confidence=min_confidence)
    queue: deque[tuple[str, list[str], list[dict[str, Any]]]] = deque(
        (seed, [seed], []) for seed in sorted(seeds)
    )
    visited = set(seeds)
    additions: list[dict[str, Any]] = []
    traversed = 0
    while queue and traversed < max_edges:
        current, path, edge_path = queue.popleft()
        for edge in adjacency[current]:
            if traversed >= max_edges:
                break
            traversed += 1
            if edge["to"] in visited:
                continue
            visited.add(edge["to"])
            next_path = [*path, edge["to"]]
            next_edges = [*edge_path, edge["kind"]]
            additions.append(
                {
                    "node": edge["to"],
                    "seed": path[0],
                    "path": next_path,
                    "edges": next_edges,
                    "provenance": next(
                        node["provenance"] for node in corpus["nodes"] if node["id"] == edge["to"]
                    ),
                }
            )
            queue.append((edge["to"], next_path, next_edges))
    return {"seeds": seeds, "additions": additions, "traversed_edges": traversed}


def select_communities(
    corpus: dict[str, Any], components: list[list[str]], query: str, *, limit: int
) -> list[dict[str, Any]]:
    nodes = {node["id"]: node for node in corpus["nodes"]}
    query_terms = set(query.lower().replace("-", " ").split())
    rows: list[dict[str, Any]] = []
    for component in components:
        text = " ".join(nodes[node]["label"] for node in component).lower()
        terms = set(text.replace("-", " ").split())
        rows.append(
            {
                "nodes": component,
                "communities": sorted({nodes[node]["community"] for node in component}),
                "score": len(query_terms & terms),
                "source_spans": sorted({nodes[node]["provenance"] for node in component}),
            }
        )
    return sorted(rows, key=lambda row: (-float(row["score"]), row["nodes"]))[:limit]


def _query_results(corpus: dict[str, Any]) -> dict[str, Any]:
    nodes = {node["id"]: node for node in corpus["nodes"]}
    raw_components = connected_components(corpus)
    denoised_components = connected_components(corpus, min_confidence=0.5)
    cases: list[dict[str, Any]] = []
    for query in corpus["queries"]:
        if query["partition"] not in MEASURED_PARTITIONS:
            continue
        case: dict[str, Any] = {
            "id": query["id"],
            "partition": query["partition"],
            "family": query["family"],
        }
        if query["family"] == "associative":
            expected = set(query["expected_path"][1:])
            memory = current_memory_walk(corpus, query["seeds"])
            ppr = personalized_pagerank(corpus, query["seeds"])
            expansion = graph_guided_expansion(corpus, query["seeds"], min_confidence=0.5)
            case.update(
                {
                    "memory_path_recall": recall_at(
                        [node for path in memory for node in path["path"][1:]], expected, 4
                    ),
                    "ppr_recall": recall_at([item["node"] for item in ppr], expected, 4),
                    "expansion_recall": recall_at(
                        [item["node"] for item in expansion["additions"]], expected, 4
                    ),
                    "ppr_forbidden_rate": (
                        len(set(query.get("forbidden", [])) & {item["node"] for item in ppr})
                        / max(len(ppr), 1)
                    ),
                    "ppr_edge_update_budget": PPR_ITERATIONS * 2 * len(corpus["edges"]),
                    "expansion_forbidden_rate": (
                        len(
                            set(query.get("forbidden", []))
                            & {item["node"] for item in expansion["additions"]}
                        )
                        / max(len(expansion["additions"]), 1)
                    ),
                    "ppr": ppr,
                    "expansion": expansion,
                }
            )
        elif query["family"] == "global":
            all_selection = select_communities(corpus, raw_components, query["text"], limit=len(raw_components))
            relevant = select_communities(corpus, denoised_components, query["text"], limit=1)
            expected = set(query["expected_communities"])
            case.update(
                {
                    "all_report_precision": (
                        sum(bool(expected & set(row["communities"])) for row in all_selection)
                        / len(all_selection)
                    ),
                    "query_relevant_precision": (
                        sum(bool(expected & set(row["communities"])) for row in relevant)
                        / len(relevant)
                    ),
                    "all_report_count": len(all_selection),
                    "query_relevant_count": len(relevant),
                    "selected": relevant,
                }
            )
        else:
            expected = set(query["expected"])
            hard_negatives = set(query["hard_negatives"])
            lexical_ranked = sorted(
                nodes,
                key=lambda node: (
                    -len(set(query["text"].lower().split()) & set(nodes[node]["label"].lower().split())),
                    node,
                ),
            )
            expansion = graph_guided_expansion(
                corpus, [lexical_ranked[0]], min_confidence=0.5, max_edges=2
            )
            graph_ranked = [lexical_ranked[0], *[item["node"] for item in expansion["additions"]]]
            case.update(
                {
                    "lexical_direct_factual_recall_at_2": recall_at(lexical_ranked, expected, 2),
                    "graph_direct_factual_recall_at_2": recall_at(graph_ranked, expected, 2),
                    "hard_negative_outranks": hard_negative_outranks(
                        graph_ranked, expected, hard_negatives
                    ),
                    "direct_expansion": expansion,
                }
            )
        cases.append(case)

    low_edge_removed = {
        **corpus,
        "edges": [edge for edge in corpus["edges"] if float(edge["confidence"]) >= 0.5],
    }
    high_edge_removed = {
        **corpus,
        "edges": [
            edge
            for edge in corpus["edges"]
            if not (edge["source"] == "N01" and edge["target"] == "N02")
        ],
    }
    return {
        "raw_giant_component_ratio": giant_component_ratio(raw_components),
        "denoised_giant_component_ratio": giant_component_ratio(denoised_components),
        "denoised_seed_stability": denoised_components == connected_components(corpus, min_confidence=0.5),
        "low_confidence_delete_churn": partition_churn(
            denoised_components, connected_components(low_edge_removed, min_confidence=0.5)
        ),
        "high_confidence_delete_churn": partition_churn(
            denoised_components, connected_components(high_edge_removed, min_confidence=0.5)
        ),
        "holdout_measured": False,
        "cases": cases,
    }


def production_scale_summary(db_path: Path) -> dict[str, Any]:
    started = time.monotonic()
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        nodes = [
            {
                "id": row["id"],
                "community": "unknown",
                "label": f'{row["canonical_name"]} {row["description"]}',
                "provenance": (json.loads(row["source_span_ids"]) or [""])[0],
            }
            for row in conn.execute(
                "SELECT id, canonical_name, description, source_span_ids FROM graph_entities"
            )
        ]
        edges = [
            {
                "source": row["source_entity_id"],
                "target": row["target_entity_id"],
                "kind": row["relation_type"],
                "confidence": row["confidence"],
            }
            for row in conn.execute(
                "SELECT source_entity_id, target_entity_id, relation_type, confidence "
                "FROM graph_relations"
            )
        ]
        confidence_rows = [
            float(row[0])
            for row in conn.execute("SELECT confidence FROM graph_relations").fetchall()
        ]
    corpus = {"nodes": nodes, "edges": edges}
    raw = connected_components(corpus)
    denoised = connected_components(corpus, min_confidence=0.5)
    return {
        "snapshot": sqlite_readonly_summary(db_path),
        "raw_components": len(raw),
        "denoised_components": len(denoised),
        "raw_giant_component_ratio": giant_component_ratio(raw),
        "denoised_giant_component_ratio": giant_component_ratio(denoised),
        "relation_confidence": {
            "minimum": min(confidence_rows) if confidence_rows else None,
            "maximum": max(confidence_rows) if confidence_rows else None,
            "mean": (
                sum(confidence_rows) / len(confidence_rows) if confidence_rows else None
            ),
            "below_0_5": sum(value < 0.5 for value in confidence_rows),
            "at_or_above_0_5": sum(value >= 0.5 for value in confidence_rows),
        },
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


def run_wave_b(corpus_path: Path, production_copy: Path | None = None) -> dict[str, Any]:
    corpus = load_yaml(corpus_path)
    result = {
        "wave": "B",
        "execution_mode": "deterministic-provider-free",
        "corpus_version": corpus["version"],
        "stress": _query_results(corpus),
    }
    if production_copy and production_copy.is_file():
        result["production_scale"] = production_scale_summary(production_copy)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path(__file__).resolve().parent / "corpora" / "graph_stress.yml",
    )
    parser.add_argument(
        "--production-copy",
        type=Path,
        default=Path(__file__).resolve().parent / "local" / "snapshots" / "prod-second-brain.sqlite",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "local" / "results" / "wave_b.json",
    )
    args = parser.parse_args()
    write_json(args.output, run_wave_b(args.corpus, args.production_copy))
    print(args.output)


if __name__ == "__main__":
    main()
