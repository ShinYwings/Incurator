"""Logic for managing development testbeds within the CLI."""

from __future__ import annotations

import shutil
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from . import config as cfg
from . import db, page_writer
from .workspace.provisioner import prepare_workspace

def get_scenarios_dir() -> Path:
    """Find the scripts/dev directory relative to the package."""
    # REPO_ROOT is 3 levels up from backend/src/curator/testbed_manager.py
    return Path(__file__).resolve().parents[3] / "scripts" / "dev"

def list_scenarios() -> List[str]:
    """List available testbed scenarios in scripts/dev/."""
    dev_dir = get_scenarios_dir()
    if not dev_dir.exists():
        return []
    # A directory is a scenario if it contains a MASTER_PLAN.md
    return [d.name for d in dev_dir.iterdir() if d.is_dir() and (d / "MASTER_PLAN.md").exists()]

def init_testbed(
    scenario_name: str = "testbed_template", 
    force: bool = False,
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
) -> Path:
    """Initialize a testbed vault using a specific scenario."""
    dev_dir = get_scenarios_dir()
    scenario_dir = dev_dir / scenario_name
    if not scenario_dir.exists():
        raise ValueError(f"Scenario '{scenario_name}' not found in {dev_dir}")

    # Import the scenario's create_testbed function dynamically if needed, 
    # but for standardization, we'll use a common logic here that respects the template structure.
    repo_root = dev_dir.parents[1]
    testbed_root = repo_root / "testbed"
    
    if testbed_root.exists() and not force:
        raise RuntimeError(f"Testbed already exists at {testbed_root}. Use --force to recreate.")

    # Prepare root
    if force and testbed_root.exists():
        shutil.rmtree(testbed_root)
    testbed_root.mkdir(parents=True, exist_ok=True)

    # Seed from stage
    stage_dir = scenario_dir / "stage"
    if stage_dir.exists():
        shutil.copytree(stage_dir, testbed_root, dirs_exist_ok=True)

    # Standard initialization
    (testbed_root / ".obsidian").mkdir(parents=True, exist_ok=True)
    for dirname in cfg.VAULT_TOPOLOGY:
        (testbed_root / dirname).mkdir(parents=True, exist_ok=True)

    from . import constants as consts  # noqa: PLC0415 – local import avoids circular ref
    raw_dirs = [consts.DIR_WIKI, consts.DIR_NOTES, consts.DIR_RESOURCES, consts.DIR_ARCHIVES]
    paths = cfg.WikiPaths(root=testbed_root, raw_dirs_override=raw_dirs)
    paths.internal.mkdir(parents=True, exist_ok=True)
    paths.collections.mkdir(parents=True, exist_ok=True)
    for layer in cfg.COLLECTION_LAYERS:
        (paths.collections / layer).mkdir(parents=True, exist_ok=True)
    config = dict(cfg.DEFAULT_CONFIG)
    primary_provider = llm_provider or consts.BACKEND_ANTIGRAVITY_CLI
    model = llm_model or cfg.split_provider_model(cfg.DEFAULT_CONFIG["llm"]["primary"])[1]
    config["llm"]["primary"] = cfg.join_provider_model(primary_provider, model)
    # Marks this vault so production code never auto-selects it via last_root fallback
    config["testbed"] = True
    
    mock_zotero_env = dev_dir / scenario_name / "mock_zotero_env"
    if mock_zotero_env.exists():
        if "external" not in config:
            config["external"] = {"zotero": {"roots": []}}
        if "zotero" not in config["external"]:
            config["external"]["zotero"] = {"roots": []}
        config["external"]["zotero"]["roots"].append(str(mock_zotero_env.resolve()))
        
    cfg.save_config(paths, config)

    db.init_db(paths.state_db)
    page_writer.rebuild_index(paths, datetime.now(timezone.utc).isoformat())

    # Install agent rules
    fixture_rules = scenario_dir / "fixture_workspace_rules"
    fixture_has_content = fixture_rules.exists() and any(fixture_rules.rglob("*"))
    tmpl_root = fixture_rules if fixture_has_content else None
    ws_root = testbed_root / consts.DIR_WORKSPACES
    if ws_root.exists():
        for ws_dir in ws_root.iterdir():
            if ws_dir.is_dir():
                prepare_workspace(
                    vault_root=testbed_root,
                    workspace=ws_dir,
                    agent=consts.CLOUD_ANTIGRAVITY,
                    install_rules=True,
                    template_root=tmpl_root,
                )
    
    return testbed_root
