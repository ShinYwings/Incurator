"""ROADMAP B1: the docs put `state.sqlite` inside the vault. It is not there.

`WikiPaths.state_db` resolves to the MACHINE-LOCAL repo cache
(`.cache/vaults/<sha256(resolved_root)[:16]>/state.sqlite`), not to
`<vault>/.curator/state.sqlite`. `SYSTEM_BEHAVIOR.md` said both things in
different sections, and the vault tree in `CLAUDE.md` and the contribution
guides showed the wrong one.

This is not a cosmetic doc bug. On the reference vault the documented path holds
a **0-byte stub** while the real database is 287 MB in the cache — so following
the docs finds a file, opens it, reads zero rows, and concludes the vault was
never ingested. That happened during this project's own development, twice.
"""

from __future__ import annotations

from pathlib import Path

from curator import config as cfg

REPO = Path(__file__).resolve().parents[2]


def test_state_db_is_not_inside_the_vault(tmp_path: Path) -> None:
    paths = cfg.WikiPaths(tmp_path / "vault")
    state_db = paths.state_db
    assert not str(state_db).startswith(str(paths.internal)), (
        f"state_db resolved to {state_db}, inside the vault's .curator/"
    )
    assert "vaults" in state_db.parts, f"expected a repo-cache path, got {state_db}"


def test_no_document_places_state_sqlite_under_curator() -> None:
    """The tree diagrams are what a new contributor and every agent read first."""
    docs = [
        REPO / "CLAUDE.md",
        REPO / "AGENTS.md",
        REPO / "docs" / "guides" / "CONTRIBUTION_GUIDE.md",
        REPO / "docs" / "guides" / "CONTRIBUTION_GUIDE_KR.md",
        REPO / "docs" / "specs" / "system_behavior" / "SYSTEM_BEHAVIOR.md",
    ]
    offenders: list[str] = []
    for doc in docs:
        if not doc.exists():
            continue
        for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            # a tree entry that hangs `state.sqlite` off the vault's .curator/
            if stripped.startswith(("├──", "└──")) and "state.sqlite" in stripped:
                offenders.append(f"{doc.name}:{n}: {stripped}")
            if "`state.sqlite` (source of truth)" in stripped and ".curator/" in stripped:
                offenders.append(f"{doc.name}:{n}: {stripped[:80]}")
    assert not offenders, (
        "these place state.sqlite inside the vault; it lives in the machine-local "
        "repo cache:\n  " + "\n  ".join(offenders)
    )
