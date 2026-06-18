from __future__ import annotations

import time
from typing import Any, Optional

from . import config as cfg
from . import ingest_llm
from . import prompts
from .llm import LLMError

# ---------------------------------------------------------------------------
# Time & Performance Evaluation Sub-agent
# ---------------------------------------------------------------------------
class TimePerformanceEvaluator:
    """Monitors performance and cross-checks logic during Generative Backprop."""
    def __init__(self):
        self.metrics = []

    def start_timer(self, label: str) -> float:
        return time.time()

    def record_time(self, label: str, start_time: float):
        elapsed = time.time() - start_time
        self.metrics.append({"label": label, "elapsed_sec": elapsed})

    def evaluate_atom_quality(self, atom_id: str, insight: str) -> bool:
        """Critic agent evaluates if the atom correctly addresses the insight without hallucination."""
        # For simulation: we assume valid. A true critic could invoke an LLM.
        return True

    def report(self, console: Any):
        console.print("[dim]=== Generative Backprop Performance Report ===[/dim]")
        for m in self.metrics:
            console.print(f"[dim]- {m['label']}: {m['elapsed_sec']:.2f}s[/dim]")
        console.print("[dim]==============================================[/dim]")


# ---------------------------------------------------------------------------
# Incurator System Sub-agents
# ---------------------------------------------------------------------------
class InsightExtractor:
    """Extracts specific external facts from a logically flagged node."""
    @staticmethod
    def extract(client, node_body: str, gap_reasoning: str) -> Optional[str]:
        messages = prompts.build_backprop_insight_extraction_messages(node_body, gap_reasoning)
        try:
            raw = client.chat(messages, json_mode=False, temperature=0.1)
            # The LLM returns a cohesive string of facts.
            return raw.strip()
        except LLMError:
            return None

class AtomSynthesizer:
    """Synthesizes new L2 Atoms from extracted insights."""
    @staticmethod
    def synthesize(paths: cfg.WikiPaths, client, insight: str, node_id: str) -> Optional[str]:
        today = ingest_llm._now_iso()
        return ingest_llm.add_atom_from_insight(
            paths, client, insight, today, source_hint=node_id
        )

class ConceptClusteringAgent:
    """Re-clusters existing and new Atoms into L3 Concepts."""
    @staticmethod
    def recluster(paths: cfg.WikiPaths, client, atom_ids: list[str]) -> None:
        ingest_llm.run_l3_from_existing_atoms(
            paths, client, lambda: ingest_llm.IngestCallbacks()
        )


# ---------------------------------------------------------------------------
# Workspace Sub-agent
# ---------------------------------------------------------------------------
class WorkspaceController:
    """Manages DAG updates securely without breaking Incurator constraints."""
    @staticmethod
    def commit_and_update_routing(paths: cfg.WikiPaths, new_atom_id: str):
        # The L2 atom file is already written by AtomSynthesizer.
        # This agent is responsible for any schema normalization if needed.
        pass
