"""v0.3.1 insight lifecycle.

Turns a backprop classification into a safe action, enforcing source-truth
immutability:

- correction        → patch generated nodes only (never source)
- contradiction     → flag both sides, create needs_review candidate
- derived_insight   → create a provisional insight_candidate (never rewrite source)
- style_only        → no expensive rebuild
- promotion_request → write ONLY to 02_Wiki/ (explicit human approval)
- ambiguous         → needs_review

See ``docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`` §18–§19.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import config as cfg
from . import db
from .backprop_classifier import BackpropClassification

__all__ = ["ActionPlan", "plan_action", "create_insight_from_classification", "promote_insight"]

# Generated-node prefixes that backprop may patch. Source spans and the
# read-only source folders are never touched.
_PATCHABLE = ("ATM-", "CON-", "SYN-", "KNU-", "ENT-", "REL-", "REP-")
_READ_ONLY_DIRS = ("03_Notes/", "04_Resources/", "06_Archives/")


@dataclass
class ActionPlan:
    action: str  # patch_generated | flag_review | create_insight_candidate | promote | no_op
    classification: str
    patch_node_ids: list[str] = field(default_factory=list)
    creates_candidate: bool = False
    requires_human_review: bool = False
    writes_source_truth: bool = False  # MUST remain False (invariant)
    notes: str = ""


def plan_action(classification: BackpropClassification) -> ActionPlan:
    c = classification.classification
    patchable = [n for n in classification.affected_nodes if n.startswith(_PATCHABLE)]
    if c == "correction":
        return ActionPlan("patch_generated", c, patch_node_ids=patchable,
                          notes="patch generated nodes; preserve source text")
    if c == "contradiction":
        return ActionPlan("flag_review", c, creates_candidate=True,
                          requires_human_review=True,
                          notes="flag both sides; do not merge without review")
    if c == "derived_insight":
        return ActionPlan("create_insight_candidate", c, creates_candidate=True,
                          notes="record candidate; never rewrite source L1")
    if c == "style_only":
        return ActionPlan("no_op", c, notes="presentation only; no graph rebuild")
    if c == "promotion_request":
        return ActionPlan("promote", c, requires_human_review=True,
                          notes="promote to 02_Wiki only, on explicit approval")
    return ActionPlan("flag_review", c, requires_human_review=True, notes="ambiguous")


def create_insight_from_classification(
    db_path: Path,
    classification: BackpropClassification,
    *,
    statement: str,
    workspace_id: str = "",
    source_event_id: str = "",
    evidence: list | None = None,
) -> str:
    """Create a provisional insight candidate for a derived insight / contradiction.

    Never writes source truth; the candidate lives until explicitly promoted.
    """
    status = "needs_review" if classification.classification == "contradiction" else "pending"
    return db.create_insight_candidate(
        db_path,
        classification=classification.classification,
        statement=statement,
        workspace_id=workspace_id,
        source_event_id=source_event_id or classification.trace_id,
        evidence=evidence or [],
        affected_node_ids=classification.affected_nodes,
        confidence=classification.confidence,
        status=status,
        prompt_run_id=classification.trace_id,
    )


def _slugify(text: str) -> str:
    slug = re.sub(r"[^\w\- ]", "", text).strip().replace(" ", "-").lower()
    return (slug or "insight")[:60]


def promote_insight(
    paths: cfg.WikiPaths, insight_id: str, *, subdir: str = ""
) -> str:
    """Promote an insight candidate to a durable note under 02_Wiki/ ONLY.

    Returns the vault-relative path written. Sets the candidate status to
    'promoted'. Never writes to read-only source folders.
    """
    cand = db.get_insight_candidate(paths.state_db, insight_id)
    if cand is None:
        raise ValueError(f"unknown insight candidate: {insight_id}")

    wiki_root = paths.root / "02_Wiki"
    target_dir = wiki_root / subdir if subdir else wiki_root
    target_dir.mkdir(parents=True, exist_ok=True)
    rel = f"02_Wiki/{(subdir + '/') if subdir else ''}{_slugify(cand['statement'])}.md"
    out_path = paths.root / rel
    # Guard: promotion must never land in a read-only source space.
    if any(part in rel for part in _READ_ONLY_DIRS):
        raise ValueError("promotion target must be 02_Wiki, not a source folder")

    body = (
        f"---\n"
        f"type: promoted_insight\n"
        f"source_insight_id: {insight_id}\n"
        f"classification: {cand['classification']}\n"
        f"is_verified_by_human: true\n"
        f"---\n\n# {cand['statement']}\n"
    )
    out_path.write_text(body, encoding="utf-8")
    db.update_insight_candidate_status(paths.state_db, insight_id, status="promoted")
    return rel
