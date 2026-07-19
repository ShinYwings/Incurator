"""Phase 3 (v0.3.1): compiled CurationPolicy and spec validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from curator import curate_yml as cy
from curator.curate_yml import (
    CurateBackprop,
    CurateGoal,
    CurateKnowledge,
    CurateReasoning,
    CurateSources,
    CurateSpec,
    CurateVerification,
)


def _spec(**kw) -> CurateSpec:
    base = dict(project="lab")
    base.update(kw)
    return CurateSpec(**base)


def test_compile_policy_basic() -> None:
    spec = _spec(
        sources=CurateSources(include=["03_Notes/**"], exclude=["03_Notes/private/**"]),
        reasoning=CurateReasoning(default_mode="explore", allowed_modes=["local", "explore"]),
        verification=CurateVerification(require_source_spans=True, min_confidence=0.7),
        knowledge=CurateKnowledge(avoid_merges=["A != B"]),
        backprop=CurateBackprop(enabled=False),
    )
    policy = cy.compile_curate_policy(spec, Path("/v/01_Workspaces/MyLab"))
    assert policy.workspace_id == "MyLab"
    assert policy.project == "lab"
    assert policy.source_include == ("03_Notes/**",)
    assert policy.source_exclude == ("03_Notes/private/**",)
    assert policy.allowed_routes == frozenset({"local", "explore"})
    assert policy.default_route == "explore"
    assert policy.require_source_spans is True
    assert policy.backprop_enabled is False
    assert policy.avoid_merges == ("A != B",)
    assert policy.min_confidence == 0.7


def test_default_route_auto_when_default_not_allowed() -> None:
    spec = _spec(reasoning=CurateReasoning(default_mode="global", allowed_modes=["local"]))
    policy = cy.compile_curate_policy(spec)
    # 'global' not in allowed -> falls back to auto
    assert policy.default_route == "auto"
    assert policy.allowed_routes == frozenset({"local"})


def test_empty_allowed_modes_defaults_to_all_routes() -> None:
    spec = _spec(reasoning=CurateReasoning(default_mode="auto", allowed_modes=["bogus"]))
    policy = cy.compile_curate_policy(spec)
    assert policy.allowed_routes == cy.VALID_ROUTES


def test_workspace_id_from_project_when_no_path() -> None:
    spec = _spec(project="My Cool Project")
    policy = cy.compile_curate_policy(spec)
    assert policy.workspace_id == "my-cool-project"


def test_validate_clean_spec() -> None:
    spec = _spec(
        goal=CurateGoal(audience="researcher"),
        reasoning=CurateReasoning(default_mode="local", allowed_modes=["local", "global"]),
    )
    assert cy.validate_curate_spec(spec) == []


def test_validate_flags_bad_audience() -> None:
    spec = _spec(goal=CurateGoal(audience="wizard"))
    errs = cy.validate_curate_spec(spec)
    assert any("audience" in e for e in errs)


def test_validate_flags_unknown_route_and_default_mismatch() -> None:
    spec = _spec(reasoning=CurateReasoning(default_mode="global", allowed_modes=["local"]))
    errs = cy.validate_curate_spec(spec)
    assert any("not in allowed_modes" in e for e in errs)


def test_validate_flags_bad_confidence() -> None:
    spec = _spec(verification=CurateVerification(min_confidence=1.5))
    errs = cy.validate_curate_spec(spec)
    assert any("min_confidence" in e for e in errs)


def test_validate_flags_bad_contradiction_policy() -> None:
    spec = _spec(verification=CurateVerification(contradiction_policy="ignore-it"))
    errs = cy.validate_curate_spec(spec)
    assert any("contradiction_policy" in e for e in errs)


def test_resolve_policy_keeps_missing_workspace_default(tmp_path: Path) -> None:
    policy, spec_hash = cy.resolve_curate_policy(tmp_path)

    assert policy.project == "default"
    assert spec_hash == ""


def test_resolve_policy_rejects_semantically_invalid_existing_spec(
    tmp_path: Path,
) -> None:
    (tmp_path / "curate.yml").write_text(
        'project: "bad"\nreasoning:\n  allowed_modes: [bogus]\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="allowed_modes"):
        cy.resolve_curate_policy(tmp_path)


def test_resolve_policy_propagates_hash_read_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "curate.yml").write_text('project: "valid"\n', encoding="utf-8")

    def fail_hash(_workspace: Path) -> str:
        raise OSError("hash read denied")

    monkeypatch.setattr(cy, "curate_spec_hash", fail_hash)

    with pytest.raises(OSError, match="hash read denied"):
        cy.resolve_curate_policy(tmp_path)


def test_resolve_policy_rejects_spec_disappearing_before_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "curate.yml").write_text('project: "valid"\n', encoding="utf-8")
    monkeypatch.setattr(cy, "curate_spec_hash", lambda _workspace: "")

    with pytest.raises(ValueError, match="disappeared"):
        cy.resolve_curate_policy(tmp_path)
