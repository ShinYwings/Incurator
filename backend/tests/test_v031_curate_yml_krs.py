"""Phase 3 (v0.3.1): curate.yml Knowledge Requirement Specification parsing."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from curator import curate_yml as cy

FULL_YML = """\
project: "resnet-dynamics-lab"
description: "Workspace purpose."

goal:
  primary: "Explain residual networks through a dynamics lens."
  audience: "researcher"
  deliverables: ["curated-exhibition", "research-note-context"]
  success_criteria:
    - "Every mathematical claim cites a source span."

sources:
  include: ["03_Notes/**", "04_Resources/**"]
  exclude: ["03_Notes/private/**"]
  reference_mode:
    allow_external: true
    require_rebind_approval: false

knowledge:
  domains: ["machine-learning", "dynamical-systems"]
  topics: ["residual learning", "Euler discretization"]
  disambiguation_keywords: ["ResNet", "Neural ODE"]
  avoid_merges:
    - "original ResNet claim != later ODE interpretation"

output:
  format: "exhibition"
  style: "dense-technical"
  citation_style: "curator-source-spans"
  include_sections: ["Evidence Map", "Unresolved Gaps"]

reasoning:
  default_mode: "explore"
  allowed_modes: ["local", "global", "explore", "exhibition"]
  exploration_enabled: true
  max_followups: 7
  require_insight_candidates: true

verification:
  min_confidence: 0.70
  high_threshold: 0.90
  require_source_spans: true
  allow_general_knowledge: false
  contradiction_policy: "surface-and-flag"

backprop:
  enabled: true
  source_truth_policy: "never_rewrite_original_source"
  derived_insight_policy: "record_then_promote_or_patch_generated"
  ambiguous_merge_policy: "needs_review"

prompts:
  profile: "technical-research"
  output_language: "same_as_latest_request"
  prompt_overrides: {}
"""

MINIMAL_YML = 'project: "minimal-lab"\n'


def _write(tmp: Path, text: str) -> Path:
    ws = tmp / "ws"
    ws.mkdir()
    (ws / "curate.yml").write_text(text, encoding="utf-8")
    return ws


def test_parse_full_krs() -> None:
    with tempfile.TemporaryDirectory() as t:
        ws = _write(Path(t), FULL_YML)
        spec = cy.load_curate_spec(ws)
    assert spec is not None
    assert spec.goal.primary.startswith("Explain residual")
    assert spec.goal.audience == "researcher"
    assert spec.goal.deliverables == ["curated-exhibition", "research-note-context"]
    assert spec.knowledge.domains == ["machine-learning", "dynamical-systems"]
    assert "ResNet" in spec.knowledge.disambiguation_keywords
    assert spec.knowledge.avoid_merges
    assert spec.output.include_sections == ["Evidence Map", "Unresolved Gaps"]
    assert spec.reasoning.default_mode == "explore"
    assert spec.reasoning.max_followups == 7
    assert spec.reasoning.require_insight_candidates is True
    assert spec.verification.min_confidence == 0.70
    assert spec.verification.high_threshold == 0.90
    assert spec.backprop.source_truth_policy == "never_rewrite_original_source"
    assert spec.prompts.profile == "technical-research"
    assert spec.reference_mode.require_rebind_approval is False


def test_parse_minimal_uses_defaults() -> None:
    with tempfile.TemporaryDirectory() as t:
        ws = _write(Path(t), MINIMAL_YML)
        spec = cy.load_curate_spec(ws)
    assert spec is not None
    assert spec.project == "minimal-lab"
    assert spec.goal.audience == "generalist"
    assert spec.reasoning.default_mode == "auto"
    assert spec.reasoning.allowed_modes == ["local", "global", "explore"]
    assert spec.verification.require_source_spans is True
    assert spec.backprop.enabled is True
    assert spec.prompts.profile == "default"


def test_missing_curate_yml_returns_none() -> None:
    with tempfile.TemporaryDirectory() as t:
        ws = Path(t) / "empty"
        ws.mkdir()
        assert cy.load_curate_spec(ws) is None


def test_curate_spec_hash_stable_and_sensitive() -> None:
    with tempfile.TemporaryDirectory() as t:
        ws = _write(Path(t), FULL_YML)
        h1 = cy.curate_spec_hash(ws)
        h2 = cy.curate_spec_hash(ws)
        assert h1 == h2 and h1
        (ws / "curate.yml").write_text(FULL_YML + "\n# edit\n", encoding="utf-8")
        assert cy.curate_spec_hash(ws) != h1


def test_invalid_yaml_raises() -> None:
    with tempfile.TemporaryDirectory() as t:
        ws = _write(Path(t), "project: [unclosed\n")
        with pytest.raises(ValueError):
            cy.load_curate_spec(ws)
