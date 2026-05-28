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

# ---------------------------------------------------------------------------
# Defaults (used when no config.yml has been written yet)
# ---------------------------------------------------------------------------

# Source directories the Curator monitors (READ-ONLY).
# Ordered by epistemic authority: 03_Notes (human verified) > 02_Wiki > rest.
DEFAULT_RAW_DIRS = ["02_Wiki", "03_Notes", "04_Resources"]

# Curator internal hidden directory
INTERNAL_DIR = ".curator"

# Collections data-plane inside .curator/
DEFAULT_COLLECTIONS_DIR = ".curator/Collections"

# Obsidian vault top-level directories (README.md topology §2)
VAULT_TOPOLOGY = (
    "00_System",       # Scripts & Templates
    "01_Workspaces",   # Active agent projects
    "02_Wiki",         # Shared truth — agent-managed knowledge base
    "03_Notes",        # Human-verified atomic knowledge
    "04_Resources",    # External reference PDFs & Docs (read-only)
    "05_Assets",       # System byproducts (Zotero assets, images)
    "06_Archives",     # Terminated projects & legacy data (read-only)
)

# L1-L4 subdirectories under Collections/
COLLECTION_LAYERS = (
    "01_Contexts",    # L1: 1:1 hash-matched context summaries
    "02_Atoms",       # L2: Irreducible atomic knowledge units
    "03_Concepts",    # L3: High-level conceptual clusters of atoms
    "04_Exhibitions", # L4: Terminal packaged contexts for agents (Artists)
)

# Top-level routing / control-plane files inside .curator/
OVERVIEW_FILE = "overview.md"
INDEX_FILE    = "index.md"
LOG_FILE      = "log.md"
LEDGER_FILE   = "ledger.md"

CONFIG_FILE = "config.yml"
STATE_DB    = "state.sqlite"


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
        return self.root / INTERNAL_DIR

    @property
    def collections(self) -> Path:
        """`.curator/Collections/` — the DAG knowledge lake."""
        return self.root / (self.collections_dir_override or DEFAULT_COLLECTIONS_DIR)

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
        return self.collections / "01_Contexts"

    @property
    def atoms(self) -> Path:
        """L2: `.curator/Collections/02_Atoms/`"""
        return self.collections / "02_Atoms"

    @property
    def concepts(self) -> Path:
        """L3: `.curator/Collections/03_Concepts/`"""
        return self.collections / "03_Concepts"

    @property
    def exhibitions(self) -> Path:
        """L4: `.curator/Collections/04_Exhibitions/`"""
        return self.collections / "04_Exhibitions"

    # ------------------------------------------------------------------
    # Control-plane routing files
    # ------------------------------------------------------------------

    @property
    def overview(self) -> Path:
        return self.internal / OVERVIEW_FILE

    @property
    def index(self) -> Path:
        return self.internal / INDEX_FILE

    @property
    def log(self) -> Path:
        return self.internal / LOG_FILE

    @property
    def ledger(self) -> Path:
        return self.internal / LEDGER_FILE

    # ------------------------------------------------------------------
    # Operational files
    # ------------------------------------------------------------------

    @property
    def config_file(self) -> Path:
        return self.internal / CONFIG_FILE

    @property
    def state_db(self) -> Path:
        return self.internal / STATE_DB

    # ------------------------------------------------------------------
    # QMD search-engine state — kept inside the project so it travels with
    # the vault and stays isolated from any global ~/.config/qmd index.
    # ------------------------------------------------------------------

    @property
    def qmd_dir(self) -> Path:
        """`.curator/qmd/` — qmd config + sqlite index for this project."""
        return self.internal / "qmd"

    @property
    def qmd_config_file(self) -> Path:
        """qmd's per-project YAML config (collection definitions + contexts)."""
        return self.qmd_dir / "index.yml"

    @property
    def qmd_db(self) -> Path:
        """qmd's per-project sqlite index."""
        return self.qmd_dir / "index.sqlite"

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
        "collections_dir": DEFAULT_COLLECTIONS_DIR,
    },
    "llm": {
        # --- Ollama settings ---
        "model": "qwen2.5:7b",
        "host": "http://localhost:11434",
        # --- Gemini settings ---
        "gemini_flash_model": "gemini-3.1-flash-lite-preview",
        "gemini_think_model": "gemini-3.1-pro-preview",
        # thinking mode — used for L2 Fragment extraction (slower, higher quality)
        "temperature": 0.3,
        "thinking": True,
        # primary: 'ollama' | 'cloud' | 'claude-code' | 'gemini-cli' | ''
        #   ''  → legacy auto/provider field takes effect
        "primary": "",
        # fallback: 'ollama' | 'cloud' | 'claude-code' | 'gemini-cli' | ''
        #   explicit failover backend; '' = use legacy hardcoded fallback logic
        "fallback": "",
        # --- Cloud provider selection ---
        # 'gemini' | 'claude' | 'openai'
        "cloud_provider": "gemini",
        # --- Claude settings ---
        "claude_model": "claude-sonnet-4-6",
        "claude_think_model": "claude-opus-4-7",
        # --- OpenAI settings ---
        "openai_model": "gpt-4.1",
        "openai_think_model": "o3",
        # --- Failover / multi-host settings ---
        # Set to remote Ollama URL (e.g. linux server) when running on macOS.
        # FailoverClient([OllamaClient(remote), cloud_client]) is used automatically.
        "remote_ollama_host": "",
        "probe_interval": 60,    # seconds between background probes; 0 = disable
        # --- Vision / image inference ---
        # Ollama model to use for image description. '' = use main model if it
        # supports vision, else skip image inference.
        # Examples: 'gemma4:31b-it', 'gemma3:12b', 'llava:latest', 'qwen2.5-vl:7b'
        "vision_model": "",
    },
    "search": {
        "backend": "qmd",
        "rerank": True,
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
    last_root_file = get_global_config_dir() / "last_root"
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
        (cache_dir / "last_root").write_text(str(root.resolve()), encoding="utf-8")
    except Exception:
        pass


def load_config(paths: WikiPaths) -> dict:
    """Load the Curator's config.yml, falling back to defaults for missing keys."""
    merged = dict(DEFAULT_CONFIG)

    # 1. Load from global config file if it exists
    global_cfg_file = get_global_config_dir() / "config.yml"
    if global_cfg_file.exists():
        try:
            with global_cfg_file.open("r", encoding="utf-8") as f:
                global_loaded = yaml.safe_load(f) or {}
            for key, val in global_loaded.items():
                if isinstance(val, dict) and isinstance(merged.get(key), dict):
                    merged[key] = {**merged[key], **val}
                else:
                    merged[key] = val
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
        except Exception:
            pass

    return merged


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
        cfg_file = candidate / INTERNAL_DIR / CONFIG_FILE
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
    """Return the curate.yml path from WORKSPACE_PATH env var or active workspace.

    Resolution order:
    1. WORKSPACE_PATH env var (if set and curate.yml exists there)
    2. None — caller falls back to unscoped search
    """
    import os
    env_ws = os.environ.get("WORKSPACE_PATH")
    if env_ws:
        candidate = Path(env_ws).expanduser().resolve() / "curate.yml"
        if candidate.exists():
            return candidate
    return None
