#!/usr/bin/env python3
"""Write shared backend/plugin build metadata for local setup."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


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
    manifest = {
        "schema": 1,
        "git_commit": git_commit(),
        "git_dirty": git_dirty(),
        "backend_version": backend_version(),
        "plugin_version": read_version(ROOT / "plugin/manifest.json"),
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
