"""Contradiction decision storage for incurator.

Tracks dismissed and resolved ATM-pair decisions so `wiki sync` can
skip re-detecting them in future deep-check runs. Agents can also
dismiss or resolve contradictions via MCP tools.

Storage: .curator/contradiction_dismissed.json
"""

from __future__ import annotations

import json
from pathlib import Path


from . import constants as consts

_DISMISSED_FILE = consts.FILE_DISMISSED_CONTRADICTIONS


def _storage_path(paths) -> Path:
    return paths.internal / _DISMISSED_FILE


def load_dismissed(paths) -> list[dict]:
    """Load dismissed/resolved pairs from disk. Returns [] if file missing."""
    p = _storage_path(paths)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def normalize_id(atom_id: str) -> str:
    """Normalize 'ATM-xxx' or '02_Atoms/ATM-xxx.md' to bare 'ATM-xxx'."""
    stem = Path(atom_id).stem
    return stem.rsplit("/", 1)[-1] if "/" in stem else stem


def is_dismissed(dismissed: list[dict], atom_a: str, atom_b: str) -> bool:
    """Order-insensitive check against the dismissed list."""
    pair = frozenset([normalize_id(atom_a), normalize_id(atom_b)])
    return any(frozenset(e["pair"]) == pair for e in dismissed)


def add_dismissed(paths, atom_a: str, atom_b: str, reason: str = "") -> None:
    """Persist a dismissed (or resolved) pair. No-op if already present."""
    from . import page_writer as _pw
    a = normalize_id(atom_a)
    b = normalize_id(atom_b)
    dismissed = load_dismissed(paths)
    if is_dismissed(dismissed, a, b):
        return
    dismissed.append({
        "pair": [a, b],
        "reason": reason,
        "at": _pw.today_iso(),
    })
    _save(paths, dismissed)


def _save(paths, dismissed: list[dict]) -> None:
    p = _storage_path(paths)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(dismissed, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def clear_flagged(paths, atom_a: str, atom_b: str) -> None:
    """Set is_flagged_for_agent: false on both atoms after dismiss or resolve."""
    from . import page_writer as _pw
    for atom_id in [normalize_id(atom_a), normalize_id(atom_b)]:
        atom_path = paths.atoms / f"{atom_id}.md"
        if not atom_path.exists():
            continue
        page = _pw.read_page(atom_path)
        if page is None:
            continue
        if page.frontmatter.get("is_flagged_for_agent"):
            page.frontmatter["is_flagged_for_agent"] = False
            _pw.write_page(atom_path, page.to_markdown())


def apply_resolution(paths, atom_a: str, atom_b: str, proposal: dict) -> None:
    """Write LLM-proposed body edits to both Atoms and mark resolved.

    proposal keys:
        atom_a_body_revised: revised body (no frontmatter) for atom_a
        atom_b_body_revised: revised body (no frontmatter) for atom_b

    After writing:
    - is_flagged_for_agent is set to false
    - is_verified_by_human is set to true
    - last_updated is refreshed
    - The pair is stored as dismissed with reason="resolved"
    """
    from . import page_writer as _pw
    today = _pw.today_iso()

    pairs = [
        (normalize_id(atom_a), proposal.get("atom_a_body_revised", "")),
        (normalize_id(atom_b), proposal.get("atom_b_body_revised", "")),
    ]
    for atom_id, revised_body in pairs:
        if not revised_body.strip():
            continue
        atom_path = paths.atoms / f"{atom_id}.md"
        if not atom_path.exists():
            continue
        page = _pw.read_page(atom_path)
        if page is None:
            continue
        page.body = revised_body.strip()
        page.frontmatter["is_flagged_for_agent"] = False
        page.frontmatter["is_verified_by_human"] = True
        page.frontmatter["last_updated"] = today
        _pw.write_page(atom_path, page.to_markdown())

    add_dismissed(paths, atom_a, atom_b, reason="resolved")
