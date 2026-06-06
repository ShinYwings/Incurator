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
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "backend" / "src"
TESTBED_ROOT = REPO_ROOT / "testbed"

# Domain-neutral defaults
WORKSPACE_NAME = "Validation Lab"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from curator import config as cfg, constants as consts  # noqa: E402
from curator import db, page_writer  # noqa: E402
from curator.workspace.provisioner import prepare_workspace  # noqa: E402

RAW_DIRS = [consts.DIR_WIKI, consts.DIR_NOTES, consts.DIR_RESOURCES, consts.DIR_ARCHIVES]

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

def _ensure_testbed_stage(root: Path, stage_path: Path) -> None:
    if not stage_path.exists():
        return # Optional stage
    shutil.copytree(stage_path, root, dirs_exist_ok=True)

def _init_like_wiki_init(root: Path, scenario_root: Path) -> cfg.WikiPaths:
    (root / ".obsidian").mkdir(parents=True, exist_ok=True)
    for dirname in cfg.VAULT_TOPOLOGY:
        (root / dirname).mkdir(parents=True, exist_ok=True)

    paths = cfg.WikiPaths(root=root, raw_dirs_override=RAW_DIRS)
    paths.internal.mkdir(parents=True, exist_ok=True)
    paths.collections.mkdir(parents=True, exist_ok=True)
    for layer in cfg.COLLECTION_LAYERS:
        (paths.collections / layer).mkdir(parents=True, exist_ok=True)

    config = dict(cfg.DEFAULT_CONFIG)
    config["llm"]["primary"] = consts.BACKEND_ANTIGRAVITY_CLI
    config["llm"]["antigravity_flash_model"] = "gemini-3.5-flash"
    
    # Marks this vault so production code never auto-selects it via last_root fallback
    config["testbed"] = True
    
    mock_zotero_env = scenario_root / "mock_zotero_env"
    if mock_zotero_env.exists():
        if "external" not in config:
            config["external"] = {"zotero": {"roots": []}}
        if "zotero" not in config["external"]:
            config["external"]["zotero"] = {"roots": []}
        config["external"]["zotero"]["roots"].append(str(mock_zotero_env.resolve()))

    cfg.save_config(paths, config)

    db.init_db(paths.state_db)
    page_writer.rebuild_index(paths, _now_iso())
    return paths

def _write_testbed_agent_rules(root: Path, rules_path: Path) -> None:
    ws_dir = root / consts.DIR_WORKSPACES / WORKSPACE_NAME
    fixture_has_content = rules_path.exists() and any(rules_path.rglob("*"))
    tmpl_root = rules_path if fixture_has_content else None
    for agent in ("antigravity",):
        prepare_workspace(
            vault_root=root,
            workspace=ws_dir,
            agent=agent,
            install_rules=True,
            template_root=tmpl_root,
        )

def create_testbed(scenario_name: str, *, force: bool) -> None:
    scenario_root = REPO_ROOT / "tests" / "scenarios" / scenario_name
    if not scenario_root.exists():
        raise SystemExit(f"Scenario '{scenario_name}' not found under tests/scenarios/")
        
    stage_path = scenario_root / "stage"
    rules_path = scenario_root / "fixture_workspace_rules"

    _prepare_root(TESTBED_ROOT, force=force)
    _ensure_testbed_stage(TESTBED_ROOT, stage_path)
    paths = _init_like_wiki_init(TESTBED_ROOT, scenario_root)
    _write_testbed_agent_rules(paths.root, rules_path)
    print(f"Created testbed at {TESTBED_ROOT} using assets from {scenario_root}")
    
    # Auto-Seeding pipeline execution with Mock LLM
    print("Running auto-seeding pipeline (wiki update) with Mock LLM...")
    import subprocess
    env = os.environ.copy()
    env["VAULT_ROOT"] = "testbed"
    # Force the use of a mock or fast model via env if supported, or rely on the config written above.
    # The config already sets primary to ANTIGRAVITY_CLI, which can mock or run fast.
    subprocess.run([sys.executable, "-m", "curator.cli", "update"], env=env, cwd=str(REPO_ROOT), check=False)
    print("Auto-seeding complete.")

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="testbed_template", help="Scenario name to use (under tests/scenarios/)")
    parser.add_argument("--force", action="store_true", help="Recreate the testbed.")
    args = parser.parse_args()
    create_testbed(scenario_name=args.scenario, force=args.force)

if __name__ == "__main__":
    main()
