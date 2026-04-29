"""Path constants and config loading for an LLM-Wiki project.

The key insight: RAW_DIRS and WIKI_DIR are stored *in the config* so each
vault can customise them at init time.  The module-level constants are
just defaults used when no config.yml exists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

# ---------------------------------------------------------------------------
# Defaults (used when no config.yml has been written yet)
# ---------------------------------------------------------------------------

DEFAULT_RAW_DIRS = ["03_Resources", "02_Wiki"]
DEFAULT_WIKI_DIR = ".wiki/distilled"
SCHEMA_DIR = "schema"
INTERNAL_DIR = ".wiki"

WIKI_SUBDIRS = ("Extracted", "Synthesized", "Metadata")

INDEX_FILE = "index.md"
LOG_FILE = "log.md"
AGENTS_FILE = "AGENTS.md"
CONFIG_FILE = "config.yml"
STATE_DB = "state.sqlite"

OBSIDIAN_DIR = ".obsidian"


@dataclass
class WikiPaths:
    """Resolved absolute paths for a wiki project.

    raw_dirs_override and wiki_dir_override allow per-project customisation
    (set via config.yml during ``wiki init``).
    """

    root: Path
    raw_dirs_override: Optional[list[str]] = field(default=None)
    wiki_dir_override: Optional[str] = field(default=None)

    @property
    def raw_dirs(self) -> list[Path]:
        dirs = self.raw_dirs_override or DEFAULT_RAW_DIRS
        return [self.root / d for d in dirs]

    @property
    def wiki(self) -> Path:
        return self.root / (self.wiki_dir_override or DEFAULT_WIKI_DIR)

    @property
    def schema(self) -> Path:
        return self.root / SCHEMA_DIR

    @property
    def internal(self) -> Path:
        return self.root / INTERNAL_DIR

    @property
    def index(self) -> Path:
        return self.wiki / INDEX_FILE

    @property
    def log(self) -> Path:
        return self.wiki / LOG_FILE

    @property
    def agents(self) -> Path:
        return self.schema / AGENTS_FILE

    @property
    def config_file(self) -> Path:
        return self.internal / CONFIG_FILE

    @property
    def state_db(self) -> Path:
        return self.internal / STATE_DB

    @property
    def obsidian(self) -> Path:
        return self.wiki / OBSIDIAN_DIR

    def is_initialized(self) -> bool:
        """A folder counts as initialized if its config file exists."""
        return self.config_file.exists()


# ---------------------------------------------------------------------------
# Default config (written on ``wiki init``)
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict = {
    "version": 1,
    "paths": {
        "raw_dirs": DEFAULT_RAW_DIRS,
        "wiki_dir": DEFAULT_WIKI_DIR,
    },
    "llm": {
        # provider: 'auto' | 'ollama' | 'gemini'
        # 'auto' selects based on system RAM at runtime:
        #   < 16 GB  →  Gemini API
        #   ≥ 16 GB  →  Ollama (deepseek-r1:14b)
        "provider": "auto",
        # --- Ollama settings (used when provider=ollama or RAM ≥ 16 GB) ---
        "model": "deepseek-r1:14b",
        "host": "http://localhost:11434",
        # --- Gemini settings (used when provider=gemini or RAM < 16 GB) ---
        # API key can also be set via GEMINI_API_KEY environment variable
        "gemini_api_key": "",
        "gemini_flash_model": "gemini-3-flash-preview",
        "gemini_think_model": "gemini-3.1-pro-preview",
        # thinking mode — used for Pass 1 extraction (slower but higher quality)
        "temperature": 0.3,
        "thinking": True,
    },
    "search": {
        "backend": "qmd",
        "rerank": True,
    },
    "ingest": {
        "interactive": True,
        "auto_update_index": True,
        "auto_update_log": True,
    },
}


def load_config(paths: WikiPaths) -> dict:
    """Load the wiki's config.yml, falling back to defaults for missing keys."""
    if not paths.config_file.exists():
        return dict(DEFAULT_CONFIG)
    with paths.config_file.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    merged = dict(DEFAULT_CONFIG)
    # Deep-merge top-level dicts
    for key, val in loaded.items():
        if isinstance(val, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **val}
        else:
            merged[key] = val
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
        wiki_dir_override=paths_cfg.get("wiki_dir"),
    )


def save_config(paths: WikiPaths, config: dict) -> None:
    """Write config to disk, creating the internal directory if needed."""
    paths.internal.mkdir(parents=True, exist_ok=True)
    with paths.config_file.open("w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False, default_flow_style=False)


def find_wiki_root(start: Path | None = None) -> Path | None:
    """Walk upward from ``start`` looking for a ``.wiki/config.yml``.

    Returns the project root if found, else None.
    """
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / INTERNAL_DIR / CONFIG_FILE).exists():
            return candidate
    return None
