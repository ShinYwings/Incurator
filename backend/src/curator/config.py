"""Path constants and config loading for an incurator Curator project.

The Curator (Compiler) is a background abstraction engine that:
  1. Monitors source dirs (02_Wiki, 03_Notes, 04_Resources) for changes
  2. Registers sources and builds L1-L3 layers during `wiki add`
  3. Synthesizes L4 Exhibitions via `wiki curate`

All Curator state lives exclusively in `.curator/`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from . import constants as consts

# ---------------------------------------------------------------------------
# Defaults (used when no config.yml has been written yet)
# ---------------------------------------------------------------------------

# Source directories the Curator monitors (READ-ONLY).
# Ordered by epistemic authority: 03_Notes (human verified) > 02_Wiki > rest.
DEFAULT_RAW_DIRS = [consts.DIR_WIKI, consts.DIR_NOTES, consts.DIR_RESOURCES]

# Obsidian vault top-level directories (README.md topology §2)
VAULT_TOPOLOGY = (
    consts.DIR_SYSTEM,
    consts.DIR_WORKSPACES,
    consts.DIR_WIKI,
    consts.DIR_NOTES,
    consts.DIR_RESOURCES,
    consts.DIR_ASSETS,
    consts.DIR_ARCHIVES,
)

# L1-L4 subdirectories under Collections/
COLLECTION_LAYERS = (
    consts.LAYER_L1,
    consts.LAYER_L2,
    consts.LAYER_L3,
    consts.LAYER_L4,
)



@dataclass
class WikiPaths:
    """Resolved absolute paths for a Curator project.

    ``raw_dirs_override`` and ``collections_dir_override`` allow per-project
    customisation via ``config.yml`` (written during ``wiki init``).
    """

    root: Path
    raw_dirs_override: Optional[list[str]] = field(default=None)
    collections_dir_override: Optional[str] = field(default=None)

    # ------------------------------------------------------------------
    # Source (read-only) directories
    # ------------------------------------------------------------------

    @property
    def raw_dirs(self) -> list[Path]:
        dirs = self.raw_dirs_override or DEFAULT_RAW_DIRS
        return [self.root / d for d in dirs]

    # ------------------------------------------------------------------
    # Curator internal paths
    # ------------------------------------------------------------------

    @property
    def internal(self) -> Path:
        """The hidden `.curator/` directory."""
        return self.root / consts.INTERNAL_DIR

    @property
    def collections(self) -> Path:
        """`.curator/Collections/` — the DAG knowledge lake."""
        return self.root / (self.collections_dir_override or consts.DEFAULT_COLLECTIONS_DIR)

    @property
    def staging(self) -> Path:
        """`.curator/staging/` — transient files for background ingest jobs."""
        return self.root / consts.STAGING_DIR

    # Backward-compatible alias so existing callers of `paths.wiki` still work
    @property
    def wiki(self) -> Path:
        return self.collections

    # ------------------------------------------------------------------
    # Layer paths
    # ------------------------------------------------------------------

    @property
    def contexts(self) -> Path:
        """L1: `.curator/Collections/01_Contexts/`"""
        return self.collections / consts.LAYER_L1

    @property
    def atoms(self) -> Path:
        """L2: `.curator/Collections/02_Atoms/`"""
        return self.collections / consts.LAYER_L2

    @property
    def concepts(self) -> Path:
        """L3: `.curator/Collections/03_Concepts/`"""
        return self.collections / consts.LAYER_L3

    @property
    def exhibitions(self) -> Path:
        """L4: `.curator/Collections/04_Exhibitions/`"""
        return self.collections / consts.LAYER_L4

    # ------------------------------------------------------------------
    # Control-plane routing files
    # ------------------------------------------------------------------

    @property
    def overview(self) -> Path:
        """Top-level domain manifest."""
        return self.internal / consts.OVERVIEW_FILE

    @property
    def index(self) -> Path:
        """DAG routing table."""
        return self.internal / consts.INDEX_FILE

    @property
    def log(self) -> Path:
        """Append-only system event log."""
        return self.internal / consts.LOG_FILE

    @property
    def ledger(self) -> Path:
        """HITL correction record."""
        return self.internal / consts.LEDGER_FILE

    @property
    def config_file(self) -> Path:
        """`.curator/config.yml`"""
        return self.internal / consts.CONFIG_FILE

    @property
    def state_db(self) -> Path:
        """SQLite metadata & provenance DB."""
        return self.internal / consts.STATE_DB



    # ------------------------------------------------------------------
    # QMD search-engine state — kept inside the project so it travels with
    # the vault and stays isolated from any global ~/.config/qmd index.
    # ------------------------------------------------------------------

    @property
    def qmd_dir(self) -> Path:
        """`.curator/qmd/` — qmd config + sqlite index for this project."""
        return self.internal / consts.DIR_QMD

    @property
    def qmd_config_file(self) -> Path:
        """qmd's per-project YAML config (collection definitions + contexts)."""
        return self.qmd_dir / consts.FILE_INDEX_YML

    @property
    def qmd_db(self) -> Path:
        """qmd's per-project sqlite index."""
        return self.qmd_dir / consts.FILE_QMD_INDEX_SQLITE

    # ------------------------------------------------------------------

    def is_initialized(self) -> bool:
        """A folder counts as initialized if its config file exists."""
        return self.config_file.exists()


