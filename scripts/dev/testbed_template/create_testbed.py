#!/usr/bin/env python3
"""Create the repo-local initialized testbed vault for incurator development validation."""

from __future__ import annotations

import argparse
import shutil
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

# Robust path resolution
REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "src"
TESTBED_ROOT = REPO_ROOT / "testbed"

# Assets are local to this scenario folder
SCENARIO_ROOT = Path(__file__).parent.resolve()
TESTBED_STAGE = SCENARIO_ROOT / "stage"
FIXTURE_WORKSPACE_RULES = SCENARIO_ROOT / "fixture_workspace_rules"

# Domain-neutral defaults
WORKSPACE_NAME = "Validation Lab"
RAW_DIRS = ["02_Wiki", "03_Notes", "04_Resources", "06_Archives"]

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from curator import config as cfg  # noqa: E402
from curator import db, page_writer, search  # noqa: E402
from curator.workspace.provisioner import prepare_workspace  # noqa: E402

def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")

def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()

def _prepare_root(root: Path, *, force: bool) -> None:
    if root.exists() and not force:
        raise SystemExit(f"{root} already exists. Use --force to reset.")
    root.mkdir(parents=True, exist_ok=True)
    if force:
        for child in list(root.iterdir()):
            _remove(child)

def _ensure_testbed_stage(root: Path) -> None:
    if not TESTBED_STAGE.exists():
        return # Optional stage
    shutil.copytree(TESTBED_STAGE, root, dirs_exist_ok=True)

def _init_like_wiki_init(root: Path) -> cfg.WikiPaths:
    (root / ".obsidian").mkdir(parents=True, exist_ok=True)
    for dirname in cfg.VAULT_TOPOLOGY:
        (root / dirname).mkdir(parents=True, exist_ok=True)

    paths = cfg.WikiPaths(root=root, raw_dirs_override=RAW_DIRS)
    paths.internal.mkdir(parents=True, exist_ok=True)
    paths.collections.mkdir(parents=True, exist_ok=True)
    for layer in cfg.COLLECTION_LAYERS:
        (paths.collections / layer).mkdir(parents=True, exist_ok=True)

    config = dict(cfg.DEFAULT_CONFIG)
    config["llm"]["primary"] = "gemini-cli"
    config["llm"]["gemini_flash_model"] = "gemini-3.1-flash-lite-preview"
    cfg.save_config(paths, config)

    db.init_db(paths.state_db)
    page_writer.rebuild_index(paths, _now_iso())
    search.write_qmd_config(paths, overwrite=True)
    return paths

def _write_testbed_agent_rules(root: Path) -> None:
    ws_dir = root / "01_Workspaces" / WORKSPACE_NAME
    fixture_has_content = FIXTURE_WORKSPACE_RULES.exists() and any(FIXTURE_WORKSPACE_RULES.rglob("*"))
    tmpl_root = FIXTURE_WORKSPACE_RULES if fixture_has_content else None
    for agent in ("antigravity", "gemini-cli"):
        prepare_workspace(
            wiki_root=root,
            workspace=ws_dir,
            agent=agent,
            install_rules=True,
            template_root=tmpl_root,
        )

def create_testbed(*, force: bool) -> None:
    _prepare_root(TESTBED_ROOT, force=force)
    _ensure_testbed_stage(TESTBED_ROOT)
    paths = _init_like_wiki_init(TESTBED_ROOT)
    _write_testbed_agent_rules(paths.root)
    print(f"Created testbed at {TESTBED_ROOT} using assets from {SCENARIO_ROOT}")

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Recreate the testbed.")
    args = parser.parse_args()
    create_testbed(force=args.force)

if __name__ == "__main__":
    main()
