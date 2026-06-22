"""Tests for testbed scenario discovery and initialization (testbed_manager.py).

These lock the post-cleanup contract: scenarios live ONLY under tests/scenarios/,
the CLI/manager is the single creation entry point (no standalone
create_testbed.py), and a scenario is identified by its MASTER_PLAN.md.
"""
from __future__ import annotations

from pathlib import Path

from curator import testbed_manager as tm


def test_scenarios_dir_points_at_tests_scenarios() -> None:
    scenarios = tm.get_scenarios_dir()
    assert scenarios.name == "scenarios"
    assert scenarios.parent.name == "tests"


def test_list_scenarios_requires_master_plan(tmp_path: Path, monkeypatch) -> None:
    fake = tmp_path / "scenarios"
    (fake / "good").mkdir(parents=True)
    (fake / "good" / "MASTER_PLAN.md").write_text("# Good\n", encoding="utf-8")
    (fake / "no_plan").mkdir()
    (fake / "no_plan" / "stage").mkdir()
    monkeypatch.setattr(tm, "get_scenarios_dir", lambda: fake)

    found = tm.list_scenarios()
    assert "good" in found
    assert "no_plan" not in found


def test_init_testbed_seeds_from_stage_and_marks_testbed(tmp_path: Path, monkeypatch) -> None:
    # Build a minimal scenario under a fake scenarios dir whose parents[1] is a
    # temp repo root, so init_testbed writes testbed/ there (not the real repo).
    repo = tmp_path / "repo"
    scenarios = repo / "tests" / "scenarios"
    scenario = scenarios / "demo"
    (scenario / "stage" / "03_Notes").mkdir(parents=True)
    (scenario / "MASTER_PLAN.md").write_text("# Demo\n", encoding="utf-8")
    (scenario / "stage" / "03_Notes" / "note.md").write_text("hello\n", encoding="utf-8")
    monkeypatch.setattr(tm, "get_scenarios_dir", lambda: scenarios)

    root = tm.init_testbed("demo", force=True)

    assert root == repo / "testbed"
    assert (root / "03_Notes" / "note.md").read_text(encoding="utf-8") == "hello\n"
    assert (root / ".curator" / "settings.yml").exists()
    # Testbed must be flagged so production code never auto-selects it.
    import yaml
    cfg_data = yaml.safe_load((root / ".curator" / "settings.yml").read_text(encoding="utf-8"))
    assert cfg_data.get("testbed") is True


def test_init_testbed_unknown_scenario_raises(tmp_path: Path, monkeypatch) -> None:
    scenarios = tmp_path / "repo" / "tests" / "scenarios"
    scenarios.mkdir(parents=True)
    monkeypatch.setattr(tm, "get_scenarios_dir", lambda: scenarios)
    try:
        tm.init_testbed("does_not_exist", force=True)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "does_not_exist" in str(exc)
