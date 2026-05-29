#!/usr/bin/env python3
"""Cross-model benchmark harness for InCurator.

Usage:
    python scripts/benchmark/benchmark.py run GS_Testbed --models gemini-flash qwen2.5:7b
    python scripts/benchmark/benchmark.py compare results/run_a.json results/run_b.json

Measures:
  - add + sync wall-clock time
  - atom/concept/exhibition counts and merge rate from atom coordinator
  - vault health score (lint)
  - verification gap count
  - LLM-as-judge quality on a fixed GS query set
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Allow running as a script from anywhere in the repo
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from curator import config as cfg
from curator import db
from curator import ingest_llm
from curator import lint as lint_module
from curator import query as query_module
from curator import search
from curator import sync
from curator import testbed_manager
from curator.llm import build_client


# ---------------------------------------------------------------------------
# Fixed GS query set
# ---------------------------------------------------------------------------

QUERY_SET = [
    "What is the mathematical foundation of 2D Gaussian Splatting?",
    "How does EWA Splatting handle screen-space filtering?",
    "What are the key differences between 2D and 3D Gaussian representations?",
    "Describe the rasterization pipeline for Gaussian primitives.",
]

JUDGE_PROMPT = """\
You are an expert evaluator. Score the following answer to a technical question.

Question: {question}
Answer: {answer}

Scoring criteria (each 0–5):
- relevance: How directly does the answer address the question?
- coverage: How thoroughly does it cover the key aspects?
- accuracy: Are the technical claims correct and precise?