# ---------------------------------------------------------------------------
# Default config (written on ``wiki init``)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict = {
    "version": 2,
    "paths": {
        "raw_dirs": DEFAULT_RAW_DIRS,
        "collections_dir": consts.DEFAULT_COLLECTIONS_DIR,
    },
    "llm": {
        # 'provider::model' format — both primary and fallback encode provider + model together
        "primary":  f"{consts.BACKEND_ANTIGRAVITY_CLI}::{consts.DEFAULT_ANTIGRAVITY_MODEL}",
        "fallback": "",
        # Reasoning/effort level per slot (claude --effort, codex
        # model_reasoning_effort, agy prompt hint). Empty = CLI default.
        "primary_effort":  "",
        "fallback_effort": "",
        "temperature": 0.3,
        "instant_l1": True,
        "probe_interval": 60,
        # ollama only needs connection settings (model lives in primary/fallback value)
        consts.BACKEND_OLLAMA: {
            "host":    consts.DEFAULT_OLLAMA_HOST,
            "timeout": consts.DEFAULT_TIMEOUT,
        },
    },
    "search": {
        "backend": "qmd",
        "rerank": True,
    },
    "external": {
        # Machine-local roots used to rediscover reference-mode files that move
        # outside the vault. Store real Zotero/iCloud paths in the global
        # config file, not in the synced vault config.
        "roots": [],
        "zotero": {
            "enabled": True,
            "roots": [],
        },
    },
    "sync": {
        "max_parallel_verifications": 4,  # threads for Mode C Phase 1; 0 = sequential
    },
    "curate": {
        "interactive": True,
        "auto_update_index": True,
        "auto_update_log": True,
        "log_retention_days": 30,
    },
    "persona": {
        "area": "STEM",
        "text": (
            "Scientific and technical research vault.\n"
            "Focus on formal derivability, mathematical rigor, and algorithmic correctness."
        ),
        "knowledge_artifacts": ["equations", "algorithms", "research papers", "experimental results"],
        "verification_philosophy": "mathematical derivability and citation-based evidence",
        "exhibition_intent": "knowledge-worker",
        "confidence": {
            "high_threshold": 0.85,
            "low_threshold": 0.55,
        },
        "disambiguation_keywords": ["Architecture", "Optimization", "Algorithm", "Theory", "Implementation"],
        "updated_at": "",
    },
}


def split_provider_model(value: str) -> tuple[str, str]:
    """Split 'provider::model' → (provider, model). Model may be empty."""
    provider, _, model = value.partition("::")
    return provider.strip(), model.strip()


def join_provider_model(provider: str, model: str) -> str:
    """Build 'provider::model'. Returns just provider when model is empty."""
    return f"{provider}::{model}" if model else provider


def get_curator_persona(config: dict) -> dict:
    """Return the Curator (vault-level) persona dict, falling back to DEFAULT_CONFIG persona."""
    return config.get("persona") or DEFAULT_CONFIG["persona"]


def get_global_config_dir() -> Path:
    """Get cross-platform global config directory for macOS and Linux."""
    import sys
    import os
    # If XDG_CONFIG_HOME is set, respect it
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "curator"

    # macOS specific standard path fallback
    if sys.platform == "darwin":
        mac_path = Path.home() / "Library" / "Application Support" / "curator"
        linux_fallback = Path.home() / ".config" / "curator"
        # If macOS path exists, or Linux path doesn't exist, use macOS path
        if mac_path.exists() or not linux_fallback.exists():
            return mac_path
        return linux_fallback

    # Linux fallback
    return Path.home() / ".config" / "curator"


def get_last_root() -> Optional[Path]:
    """Get the last active project root from the dedicated last_root file."""
    last_root_file = get_global_config_dir() / consts.FILE_LAST_ROOT
    if last_root_file.exists():
        try:
            val = last_root_file.read_text(encoding="utf-8").strip()
            if val:
                return Path(val).resolve()
        except Exception:
            pass
    return None


def set_last_root(root: Path) -> None:
    """Save the last active project root in the dedicated last_root file."""
    try:
        cache_dir = get_global_config_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / consts.FILE_LAST_ROOT).write_text(str(root.resolve()), encoding="utf-8")
    except Exception:
        pass


