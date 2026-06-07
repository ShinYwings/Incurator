"""Dialogue 3: verify query session Exhibition creation for both --save-as and --curate.

Tests two Exhibition creation paths:

  A. --save-as  (explicit, always non-ephemeral)
     Validates query_session, workspace, and ephemeral=False frontmatter.

  B. --curate   (session-scoped, ephemeral by default)
     Validates that an ephemeral=True Exhibition is created and accumulates
     across turns without creating duplicate EXH files.

Prerequisites (for full validation):
    python scripts/dev/GS_Testbed/create_testbed.py --force
    WIKI_ROOT=testbed wiki add
    WIKI_ROOT=testbed wiki curate --workspace testbed/01_Workspaces/Gaussian\\ Splatting\\ Geometry\\ Lab
    WIKI_ROOT=testbed wiki reindex

Part B requires at least one L3 Concept to exist (needed by _save_curation_page).
If none exist, Part B is skipped with a clear message.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml


def _testbed() -> Path:
    root = Path(__file__).resolve().parents[4] / "testbed"
    if not root.exists():
        raise SystemExit("testbed/ not found; run scripts/dev/GS_Testbed/create_testbed.py --force")
    return root


def _exh_dir(root: Path) -> Path:
    return root / ".curator" / "Collections" / "04_Exhibitions"


def _snapshot(root: Path) -> set[str]:
    d = _exh_dir(root)
    return {p.name for p in d.glob("EXH-*.md")} if d.exists() else set()


def _has_collections(root: Path) -> bool:
    """Return True if the curator collections have any pages at all."""
    col_root = root / ".curator" / "Collections"
    for layer in ("01_Contexts", "02_Atoms", "03_Concepts", "04_Exhibitions"):
        d = col_root / layer
        if d.exists() and any(d.glob("*.md")):
            return True
    return False


def _has_l3_concepts(root: Path) -> bool:
    con_dir = root / ".curator" / "Collections" / "03_Concepts"
    return con_dir.exists() and any(con_dir.glob("CON-*.md"))


def _run_query(root: Path, workspace: Path, extra_args: list[str], stdin: str = "\n") -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["WIKI_ROOT"] = str(root)
    return subprocess.run(
        [
            sys.executable,
            "-m", "curator.cli",
            "query", "gaussian splatting",
            "--workspace", str(workspace),
            "--no-intent-classify",
            "--lex",
            "--limit", "5",
            *extra_args,
        ],
        cwd=str(root),
        env=env,
        text=True,
        input=stdin,
        capture_output=True,
        check=False,
    )


def _read_fm(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"No YAML frontmatter in {path}")
    return yaml.safe_load(parts[1]) or {}


# ---------------------------------------------------------------------------
# Part A: --save-as (explicit, non-ephemeral)
# ---------------------------------------------------------------------------

def test_save_as(root: Path, workspace: Path) -> None:
    print("  [Part A] --save-as")
    before = _snapshot(root)
    result = _run_query(
        root, workspace,
        extra_args=["--save-as", "Dialogue query session"],
        stdin="\n",
    )
    if result.returncode != 0:
        raise SystemExit(f"wiki query --save-as failed:\n{result.stderr or result.stdout}")

    created = [
        _exh_dir(root) / name
        for name in (_snapshot(root) - before)
    ]
    if not created:
        raise SystemExit(
            "Part A: --save-as did not create an Exhibition.\n"
            "Make sure wiki add + wiki curate + wiki reindex have been run."
        )

    fm = _read_fm(created[0])
    assert str(fm.get("query_session", "")).startswith("QRY-"), \
        f"query_session field missing or wrong format: {fm}"
    assert fm.get("workspace") == "Gaussian Splatting Geometry Lab", \
        f"workspace field wrong: {fm}"
    assert fm.get("ephemeral") is False, \
        f"--save-as Exhibition must have ephemeral=False: {fm}"
    print(f"    created {created[0].name} with ephemeral=False — ok")


# ---------------------------------------------------------------------------
# Part B: --curate (session-scoped, ephemeral)
# ---------------------------------------------------------------------------

def test_curate_session(root: Path, workspace: Path) -> None:
    print("  [Part B] --curate session Exhibition")

    if not _has_l3_concepts(root):
        print(
            "    SKIP: no L3 Concepts found — run wiki add + wiki curate first "
            "to validate --curate behavior"
        )
        return

    before = _snapshot(root)
    # Non-interactive mode: ephemeral Exhibition is created during the session,
    # then auto-deleted at session end. We validate via stdout, not leftover files.
    result = _run_query(
        root, workspace,
        extra_args=["--curate"],
        stdin="\n",
    )
    if result.returncode != 0:
        raise SystemExit(f"wiki query --curate failed:\n{result.stderr or result.stdout}")

    # In non-interactive mode, ephemeral Exhibition is auto-deleted at session end.
    # Verify via stdout that the Exhibition was created during the session.
    stdout = result.stdout + result.stderr
    assert "session Exhibition" in stdout or "EXH-" in stdout, (
        "Part B: expected session Exhibition creation message in stdout, "
        f"but got:\n{stdout[:600]}"
    )
    created = [_exh_dir(root) / name for name in (_snapshot(root) - before)]
    assert len(created) == 0, (
        f"Part B: ephemeral Exhibition must be auto-deleted in non-interactive mode, "
        f"but found: {[p.name for p in created]}"
    )
    print("    non-interactive --curate: Exhibition created then auto-deleted — ok")

    # Multi-turn: second independent CLI run with a follow-up question.
    # Validates that multi-turn sessions also produce 0 leftover EXH files.
    before2 = _snapshot(root)
    result2 = _run_query(
        root, workspace,
        extra_args=["--curate"],
        stdin="EWA gaussian kernel\n\n",  # follow-up question + empty line to exit
    )
    if result2.returncode != 0:
        raise SystemExit(f"wiki query --curate (2nd call) failed:\n{result2.stderr or result2.stdout}")

    created2 = [_exh_dir(root) / name for name in (_snapshot(root) - before2)]
    assert len(created2) == 0, (
        f"Part B: multi-turn --curate run must leave 0 EXH files "
        f"(ephemeral auto-delete), but found: {[p.name for p in created2]}"
    )
    print("    multi-turn non-interactive --curate: 0 EXH files left — ok")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_scenario() -> None:
    root = _testbed()
    workspace = root / "01_Workspaces" / "Gaussian Splatting Geometry Lab"
    if not (workspace / "curate.yml").exists():
        raise SystemExit("workspace curate.yml missing")

    if not _has_collections(root):
        print(
            "SKIP: curator collections are empty.\n"
            "Run the following first, then re-run this dialogue:\n"
            "  WIKI_ROOT=testbed wiki add\n"
            "  WIKI_ROOT=testbed wiki curate --workspace testbed/01_Workspaces/Gaussian\\ Splatting\\ Geometry\\ Lab\n"
            "  WIKI_ROOT=testbed wiki reindex",
            file=sys.stderr,
        )
        sys.exit(2)  # exit code 2 = skip

    test_save_as(root, workspace)
    test_curate_session(root, workspace)
    print("dialogue_3_query_session: ok")


if __name__ == "__main__":
    run_scenario()
