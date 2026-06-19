"""Guard tests for spec synchronization.

These enforce the repo rule that the spec domains (curator_schema,
system_behavior, plugin_schema) maintain static names (SCHEMA.md,
SYSTEM_BEHAVIOR.md, PLUGIN_SCHEMA.md) without version suffixes,
that no archives/ folders exist, and that they declare the active version
in their headers. They also pin the backend version to the active spec line.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from curator import __version__

REPO_ROOT = Path(__file__).resolve().parents[2]
SPECS_ROOT = REPO_ROOT / "docs" / "specs"

ACTIVE_VERSION = "0.12.0"

DOMAINS = {
    "curator_schema": "SCHEMA",
    "system_behavior": "SYSTEM_BEHAVIOR",
    "plugin_schema": "PLUGIN_SCHEMA",
    "search_engine": "SEARCH_ENGINE_SCHEMA",
}


@pytest.mark.parametrize("domain,stem", list(DOMAINS.items()))
def test_static_spec_file_exists_and_no_versioned_specs(domain: str, stem: str) -> None:
    domain_dir = SPECS_ROOT / domain
    static_file = domain_dir / f"{stem}.md"
    
    assert static_file.exists(), f"Static spec file {static_file} must exist"
    
    # Ensure there are no versioned spec files matching stem_v*.md
    versioned_files = list(domain_dir.glob(f"{stem}_v*.md"))
    assert not versioned_files, f"No versioned spec files allowed in {domain}, found: {versioned_files}"
    
    # Ensure there is no archives directory
    archives_dir = domain_dir / "archives"
    assert not archives_dir.exists(), f"Archives directory must not exist under {domain_dir}"


@pytest.mark.parametrize("domain,stem", list(DOMAINS.items()))
def test_active_spec_declares_active_version(domain: str, stem: str) -> None:
    spec = SPECS_ROOT / domain / f"{stem}.md"
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