def load_config(paths: WikiPaths) -> dict:
    """Load the Curator's config.yml, falling back to defaults for missing keys."""
    import copy

    merged = copy.deepcopy(DEFAULT_CONFIG)

    # 1. Load from global config file if it exists
    global_cfg_file = get_global_config_dir() / consts.FILE_CONFIG_YML
    if global_cfg_file.exists():
        try:
            with global_cfg_file.open("r", encoding="utf-8") as f:
                global_loaded = yaml.safe_load(f) or {}
            for key, val in global_loaded.items():
                if isinstance(val, dict) and isinstance(merged.get(key), dict):
                    merged[key] = {**merged[key], **val}
                else:
                    merged[key] = val
        except yaml.YAMLError as e:
            import logging
            logging.getLogger(__name__).warning(
                "Global config '%s' has invalid YAML — using defaults. Error: %s",
                global_cfg_file, e,
            )
        except Exception:
            pass

    # 2. Merge with the local project's config file
    if paths.config_file.exists():
        try:
            with paths.config_file.open("r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            for key, val in loaded.items():
                if isinstance(val, dict) and isinstance(merged.get(key), dict):
                    merged[key] = {**merged[key], **val}
                else:
                    merged[key] = val
        except yaml.YAMLError as e:
            import logging
            logging.getLogger(__name__).warning(
                "Vault config '%s' has invalid YAML — using defaults. Error: %s",
                paths.config_file, e,
            )
        except Exception:
            pass

    _migrate_llm_config(merged)
    return merged


def _migrate_llm_config(config: dict) -> None:
    """Strip obsolete fields from llm config. No backward compat for old formats."""
    if "llm" not in config or not isinstance(config["llm"], dict):
        return
    llm = config["llm"]
    ollama = llm.setdefault(consts.BACKEND_OLLAMA, {})
    # Remove obsolete keys
    for key in ("vision_model", "remote_ollama_host", "model",
                "antigravity_model", "claude_model", "codex_model",
                consts.BACKEND_ANTIGRAVITY_CLI, consts.BACKEND_CLAUDE_CODE, consts.BACKEND_CODEX_CLI,
                "host", "timeout", "provider", "cloud_provider"):
        llm.pop(key, None)
    for key in ("model", "remote_ollama_host", "vision_model"):
        ollama.pop(key, None)


def paths_from_config(root: Path, config: dict | None = None) -> WikiPaths:
    """Build WikiPaths with any per-project path overrides from config."""
    if config is None:
        wp = WikiPaths(root=root)
        if wp.config_file.exists():
            config = load_config(wp)
        else:
            return wp
    paths_cfg = config.get("paths", {})
    return WikiPaths(
        root=root,
        raw_dirs_override=paths_cfg.get("raw_dirs"),
        collections_dir_override=paths_cfg.get("collections_dir"),
    )


def save_config(paths: WikiPaths, config: dict) -> None:
    """Write config to disk, creating the internal directory if needed."""
    paths.internal.mkdir(parents=True, exist_ok=True)
    with paths.config_file.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False, default_flow_style=False)


def find_wiki_root(start: Path | None = None) -> Path | None:
    """Walk upward from ``start`` looking for a ``.curator/config.yml``.

    Vaults marked with ``testbed: true`` in their config are skipped so that
    development testbeds are never auto-selected for production commands.

    Returns the project root if found, else None.
    """
    import yaml as _yaml
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        cfg_file = candidate / consts.INTERNAL_DIR / consts.CONFIG_FILE
        if cfg_file.exists():
            try:
                data = _yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
                if data.get("testbed"):
                    continue
            except Exception:
                pass
            return candidate
    return None


def find_workspace_curate_yml(vault_root: Path) -> Optional[Path]:
    """Return the curate.yml path from WORKSPACE_PATH env var or vault workspace scan.

    Resolution order:
    1. WORKSPACE_PATH env var (if set and curate.yml exists there)
    2. Single curate.yml found under vault_root/01_Workspaces/ (unambiguous match)
    3. None — caller falls back to unscoped search
    """
    import os
    env_ws = os.environ.get("WORKSPACE_PATH")
    if env_ws:
        candidate = Path(env_ws).expanduser().resolve() / consts.FILE_CURATE_YML
        if candidate.exists():
            return candidate

    # Fallback: scan vault workspaces directory for a single curate.yml
    workspaces_dir = vault_root / consts.DIR_WORKSPACES
    if workspaces_dir.is_dir():
        found = list(workspaces_dir.rglob(consts.FILE_CURATE_YML))
        if len(found) == 1:
            return found[0]

    return None
