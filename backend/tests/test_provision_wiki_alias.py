"""Tests for `scripts/install/provision_wiki_alias.sh` (v0.42.0).

Regression origin: setup.sh provisioned no `wiki` entry point, so users
hand-rolled one. A hand-rolled alias carried from a Linux machine to macOS kept
`VIRTUAL_ENV=/home/<user>/...` — a path that cannot exist on macOS — so `wiki`
silently degraded to whatever else sat on PATH.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "install" / "provision_wiki_alias.sh"

BEGIN_MARK = "# >>> Added by Incurator >>>"
END_MARK = "# <<< Added by Incurator <<<"


pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None, reason="bash is required to run the installer script"
)


def run_script(repo_root: Path, *rc_files: Path, original_path: str | None = None):
    env = dict(os.environ)
    if original_path is not None:
        env["INCURATOR_ORIGINAL_PATH"] = original_path
    return subprocess.run(
        ["bash", str(SCRIPT), str(repo_root), *[str(p) for p in rc_files]],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "Incurator"
    (repo / ".venv" / "bin").mkdir(parents=True)
    launcher = repo / ".venv" / "bin" / "wiki"
    launcher.write_text("#!/bin/sh\necho incurator 9.9.9\n", encoding="utf-8")
    launcher.chmod(0o755)
    return repo


def test_alias_target_is_derived_from_the_repo_root(fake_repo: Path, tmp_path: Path):
    rc = tmp_path / ".zshrc"
    rc.write_text("export EDITOR=vim\n", encoding="utf-8")

    result = run_script(fake_repo, rc)

    assert result.returncode == 0, result.stderr
    body = rc.read_text(encoding="utf-8")
    assert f'alias wiki="{fake_repo}/.venv/bin/wiki"' in body
    # The pre-existing content must survive untouched.
    assert "export EDITOR=vim" in body
    # Never emit a foreign home layout.
    assert "/home/" not in body


def test_rerun_replaces_instead_of_appending(fake_repo: Path, tmp_path: Path):
    rc = tmp_path / ".zshrc"
    rc.write_text("export EDITOR=vim\n", encoding="utf-8")

    run_script(fake_repo, rc)
    first = rc.read_text(encoding="utf-8")
    run_script(fake_repo, rc)
    second = rc.read_text(encoding="utf-8")

    assert second.count(BEGIN_MARK) == 1
    assert second.count(END_MARK) == 1
    assert second.count("alias wiki=") == 1
    # Idempotent: the second run must not drift the file at all.
    assert first == second


def test_legacy_hand_rolled_alias_is_repaired(fake_repo: Path, tmp_path: Path):
    """The exact broken state found in the field: a Linux path on macOS."""
    rc = tmp_path / ".zshrc"
    rc.write_text(
        "export EDITOR=vim\n"
        "\n"
        "# Added by Incurator \n"
        "alias wiki='VIRTUAL_ENV=/home/shin/shinywings/Incurator/.venv uv run wiki'\n"
        "\n"
        "# Added by Antigravity IDE\n"
        "export AGY=1\n",
        encoding="utf-8",
    )

    result = run_script(fake_repo, rc)

    assert result.returncode == 0, result.stderr
    body = rc.read_text(encoding="utf-8")
    assert "/home/shin" not in body
    assert "uv run wiki" not in body
    assert body.count("alias wiki=") == 1
    assert f'alias wiki="{fake_repo}/.venv/bin/wiki"' in body
    # An unrelated tool's block must not be collateral damage.
    assert "# Added by Antigravity IDE" in body
    assert "export AGY=1" in body


def test_handles_zsh_and_bash_rc_together(fake_repo: Path, tmp_path: Path):
    zshrc = tmp_path / ".zshrc"
    bashrc = tmp_path / ".bashrc"
    zshrc.write_text("# zsh\n", encoding="utf-8")
    bashrc.write_text("# bash\n", encoding="utf-8")

    result = run_script(fake_repo, zshrc, bashrc)

    assert result.returncode == 0, result.stderr
    for rc in (zshrc, bashrc):
        body = rc.read_text(encoding="utf-8")
        assert f'alias wiki="{fake_repo}/.venv/bin/wiki"' in body
        assert body.count(BEGIN_MARK) == 1


def test_warns_when_another_wiki_is_earlier_on_path(
    fake_repo: Path, tmp_path: Path
):
    conflicting_dir = tmp_path / "anaconda" / "bin"
    conflicting_dir.mkdir(parents=True)
    conflicting = conflicting_dir / "wiki"
    conflicting.write_text("#!/bin/sh\necho incurator 0.4.3\n", encoding="utf-8")
    conflicting.chmod(0o755)

    rc = tmp_path / ".zshrc"
    rc.write_text("", encoding="utf-8")

    result = run_script(fake_repo, rc, original_path=str(conflicting_dir))

    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert "ANOTHER 'wiki' IS EARLIER ON YOUR PATH" in combined
    assert str(conflicting) in combined
    # The warning must name the correct launcher so the fix is actionable.
    assert f"{fake_repo}/.venv/bin/wiki" in combined


def test_no_warning_when_path_already_resolves_to_this_repo(
    fake_repo: Path, tmp_path: Path
):
    rc = tmp_path / ".zshrc"
    rc.write_text("", encoding="utf-8")

    result = run_script(
        fake_repo, rc, original_path=str(fake_repo / ".venv" / "bin")
    )

    assert result.returncode == 0, result.stderr
    assert "ANOTHER 'wiki'" not in (result.stdout + result.stderr)


def test_missing_repo_root_argument_fails_loudly():
    result = subprocess.run(
        ["bash", str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert result.returncode != 0
    assert "repo root is required" in result.stderr
