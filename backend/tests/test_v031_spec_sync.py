"""Guard tests for v0.3.1 spec synchronization.

These enforce the repo rule that the three spec domains (curator_schema,
system_behavior, plugin_schema) stay version-synchronized, that exactly one
active spec lives at each domain root, and that the previous active version is
archived. They also pin the backend ``__version__`` to the active spec line so
the docs and package cannot silently drift apart.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from curator import __version__

REPO_ROOT = Path(__file__).resolve().parents[2]
SPECS_ROOT = REPO_ROOT / "docs" / "specs"

ACTIVE_VERSION = "0.3.1"
PREVIOUS_VERSION = "0.2.2"

DOMAINS = {
    "curator_schema": "SCHEMA",
    "system_behavior": "SYSTEM_BEHAVIOR",
    "plugin_schema": "PLUGIN_SCHEMA",
}


def _root_specs(domain: str, stem: str) -> list[Path]:
    domain_dir = SPECS_ROOT / domain
    return [
        p
        for p in domain_dir.glob(f"{stem}_v*.md")
        if p.parent.name != "archives"
    ]


@pytest.mark.parametrize("domain,stem", list(DOMAINS.items()))
def test_single_active_spec_per_domain(domain: str, stem: str) -> None:
    roots = _root_specs(domain, stem)
    assert len(roots) == 1, (
        f"{domain} must contain exactly one active spec at its root, "
        f"found: {[p.name for p in roots]}"
    )
    assert roots[0].name == f"{stem}_v{ACTIVE_VERSION}.md"


@pytest.mark.parametrize("domain,stem", list(DOMAINS.items()))
def test_previous_version_archived(domain: str, stem: str) -> None:
    archived = SPECS_ROOT / domain / "archives" / f"{stem}_v{PREVIOUS_VERSION}.md"
    assert archived.exists(), f"{archived} must be archived, not deleted"


@pytest.mark.parametrize("domain,stem", list(DOMAINS.items()))
def test_active_spec_declares_active_version(domain: str, stem: str) -> None:
    spec = SPECS_ROOT / domain / f"{stem}_v{ACTIVE_VERSION}.md"
    text = spec.read_text(encoding="utf-8")
    title = text.splitlines()[0]
    assert ACTIVE_VERSION in title, (
        f"{spec.name} title must declare v{ACTIVE_VERSION}: {title!r}"
    )


def test_backend_version_matches_active_spec_line() -> None:
    # __version__ must be on the same minor line as the active spec set.
    active_line = ".".join(ACTIVE_VERSION.split(".")[:2])
    backend_line = ".".join(__version__.split(".")[:2])
    assert re.match(r"^\d+\.\d+\.\d+$", __version__), __version__
    assert backend_line == active_line, (
        f"backend __version__={__version__} must match active spec line "
        f"{active_line}.x"
    )
