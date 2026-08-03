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

import functools
import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SPECS_ROOT = REPO_ROOT / "docs" / "specs"


def _parse_project_version(text: str) -> str:
    # Scope to the [project] table so a tool-section `version =` can't shadow it
    # (Python 3.10 has no stdlib tomllib, so parse the relevant block directly).
    block = re.search(r"(?ms)^\[project\]\s*\n(.*?)(?=^\[|\Z)", text)
    assert block, "pyproject.toml missing a [project] table"
    # Accept both single- and double-quoted version strings (valid TOML variants).
    m = re.search(r"""(?m)^version\s*=\s*["']([^"']+)["']""", block.group(1))
    assert m, "pyproject.toml [project] table missing a version"
    return m.group(1)


def _pyproject_version() -> str:
    text = (REPO_ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8")
    return _parse_project_version(text)


def _json_version(relpath: str) -> str:
    data = json.loads((REPO_ROOT / relpath).read_text(encoding="utf-8"))
    return data["version"]


def _lockfile_versions(relpath: str) -> dict[str, str]:
    # npm records the package version twice in a lockfile: at the top level and
    # in the root entry of `packages`. `npm install` rewrites both from
    # package.json, so a bump that edits only package.json leaves BOTH stale and
    # the next unrelated npm invocation produces a surprise diff.
    data = json.loads((REPO_ROOT / relpath).read_text(encoding="utf-8"))
    versions = {relpath: data["version"]}
    root_entry = data.get("packages", {}).get("")
    if isinstance(root_entry, dict) and "version" in root_entry:
        versions[f'{relpath} packages[""]'] = root_entry["version"]
    return versions


# Single source of truth: the build manifests. Resolved lazily (cached) so the
# file I/O happens at test-run time, not at import/collection time — a missing or
# unavailable manifest fails the specific test, never the whole collection phase.
# (PEP 562 module __getattr__ would not help here: the tests reference these as
# bare globals, which compile to LOAD_GLOBAL and never trigger module __getattr__.)
@functools.lru_cache(maxsize=1)
def _build_manifest_versions() -> dict[str, str]:
    return {
        "backend/pyproject.toml": _pyproject_version(),
        "plugin/package.json": _json_version("plugin/package.json"),
        "plugin/manifest.json": _json_version("plugin/manifest.json"),
        **_lockfile_versions("plugin/package-lock.json"),
    }


def _active_version() -> str:
    return _build_manifest_versions()["backend/pyproject.toml"]


def _active_line() -> str:
    # Specs declare the MAJOR.MINOR line, so patch bumps don't require spec edits.
    return ".".join(_active_version().split(".")[:2])


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
    active_line = _active_line()
    active_version = _active_version()
    spec = SPECS_ROOT / domain / f"{stem}.md"
    title = spec.read_text(encoding="utf-8").splitlines()[0]
    assert f"v{active_line}" in title, (
        f"{spec.name} title must declare the active spec line v{active_line}.x "
        f"(build-manifest version {active_version}): {title!r}"
    )


def test_pyproject_version_accepts_both_quote_styles() -> None:
    double = '[project]\nname = "x"\nversion = "1.2.3"\n\n[tool.foo]\nversion = "9.9.9"\n'
    single = "[project]\nname = 'x'\nversion = '1.2.3'\n"
    # The [tool.foo] version must not shadow the [project] one.
    assert _parse_project_version(double) == "1.2.3"
    assert _parse_project_version(single) == "1.2.3"


def test_build_manifests_agree_on_version() -> None:
    # The build manifests are the single source of truth and must agree. The npm
    # lockfile is included because it carries the version too: v0.40.3 and
    # v0.41.0 both bumped package.json/manifest.json/pyproject.toml while
    # leaving plugin/package-lock.json pinned at 0.40.2, and nothing caught it
    # until an unrelated `npx` run rewrote the file.
    versions = _build_manifest_versions()
    active_version = versions["backend/pyproject.toml"]
    assert re.match(r"^\d+\.\d+\.\d+$", active_version), active_version
    mismatched = {k: v for k, v in versions.items() if v != active_version}
    assert not mismatched, (
        f"All build manifests must agree on version {active_version}; mismatched: {mismatched}"
    )
