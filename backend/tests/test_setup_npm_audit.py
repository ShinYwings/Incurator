"""`./setup.sh` must apply npm security fixes, and must survive them failing.

Regression origin: the plugin lockfile carried a known-vulnerable transitive
`nanoid` for an unknown span because nothing ran `npm audit fix` automatically —
it was only ever run by hand as a release-evidence gate, never wired into setup.
`git log -S"audit" -- setup.sh` returned zero commits before v0.52.1.

`setup.sh` runs under `set -euo pipefail`, which makes the guards a correctness
requirement rather than style: `npm audit fix` exits non-zero when advisories
remain that it cannot fix semver-compatibly, and `npm audit` exits non-zero
whenever any advisory is open. Unguarded, either would abort a developer's whole
setup over an upstream advisory they cannot act on.
"""

import re
from pathlib import Path

import pytest

SETUP = Path(__file__).resolve().parents[2] / "setup.sh"


@pytest.fixture(scope="module")
def setup_text() -> str:
    return SETUP.read_text(encoding="utf-8")


def test_setup_script_exists() -> None:
    assert SETUP.is_file(), f"setup.sh not found at {SETUP}"


def test_setup_still_runs_under_strict_mode(setup_text: str) -> None:
    """If this ever relaxes, the guards below stop being load-bearing."""
    assert "set -euo pipefail" in setup_text


def test_npm_audit_fix_runs_during_setup(setup_text: str) -> None:
    assert re.search(r"^\s*npm audit fix\b", setup_text, re.MULTILINE), (
        "setup.sh must apply semver-compatible npm security fixes"
    )


def test_npm_audit_fix_cannot_abort_setup(setup_text: str) -> None:
    match = re.search(r"^\s*npm audit fix.*$", setup_text, re.MULTILINE)
    assert match is not None
    assert "|| true" in match.group(0), (
        "unguarded `npm audit fix` aborts setup under `set -e` whenever an "
        "advisory remains that npm cannot fix semver-compatibly"
    )


def test_npm_audit_fix_never_uses_force(setup_text: str) -> None:
    """`--force` installs breaking major bumps with nobody reviewing them."""
    assert "npm audit fix --force" not in setup_text
    assert not re.search(r"npm audit fix[^\n]*\s--force\b", setup_text)


def test_remaining_advisories_are_reported_not_hidden(setup_text: str) -> None:
    assert "npm audit still reports unfixed advisories" in setup_text


def test_audit_precedes_the_plugin_build(setup_text: str) -> None:
    """Fixes must land in the lockfile before the bundle is built from it."""
    audit = setup_text.index("npm audit fix")
    build = setup_text.index("npm run build")
    assert audit < build, "npm audit fix must run before npm run build"


def test_audit_runs_inside_the_npm_availability_guard(setup_text: str) -> None:
    """A machine without npm must still complete backend setup."""
    guard = setup_text.index("if command -v npm")
    audit = setup_text.index("npm audit fix")
    fallback = setup_text.index("npm not found. Skipping plugin build.")
    assert guard < audit < fallback
