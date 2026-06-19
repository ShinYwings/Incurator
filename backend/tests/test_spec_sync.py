"""Guard tests for spec synchronization.

These enforce the repo rule that the spec domains (curator_schema,
system_behavior, plugin_schema, search_engine) maintain static names (SCHEMA.md,
SYSTEM_BEHAVIOR.md, PLUGIN_SCHEMA.md, SEARCH_ENGINE_SCHEMA.md) without version
suffixes, that no archives/ folders exist, and that they declare the active
version line in their headers.

The active version is derived from the build manifests (backend/pyproject.toml,
plugin/package.json, plugin/manifest.json) — the single source of truth — NOT
from installed package metadata. Reading the build manifest directly means the
check never depends on whether the editable dev install has been refreshed, so a
version bump no longer requires a reinstall to validate locally.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPECS_ROOT = REPO_ROOT / "docs" / "specs"


def _pyproject_version() -> str:
    text = (REPO_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    # Scope to the [project] table so a tool-section `version =` can't shadow it
    # (Python 3.10 has no stdlib tomllib, so parse the relevant block directly).
    block = re.search(r"(?ms)^\[project\]\s*\n(.*?)(?=^\[|\Z)", text)
    assert block, "pyproject.toml missing a [project] table"
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', block.group(1))
    assert m, "pyproject.toml [project] table missing a version"
    return m.group(1)


def _json_version(relpath: str) -> str:
    data = json.loads((REPO_ROOT / relpath).read_text(encoding="utf-8"))
    return data["version"]


# Single source of truth: the build manifests.
BUILD_MANIFEST_VERSIONS = {
    "backend/pyproject.toml": _pyproject_version(),
    "plugin/package.json": _json_version("plugin/package.json"),
    "plugin/manifest.json": _json_version("plugin/manifest.json"),
}
ACTIVE_VERSION = BUILD_MANIFEST_VERSIONS["backend/pyproject.toml"]
# Specs declare the MAJOR.MINOR line, so patch bumps don't require spec edits.
ACTIVE_LINE = ".".join(ACTIVE_VERSION.split(".")[:2])

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
def test_active_spec_declares_active_line(domain: str, stem: str) -> None:
    # The spec title must declare the active MAJOR.MINOR line from the build
    # manifest, e.g. a title `(v0.17.0)` satisfies the `0.17` line for any 0.17.x.
    spec = SPECS_ROOT / domain / f"{stem}.md"
    title = spec.read_text(encoding="utf-8").splitlines()[0]
    assert f"v{ACTIVE_LINE}" in title, (
        f"{spec.name} title must declare the active spec line v{ACTIVE_LINE}.x "
        f"(build-manifest version {ACTIVE_VERSION}): {title!r}"
    )


def test_build_manifests_agree_on_version() -> None:
    # All three build manifests are the single source of truth and must agree.
    assert re.match(r"^\d+\.\d+\.\d+$", ACTIVE_VERSION), ACTIVE_VERSION
    mismatched = {k: v for k, v in BUILD_MANIFEST_VERSIONS.items() if v != ACTIVE_VERSION}
    assert not mismatched, (
        f"All build manifests must agree on version {ACTIVE_VERSION}; mismatched: {mismatched}"
    )