Return ONLY valid JSON:
{{"relevance": <int>, "coverage": <int>, "accuracy": <int>}}
"""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class QueryScore:
    question: str
    answer_length: int
    relevance: int = 0
    coverage: int = 0
    accuracy: int = 0
    total: int = 0
    error: str = ""


@dataclass
class BenchmarkRun:
    model_key: str
    scenario: str
    timestamp: str
    add_time_sec: float
    sync_time_sec: float
    atom_count: int
    concept_count: int
    exhibition_count: int
    context_count: int
    merge_count: int
    health_score: int
    verification_gaps: int
    query_scores: list[QueryScore] = field(default_factory=list)

    @property
    def mean_quality(self) -> float:
        if not self.query_scores:
            return 0.0
        scores = [q.total for q in self.query_scores if not q.error]
        return round(sum(scores) / len(scores), 2) if scores else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["mean_quality"] = self.mean_quality
        return d


# ---------------------------------------------------------------------------
# Model key → config mapping
# ---------------------------------------------------------------------------

MODEL_CONFIGS: dict[str, dict] = {
    "gemini-flash": {
        "primary": "antigravity-cli",
        "antigravity_flash_model": "gemini-3.5-flash",
    },
    "gemini-pro": {
        "primary": "cloud",
        "cloud_provider": "gemini",
        "gemini_flash_model": "gemini-3.1-pro-preview",
    },
    "qwen2.5:7b": {
        "primary": "ollama",
        "model": "qwen2.5:7b",
        "host": "http://localhost:11434",
    },
    "claude-sonnet": {
        "primary": "claude-code",
        "claude_model": "claude-sonnet-4-6",
    },
}


def _resolve_model_config(model_key: str) -> dict:
    """Return an LLM config dict for the given model key.

    Accepts either a known shorthand from MODEL_CONFIGS or a raw provider
    string in the form 'provider:model' (e.g. 'ollama:llama3').
    """
    if model_key in MODEL_CONFIGS:
        return MODEL_CONFIGS[model_key]
    if ":" in model_key:
        provider, model = model_key.split(":", 1)
        return {"primary": provider, "model": model}
    return {"primary": model_key}


# ---------------------------------------------------------------------------
# Testbed helpers
# ---------------------------------------------------------------------------


def _init_testbed(scenario: str, model_key: str) -> tuple[cfg.WikiPaths, dict]:
    """Recreate the testbed, configure for model_key, return (paths, config)."""
    testbed_manager.init_testbed(scenario, force=True)
    repo_root = Path(__file__).resolve().parents[2]
    testbed_root = repo_root / "testbed"

    paths = cfg.WikiPaths(root=testbed_root)
    vault_config = cfg.load_config(paths)

    llm_overrides = _resolve_model_config(model_key)
    for k, v in llm_overrides.items():
        vault_config["llm"][k] = v

    cfg.save_config(paths, vault_config)
    print(f"  [init] testbed ready at {testbed_root}  model={model_key}")
    return paths, vault_config


def _build_client_for_config(vault_config: dict):
    """Build an LLM client from a vault config dict."""
    return build_client(vault_config)


# ---------------------------------------------------------------------------
# Metric collection
# ---------------------------------------------------------------------------


def _count_layer(paths: cfg.WikiPaths, layer_dir: Path) -> int:
    if not layer_dir.exists():
        return 0
    return sum(1 for _ in layer_dir.glob("*.md"))


def _collect_metrics(paths: cfg.WikiPaths, client) -> dict:
    atom_count = _count_layer(paths, paths.atoms)
    concept_count = _count_layer(paths, paths.concepts)
    exhibition_count = _count_layer(paths, paths.exhibitions)
    context_count = _count_layer(paths, paths.contexts)

    gaps: list[sync.VerificationGap] = []
    try:
        gaps = sync.run_mode_a(paths)
    except Exception as e:
        print(f"  [warn] sync mode_a failed: {e}")

    report = lint_module.run_lint(paths)
    health = report.health_score

    return {
        "atom_count": atom_count,
        "concept_count": concept_count,
        "exhibition_count": exhibition_count,
        "context_count": context_count,
        "verification_gaps": len(gaps),
        "health_score": health,
    }


def _read_merge_count_from_log(paths: cfg.WikiPaths) -> int:
    """Extract atom coordinator merge count from log.md."""
    log_path = paths.log
    if not log_path.exists():
        return 0
    text = log_path.read_text(encoding="utf-8")
    total = 0
    import re
    for m in re.finditer(r"merged\s+(\d+)\s+atom", text, re.IGNORECASE):
        total += int(m.group(1))
    return total


# ---------------------------------------------------------------------------
# LLM-as-judge scoring
# ---------------------------------------------------------------------------


def _score_answer(client, question: str, answer: str) -> QueryScore:
    score = QueryScore(question=question, answer_length=len(answer))
    if not answer:
        score.error = "empty answer"
        return score
    prompt = JUDGE_PROMPT.format(question=question, answer=answer)
    try:
        raw = client.chat([{"role": "user", "content": prompt}])
        import re
        m = re.search(r"\{[^}]+\}", raw, re.DOTALL)
        if not m:
            score.error = f"no json in: {raw[:100]}"
            return score
        data = json.loads(m.group())
        score.relevance = int(data.get("relevance", 0))
        score.coverage = int(data.get("coverage", 0))
        score.accuracy = int(data.get("accuracy", 0))
        score.total = score.relevance + score.coverage + score.accuracy
    except Exception as e:
        score.error = str(e)
    return score


def _run_query_set(paths: cfg.WikiPaths, client) -> list[QueryScore]:
    class _Silent(query_module.QueryCallbacks):
        pass

    scores: list[QueryScore] = []
    for question in QUERY_SET:
        answer = ""
        try:
            result = query_module.run_query(
                paths,
                client,
                question,
                _Silent(),
                mode="hybrid",
                classify_intent_first=False,
            )
            answer = result.answer or ""
        except Exception as e:
            print(f"  [warn] query failed: {e}")
        score = _score_answer(client, question, answer)
        scores.append(score)
        print(f"  [query] {question[:55]}... → total={score.total} err={score.error or '-'}")
    return scores


# ---------------------------------------------------------------------------
# Add pipeline
# ---------------------------------------------------------------------------


class _SilentIngestCallbacks(ingest_llm.IngestCallbacks):
    pass


def _run_add(paths: cfg.WikiPaths, client) -> float:
    """Run wiki add on all pending sources; return wall-clock seconds."""
    t0 = time.monotonic()
    ingest_llm.run_l1_to_l3(
        paths,
        client,
        lambda: _SilentIngestCallbacks(),
        mode="auto",
        auto_discover=True,
    )
    return time.monotonic() - t0


# ---------------------------------------------------------------------------
# Sync pipeline
# ---------------------------------------------------------------------------


def _run_sync(paths: cfg.WikiPaths, client) -> float:
    """Run mode C sync; return wall-clock seconds."""
    t0 = time.monotonic()
    try:
        sync.run_mode_c(paths, client, callbacks=None)
    except Exception as e:
        print(f"  [warn] sync mode_c failed: {e}")
    return time.monotonic() - t0


# ---------------------------------------------------------------------------
# Single benchmark run
# ---------------------------------------------------------------------------


def run_benchmark(scenario: str, model_key: str, results_dir: Path) -> BenchmarkRun:
    print(f"\n{'='*60}")
    print(f"  Benchmark: scenario={scenario}  model={model_key}")
    print(f"{'='*60}")

    paths, vault_config = _init_testbed(scenario, model_key)
    client = _build_client_for_config(vault_config)

    print("  [phase] add (L1→L3)...")
    add_time = _run_add(paths, client)
    print(f"  [phase] add done in {add_time:.1f}s")

    print("  [phase] sync (mode C)...")
    sync_time = _run_sync(paths, client)
    print(f"  [phase] sync done in {sync_time:.1f}s")

    print("  [phase] collecting metrics...")
    metrics = _collect_metrics(paths, client)
    merge_count = _read_merge_count_from_log(paths)

    print("  [phase] running query set...")
    query_scores = _run_query_set(paths, client)

    run = BenchmarkRun(
        model_key=model_key,
        scenario=scenario,
        timestamp=datetime.now(timezone.utc).isoformat(),
        add_time_sec=round(add_time, 2),
        sync_time_sec=round(sync_time, 2),
        merge_count=merge_count,
        query_scores=query_scores,
        **metrics,
    )

    results_dir.mkdir(parents=True, exist_ok=True)
    slug = model_key.replace(":", "_").replace("/", "_")
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = results_dir / f"{slug}_{ts}.json"
    out_path.write_text(json.dumps(run.to_dict(), indent=2), encoding="utf-8")
    print(f"  [saved] {out_path}")

    _print_run_summary(run)
    return run


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def compare_runs(paths_a: Path, paths_b: Path) -> None:
    data_a = json.loads(paths_a.read_text())
    data_b = json.loads(paths_b.read_text())

    label_a = f"{data_a['model_key']} ({paths_a.name})"
    label_b = f"{data_b['model_key']} ({paths_b.name})"

    print(f"\n{'='*60}")
    print(f"  Comparison: {label_a}  vs  {label_b}")
    print(f"{'='*60}")

    def _fmt(key: str, unit: str = "", higher_is_better: bool = True) -> None:
        va = data_a.get(key, "?")
        vb = data_b.get(key, "?")
        try:
            diff = float(vb) - float(va)
            if higher_is_better:
                winner = "B" if diff > 0 else ("A" if diff < 0 else "tie")
            else:
                winner = "A" if diff > 0 else ("B" if diff < 0 else "tie")
            arrow = f"+{diff:.2f}" if diff > 0 else f"{diff:.2f}"
        except (TypeError, ValueError):
            arrow = "?"
            winner = "?"
        print(f"  {key:<30} A={va}{unit}  B={vb}{unit}  Δ={arrow}{unit}  winner={winner}")

    print(f"\n  {'Metric':<30} {'A':>12}  {'B':>12}  {'Δ':>10}  winner")
    print(f"  {'-'*70}")
    _fmt("add_time_sec", "s", higher_is_better=False)
    _fmt("sync_time_sec", "s", higher_is_better=False)
    _fmt("atom_count", higher_is_better=True)
    _fmt("concept_count", higher_is_better=True)
    _fmt("exhibition_count", higher_is_better=True)
    _fmt("merge_count", higher_is_better=True)
    _fmt("health_score", higher_is_better=True)
    _fmt("verification_gaps", higher_is_better=False)
    _fmt("mean_quality", higher_is_better=True)

    print(f"\n  A = {label_a}")
    print(f"  B = {label_b}")


# ---------------------------------------------------------------------------
# Pretty print
# ---------------------------------------------------------------------------


def _print_run_summary(run: BenchmarkRun) -> None:
    print(f"\n  ┌─ Summary: {run.model_key} ──────────────────────────────")
    print(f"  │  add={run.add_time_sec}s  sync={run.sync_time_sec}s")
    print(f"  │  atoms={run.atom_count}  concepts={run.concept_count}  exhibitions={run.exhibition_count}")
    print(f"  │  merged={run.merge_count}  health={run.health_score}  gaps={run.verification_gaps}")
    print(f"  │  mean_quality={run.mean_quality}/15")
    print(f"  └────────────────────────────────────────────────────────")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_run(args) -> None:
    scenario = args.scenario
    models = args.models or ["gemini-flash"]
    results_dir = Path(args.output or "scripts/benchmark/results")
    runs: list[BenchmarkRun] = []
    for model_key in models:
        try:
            run = run_benchmark(scenario, model_key, results_dir)
            runs.append(run)
        except Exception as e:
            print(f"  [error] {model_key}: {e}")

    if len(runs) >= 2:
        # Auto-compare last two runs
        _print_comparison_table(runs)


def _print_comparison_table(runs: list[BenchmarkRun]) -> None:
    print(f"\n{'='*60}")
    print("  Cross-model comparison")
    print(f"{'='*60}")
    keys = ["add_time_sec", "sync_time_sec", "atom_count", "concept_count",
            "merge_count", "health_score", "verification_gaps", "mean_quality"]
    header = f"  {'Metric':<30}" + "".join(f"  {r.model_key[:12]:>12}" for r in runs)
    print(header)
    print(f"  {'-'*70}")
    for key in keys:
        row = f"  {key:<30}"
        for run in runs:
            val = getattr(run, key, run.to_dict().get(key, "?"))
            row += f"  {str(val):>12}"
        print(row)


def _cmd_compare(args) -> None:
    compare_runs(Path(args.file_a), Path(args.file_b))


def _build_arg_parser():
    import argparse
    parser = argparse.ArgumentParser(
        prog="benchmark",
        description="InCurator cross-model benchmark harness",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run a benchmark scenario")
    run_p.add_argument("scenario", help="Testbed scenario name (e.g. GS_Testbed)")
    run_p.add_argument("--models", nargs="+", default=["gemini-flash"],
                       help="Model keys to benchmark (space-separated)")
    run_p.add_argument("--output", default=None, help="Results directory")
    run_p.set_defaults(func=_cmd_run)

    cmp_p = sub.add_parser("compare", help="Compare two result JSON files")
    cmp_p.add_argument("file_a")
    cmp_p.add_argument("file_b")
    cmp_p.set_defaults(func=_cmd_compare)

    return parser


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
