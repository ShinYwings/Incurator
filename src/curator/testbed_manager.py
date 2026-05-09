"""Logic for managing development testbeds within the CLI."""

from __future__ import annotations

import shutil
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from . import config as cfg
from . import db, page_writer, search
from .workspace.provisioner import prepare_workspace

def get_scenarios_dir() -> Path:
    """Find the scripts/dev directory relative to the package."""
    # REPO_ROOT is 2 levels up from src/curator/testbed_manager.py
    return Path(__file__).resolve().parents[2] / "scripts" / "dev"

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

    raw_dirs = ["02_Wiki", "03_Notes", "04_Resources", "06_Archives"]
    paths = cfg.WikiPaths(root=testbed_root, raw_dirs_override=raw_dirs)
    paths.internal.mkdir(parents=True, exist_ok=True)
    paths.collections.mkdir(parents=True, exist_ok=True)
    for layer in cfg.COLLECTION_LAYERS:
        (paths.collections / layer).mkdir(parents=True, exist_ok=True)

    config = dict(cfg.DEFAULT_CONFIG)
    # Use specified provider or default to gemini-cli for testbeds
    config["llm"]["primary"] = llm_provider or "gemini-cli"
    if llm_model:
        if config["llm"]["primary"] == "ollama":
            config["llm"]["model"] = llm_model
        elif config["llm"]["primary"] == "gemini-cli":
            config["llm"]["gemini_flash_model"] = llm_model
    elif not llm_provider:
        # Default model for the default gemini-cli provider
        config["llm"]["gemini_flash_model"] = "gemini-3.1-flash-lite-preview"
    # Marks this vault so production code never auto-selects it via last_root fallback
    config["testbed"] = True
    cfg.save_config(paths, config)

    db.init_db(paths.state_db)
    page_writer.rebuild_index(paths, datetime.now(timezone.utc).isoformat())
    search.write_qmd_config(paths, overwrite=True)

    # Install agent rules
    fixture_rules = scenario_dir / "fixture_workspace_rules"
    if fixture_rules.exists():
        # Find first workspace in stage
        ws_root = testbed_root / "01_Workspaces"
        if ws_root.exists():
            for ws_dir in ws_root.iterdir():
                if ws_dir.is_dir():
                    prepare_workspace(
                        vault_root=testbed_root,
                        workspace=ws_dir,
                        agent="antigravity",
                        install_rules=True,
                        template_root=fixture_rules,
                    )
    
    return testbed_root
