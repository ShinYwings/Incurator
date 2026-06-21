"""Path constants and config loading for an incurator Curator project.

The Curator (Compiler) is a background abstraction engine that:
  1. Monitors source dirs (02_Wiki, 03_Notes, 04_Resources) for changes
  2. Registers sources and builds L1-L3 layers during `wiki add`
  3. Synthesizes shared L4 Synthesis via `wiki build`

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
    def synthesis(self) -> Path:
        """L4 Synthesis: `.curator/Collections/04_Synthesis/` (shared corpus-wide)."""
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
    # v0.3.2: search-engine state lives inside `state.sqlite` (FTS5 + vector).
    # The former external search config + sqlite index were removed.
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
        # Vision extraction models (v0.22.0; SYSTEM_BEHAVIOR §26.2a, SCHEMA §2.5).
        # 'provider::model'. Empty = disabled. Decoupled from primary/fallback.
        "vision_model": "",            # heavy full-page model for `add source` ingest
        "latex_extract_model": "",     # light region OCR; empty → vision_model
        "vision_render_dpi": 170,      # PyMuPDF get_pixmap target DPI (~150-200)
        "vision_max_image_px": 1600,   # hard cap on a rendered page's longest edge
        "vision_max_pages_per_run": 300,  # total-spend rail for one `add` run
        # ollama only needs connection settings (model lives in primary/fallback value)
        consts.BACKEND_OLLAMA: {
            "host":    consts.DEFAULT_OLLAMA_HOST,
            "timeout": consts.DEFAULT_TIMEOUT,
        },
        consts.BACKEND_DEEPSEEK_API: {
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
            "timeout": consts.DEFAULT_TIMEOUT,
        },
    },
    "search": {
        # v0.3.2: DB-native hybrid search (FTS5 + chunked vector + RRF + rerank).
        # The native engine is the only supported search backend.
        "backend": "native",
        "rerank": True,
        # Tier-2 LLM query expansion (lex/vec/hyde) on the answer path. Uses the
        # configured chat LLM; fail-safe to deterministic Tier-1 if unavailable.
        "query_expansion": True,
        # Keep LLM expansion/HyDE as a recovery tool by default so strong raw
        # lexical/vector matches are not perturbed by noisy expansion probes.
        "expansion_recovery_only": True,
        "expansion_vector_confidence_floor": 0.35,
        "expansion_min_lex_hits": 5,
        # Optional local GGUF query expander. Empty -> use the
        # configured chat LLM when query_expansion is enabled.
        "query_expander": "",
        "query_expander_model_path": "",
        "embedding": f"{consts.DEFAULT_EMBED_PROVIDER}::{consts.DEFAULT_EMBED_MODEL}",
        "embedding_dim": consts.DEFAULT_EMBED_DIM,
        # Absolute path to the embedding GGUF. Empty → use the host cache
        # populated by `wiki models ensure`, or degrade to FTS5-only.
        "embedding_model_path": "",
        "embedding_gguf_repo": consts.DEFAULT_EMBED_GGUF_REPO,
        "embedding_gguf_file": consts.DEFAULT_EMBED_GGUF_FILE,
        "reranker": f"{consts.DEFAULT_RERANK_PROVIDER}::{consts.DEFAULT_RERANK_MODEL}",
        # Absolute path to the reranker GGUF.
        # Empty → reranker disabled; answer path runs in `no_rerank` degraded mode.
        # `wiki models ensure` downloads the GGUF below and sets this automatically.
        "reranker_model_path": "",
        "reranker_gguf_repo": consts.DEFAULT_RERANK_GGUF_REPO,
        "reranker_gguf_file": consts.DEFAULT_RERANK_GGUF_FILE,
        "chunking": {
            "target_tokens": 256,
            "max_tokens": 384,
            "overlap_tokens": 48,
            "min_tokens": 32,
        },
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
    "auto_sync": {
        # Cross-device knowledge auto-sync over Syncthing (one-writer-per-file).
        # Opt-in: when enabled, mutating CLI commands (add/build/sync/update) write
        # this device's .curator/sync/dev-<id>.jsonl at the end. The plugin and the
        # explicit `wiki db autosync` command work regardless of this flag.
        "enabled": False,
        # Folder under .curator/ holding per-device export files. This folder IS
        # synced by Syncthing; .curator/sync_state.json (local marks) is NOT.
        "dir": "sync",
        # Plugin file-watcher debounce / fallback poll (milliseconds).
        "debounce_ms": 4000,
        "poll_ms": 60000,
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
        "output_intent": "knowledge-worker",
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
    """Get project-local config directory (originally global)."""
    # Force everything to be inside the project's .cache so no byproducts leak into ~
    return Path(__file__).resolve().parents[3] / consts.DIR_GLOBAL_CACHE


def save_global_config(config: dict) -> None:
    """Write config to the global cache config directory, merging with existing."""
    global_dir = get_global_config_dir()
    global_dir.mkdir(parents=True, exist_ok=True)
    config_file = global_dir / consts.FILE_CONFIG_YML

    existing = {}
    if config_file.exists():
        try:
            with config_file.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    existing = data
        except Exception:
            pass

    def merge_dict(a: dict, b: dict) -> dict:
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(a.get(k), dict):
                a[k] = merge_dict(a[k], v)
            else:
                a[k] = v
        return a

    merged = merge_dict(existing, config)
    with config_file.open("w", encoding="utf-8") as f:
        yaml.safe_dump(merged, f, sort_keys=False, default_flow_style=False, allow_unicode=True)


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


MACHINE_LOCAL_CONFIG_KEYS = frozenset({"llm", "search", "external"})


def _migrate_vault_machine_local_to_global(paths: WikiPaths, vault_cfg: dict) -> None:
    """Move machine-local keys from vault config dict to global cache config.

    Modifies ``vault_cfg`` in-place by removing the machine-local keys, and
    rewrites the vault config file without them.  A no-op when the vault config
    contains none of the machine-local keys.
    """
    moved = {k: vault_cfg.pop(k) for k in list(vault_cfg) if k in MACHINE_LOCAL_CONFIG_KEYS}
    if not moved:
        return
    save_global_config(moved)
    paths.internal.mkdir(parents=True, exist_ok=True)
    tmp = paths.config_file.with_name(f".{paths.config_file.name}.tmp")
    tmp.write_text(
        yaml.safe_dump(vault_cfg, sort_keys=False, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    import os as _os
    _os.replace(tmp, paths.config_file)


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
            # Merge entire vault dict first so machine-local values are not lost.
            # Migration only rewrites the file; merged already gets the correct values.
            for key, val in loaded.items():
                if isinstance(val, dict) and isinstance(merged.get(key), dict):
                    merged[key] = {**merged[key], **val}
                else:
                    merged[key] = val
            _migrate_vault_machine_local_to_global(paths, loaded)
        except yaml.YAMLError as e:
            import logging
            logging.getLogger(__name__).warning(
                "Vault config '%s' has invalid YAML — using defaults. Error: %s",
                paths.config_file, e,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Vault config migration failed for '%s' — machine-local keys may remain in vault config: %s",
                paths.config_file, e,
            )

    _migrate_llm_config(merged)
    return merged


def _migrate_llm_config(config: dict) -> None:
    """Strip obsolete fields from llm config. No backward compat for old formats."""
    if "llm" not in config or not isinstance(config["llm"], dict):
        return
    llm = config["llm"]
    ollama = llm.setdefault(consts.BACKEND_OLLAMA, {})
    # Remove obsolete keys. NOTE: `vision_model` is NO LONGER stripped here — it is a
    # canonical top-level llm key as of v0.22.0 (SCHEMA §2.5). Only the legacy
    # *nested* `ollama.vision_model` location is still cleared below.
    for key in ("remote_ollama_host", "model",
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
    """Write config to disk, routing machine-local keys to the global cache.

    Keys in MACHINE_LOCAL_CONFIG_KEYS (llm, search, external) are written to
    the global cache config instead of the synced vault config.  All other
    keys go to .curator/config.yml as before.
    """
    machine_local = {k: v for k, v in config.items() if k in MACHINE_LOCAL_CONFIG_KEYS}
    vault_only = {k: v for k, v in config.items() if k not in MACHINE_LOCAL_CONFIG_KEYS}
    if machine_local:
        save_global_config(machine_local)
    paths.internal.mkdir(parents=True, exist_ok=True)
    with paths.config_file.open("w", encoding="utf-8") as f:
        yaml.safe_dump(vault_only, f, sort_keys=False, default_flow_style=False, allow_unicode=True)


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
