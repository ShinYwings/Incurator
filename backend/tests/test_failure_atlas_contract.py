"""Failure Atlas contract tests (Program 1 / Plan D1).

Enforces docs/specs/failure_atlas/FAILURE_ATLAS.md §2–§3 on the machine-readable
case records in docs/specs/failure_atlas/cases/: schema completeness, status
lifecycle transitions, snapshot identities, oracle presence, per-family
reporting, and fixture resolvability. These are the "schema/contract tests for
atlas records and evidence bundles" required by Plan D phase P1 — they reject
missing snapshot identities, missing oracles, aggregate-only reports, and
unsupported status transitions.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ATLAS_DIR = REPO_ROOT / "docs" / "specs" / "failure_atlas"
CASES_DIR = ATLAS_DIR / "cases"

EXPECTED_IDS = [f"F{i}" for i in range(1, 14)]
STATUSES = {"suspected", "reproduced", "disproven", "accepted", "assigned"}
QUERY_FAMILIES = {
    "direct-factual", "associative", "global", "source-scoped",
    "cross-route", "compiler", "client-parity", "evaluation-infra",
}
EXECUTION_MODES = {"deterministic", "provider", "degraded", "human-review"}
OWNERS = {"plan-d2", "program-2", "program-3", "plan-e", "unassigned"}
ALLOWED_TRANSITIONS = {
    ("suspected", "reproduced"),
    ("suspected", "disproven"),
    ("reproduced", "assigned"),
    ("reproduced", "accepted"),
}
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _load_cases() -> dict[str, dict]:
    cases: dict[str, dict] = {}
    for path in sorted(CASES_DIR.glob("F*.yml")):
        record = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(record, dict), f"{path.name} did not parse to a mapping"
        cases[record.get("id", path.stem)] = record
    return cases


CASES = _load_cases()


def test_atlas_has_exactly_f1_to_f13() -> None:
    assert sorted(CASES, key=lambda s: int(s[1:])) == EXPECTED_IDS


@pytest.mark.parametrize("case_id", EXPECTED_IDS)
def test_required_fields_present_and_typed(case_id: str) -> None:
    record = CASES[case_id]
    for field in (
        "id", "title", "query_family", "execution_mode", "status",
        "status_history", "owner", "impact", "boundary", "oracles",
        "observed_result", "snapshot",
    ):
        assert field in record, f"{case_id}: missing required field {field!r}"
    assert record["query_family"] in QUERY_FAMILIES, (
        f"{case_id}: per-family reporting is mandatory; "
        f"{record['query_family']!r} is not a declared family"
    )
    assert record["execution_mode"] in EXECUTION_MODES
    assert record["status"] in STATUSES
    assert record["owner"] in OWNERS
    boundary = record["boundary"]
    assert boundary.get("module") and boundary.get("symbol"), (
        f"{case_id}: boundary must name the exact module and symbol"
    )


@pytest.mark.parametrize("case_id", EXPECTED_IDS)
def test_status_lifecycle_transitions_valid(case_id: str) -> None:
    record = CASES[case_id]
    history = record["status_history"]
    assert history, f"{case_id}: empty status_history"
    for entry in history:
        assert entry.get("date") and entry.get("status") and entry.get("evidence"), (
            f"{case_id}: each history entry needs date/status/evidence"
        )
        assert entry["status"] in STATUSES
    assert history[0]["status"] == "suspected", (
        f"{case_id}: lifecycle must start at 'suspected'"
    )
    for prev, cur in zip(history, history[1:]):
        transition = (prev["status"], cur["status"])
        assert transition in ALLOWED_TRANSITIONS, (
            f"{case_id}: unsupported status transition {transition}"
        )
    assert history[-1]["status"] == record["status"], (
        f"{case_id}: top-level status must equal the last history entry"
    )


@pytest.mark.parametrize("case_id", EXPECTED_IDS)
def test_snapshot_identities_declared(case_id: str) -> None:
    snapshot = CASES[case_id]["snapshot"]
    assert _GIT_SHA.match(str(snapshot.get("git_sha", ""))), (
        f"{case_id}: snapshot.git_sha must be a 40-hex commit sha"
    )
    assert _SEMVER.match(str(snapshot.get("version", ""))), (
        f"{case_id}: snapshot.version must be semver"
    )
    assert int(snapshot.get("schema_version", 0)) >= 1
    assert str(snapshot.get("scenario", "")).strip(), (
        f"{case_id}: snapshot must declare the active testbed scenario"
    )


@pytest.mark.parametrize("case_id", EXPECTED_IDS)
def test_oracles_declared(case_id: str) -> None:
    record = CASES[case_id]
    oracles = record["oracles"]
    assert oracles.get("deterministic") or oracles.get("semantic"), (
        f"{case_id}: at least one oracle is required"
    )
    if record["execution_mode"] == "deterministic":
        assert oracles.get("deterministic"), (
            f"{case_id}: deterministic execution_mode requires a deterministic oracle"
        )


@pytest.mark.parametrize("case_id", EXPECTED_IDS)
def test_reproduced_cases_carry_evidence_bundle(case_id: str) -> None:
    record = CASES[case_id]
    statuses = {entry["status"] for entry in record["status_history"]}
    if not ({"reproduced", "assigned"} & statuses):
        return
    assert str(record.get("fixture", "")).strip(), (
        f"{case_id}: reproduced cases need a minimal fixture (pytest node id)"
    )
    assert record.get("commands"), f"{case_id}: reproduced cases need exact commands"
    assert str(record.get("before_state_evidence", "")).strip(), (
        f"{case_id}: capture-before-repair evidence is mandatory"
    )


@pytest.mark.parametrize("case_id", EXPECTED_IDS)
def test_assigned_cases_declare_program_and_gate(case_id: str) -> None:
    record = CASES[case_id]
    if record["status"] != "assigned":
        return
    assignment = record.get("assignment") or {}
    assert assignment.get("program") in {"plan-d2", "program-2", "program-3"}, (
        f"{case_id}: assigned cases must name a downstream program"
    )
    assert str(assignment.get("gate", "")).strip(), (
        f"{case_id}: assigned cases must cite the release gate that retires them"
    )
    assert record["owner"] == assignment["program"], (
        f"{case_id}: owner must match the assigned program"
    )


@pytest.mark.parametrize("case_id", EXPECTED_IDS)
def test_fixture_node_ids_resolve(case_id: str) -> None:
    record = CASES[case_id]
    fixture = str(record.get("fixture", "")).strip()
    if not fixture:
        return
    file_part, _, test_name = fixture.partition("::")
    test_file = REPO_ROOT / file_part
    assert test_file.is_file(), f"{case_id}: fixture file {file_part} does not exist"
    assert test_name and f"def {test_name}(" in test_file.read_text(encoding="utf-8"), (
        f"{case_id}: fixture test {test_name!r} not found in {file_part}"
    )
