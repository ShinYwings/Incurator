"""Scenario 3: verify query session save-back metadata in testbed."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml


def run_scenario() -> None:
    root = Path("testbed").resolve()
    workspace = root / "01_Workspaces" / "Gaussian Splatting Geometry Lab"
    if not (workspace / "curate.yml").exists():
        raise SystemExit("workspace curate.yml missing")

    before = {p.name for p in (root / ".curator" / "Collections" / "04_Exhibitions").glob("EXH-*.md")}
    env = os.environ.copy()
    env["WIKI_ROOT"] = str(root)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "llm_wiki.cli",
            "query",
            "gaussian",
            "--workspace",
            str(workspace),
            "--save-as",
            "Scenario query session",
            "--no-intent-classify",
            "--lex",
            "--limit",
            "5",
        ],
        cwd=str(root),
        env=env,
        text=True,
        input="\n",
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)

    after_paths = list((root / ".curator" / "Collections" / "04_Exhibitions").glob("EXH-*.md"))
    created = [p for p in after_paths if p.name not in before]
    if not created:
        raise SystemExit("query did not create an Exhibition")

    text = created[0].read_text(encoding="utf-8")
    fm = yaml.safe_load(text.split("---", 2)[1])
    assert str(fm.get("query_session", "")).startswith("QRY-"), fm
    assert fm.get("workspace") == "Gaussian Splatting Geometry Lab", fm
    assert fm.get("ephemeral") is False, fm
    print("scenario_3_query_session: ok")


if __name__ == "__main__":
    run_scenario()
