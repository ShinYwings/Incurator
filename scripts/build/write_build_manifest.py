#!/usr/bin/env python3
"""Write shared backend/plugin source build fingerprints for local setup."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


BACKEND_PATTERNS = [
    "backend/pyproject.toml",
    "backend/src/curator/**/*.py",
    "backend/src/curator/data/models.json",
]

PLUGIN_PATTERNS = [
    "plugin/main.ts",
    "plugin/package.json",
    "plugin/manifest.json",
    "plugin/styles.css",
    "plugin/src/**/*.ts",
]

BUILD_PATTERNS = [
    "setup.sh",
    "scripts/build/hatch_build.py",
    "scripts/build/write_build_manifest.py",
]

EXCLUDED_SUFFIXES = {
    "backend/src/curator/data/build_manifest.json",
    "plugin/src/generated/buildManifest.json",
}


def read_version(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        version = data.get("version")
        if isinstance(version, str):
            return version
    except Exception:
        pass
    return ""


def backend_version() -> str:
    pyproject = (ROOT / "backend/pyproject.toml").read_text(encoding="utf-8")
    for line in pyproject.splitlines():
        if line.startswith("version = "):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def files_for(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(ROOT.glob(pattern))
    out = []
    for path in sorted(set(paths)):
        rel = path.relative_to(ROOT).as_posix()
        if rel in EXCLUDED_SUFFIXES:
            continue
        if path.is_file():
            out.append(path)
    return out


def fingerprint(patterns: list[str]) -> str:
    digest = hashlib.sha256()
    for path in files_for(patterns):
        rel = path.relative_to(ROOT).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def git_dirty() -> bool:
    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return bool(status.strip())
    except Exception:
        return False


def main() -> int:
    backend_fp = fingerprint(BACKEND_PATTERNS + BUILD_PATTERNS)
    plugin_fp = fingerprint(PLUGIN_PATTERNS + BUILD_PATTERNS)
    combined_fp = hashlib.sha256(f"{backend_fp}\0{plugin_fp}".encode("utf-8")).hexdigest()
    manifest = {
        "schema": 1,
        "repo_root": str(ROOT),
        "git_commit": git_commit(),
        "git_dirty": git_dirty(),
        "backend_version": backend_version(),
        "plugin_version": read_version(ROOT / "plugin/manifest.json"),
        "backend_fingerprint": backend_fp,
        "plugin_fingerprint": plugin_fp,
        "combined_fingerprint": combined_fp,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }

    targets = [
        ROOT / "backend/src/curator/data/build_manifest.json",
        ROOT / "plugin/src/generated/buildManifest.json",
    ]
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"[incurator] wrote {target.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
