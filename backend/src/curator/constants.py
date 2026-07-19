from __future__ import annotations

# Directory constants
DIR_SYSTEM = "00_System"
DIR_WORKSPACES = "01_Workspaces"
DIR_WIKI = "02_Wiki"
DIR_NOTES = "03_Notes"
DIR_RESOURCES = "04_Resources"
DIR_ASSETS = "05_Assets"
DIR_ARCHIVES = "06_Archives"
DIR_GLOBAL_CACHE = ".cache/config"

# System Files
FILE_CURATE_YML = "curate.yml"
FILE_SETTINGS_YML = "settings.yml"
FILE_GLOBAL_CONFIG_YML = "config.yml"
FILE_DEVICES_JSON = "devices.json"
FILE_OVERVIEW_MD = "overview.md"
FILE_LEDGER_MD = "ledger.md"
FILE_LOG_MD = "log.md"
FILE_INDEX_MD = "index.md"
FILE_DASHBOARD_MD = "dashboard.md"
FILE_DISMISSED_CONTRADICTIONS = "contradiction_dismissed.json"
FILE_LAST_ROOT = "last_root"
FILE_AGENTS_MD = "AGENTS.md"
FILE_CLAUDE_MD = "CLAUDE.md"
FILE_ZOTERO_SQLITE = "zotero.sqlite"
FILE_ZOTERO_PREFS = "prefs.js"

# Layer directories (L4 is the shared Synthesis layer)
LAYER_L1 = "01_Contexts"
LAYER_L2 = "02_Atoms"
LAYER_L3 = "03_Concepts"
LAYER_L4 = "04_Synthesis"

# Layer Types
TYPE_L1 = "context"
TYPE_L2 = "atom"
TYPE_L3 = "concept"
TYPE_L4 = "synthesis"

# Node prefixes
PREFIX_L1 = "CTX"
PREFIX_L2 = "ATM"
PREFIX_L3 = "CON"
PREFIX_L4 = "SYN"

# Claim & Domain Types
CLAIM_TYPE_FACT = "fact"
DOMAIN_GENERAL = "general"

# Vault schema version — bump when Collections/*.md or config structure changes
# requiring a `wiki migrate` run on existing vaults.
VAULT_SCHEMA_VERSION = 1

# Database & State
INTERNAL_DIR = ".curator"
STATE_DB = "state.sqlite"
INDEX_FILE = "index.md"
OVERVIEW_FILE = "overview.md"
LOG_FILE = "log.md"
LEDGER_FILE = "ledger.md"
SETTINGS_FILE = "settings.yml"
DEFAULT_COLLECTIONS_DIR = ".curator/Collections"

# Job & Source Statuses
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
STATUS_ERROR = "error"
STATUS_PENDING = "pending"
STATUS_SKIPPED = "skipped"

# Zotero Configs
ZOTERO_PREF_ATTACHMENT = "extensions.zotero.baseAttachmentPath"
ZOTERO_PREF_ZOTMOOV = "extensions.zotmoov.dst_dir"

# Managed Templates
MANAGED_START = "<!-- incurator:start -->"
MANAGED_END = "<!-- incurator:end -->"

# Job Phases
PHASE_L1 = "l1_contexts"
PHASE_L2 = "l2_atoms"
PHASE_L3 = "l3_concepts"
PHASE_L4 = "l4_synthesis"

# Default Configs
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"
DEFAULT_TIMEOUT = 120.0

DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"
DEFAULT_CODEX_MODEL = "gpt-5.6-sol"
DEFAULT_ANTIGRAVITY_MODEL = "gemini-3.5-flash"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"

# v0.3.2 DB-native search providers. Qwen3 0.6B GGUFs are chosen
# to keep embedding + reranking under the local ~2.5 GB VRAM target while using
# one llama-cpp runtime. Ollama remains available as a chat backend and fallback
# embedding profile (e.g. ollama::bge-m3).
DEFAULT_EMBED_PROVIDER = "llama-cpp"
DEFAULT_EMBED_MODEL = "qwen3-embedding-0.6b"
DEFAULT_EMBED_DIM = 1024
# Qwen3 embedding GGUF auto-download source (HuggingFace resolve/main).
DEFAULT_EMBED_GGUF_REPO = "Qwen/Qwen3-Embedding-0.6B-GGUF"
DEFAULT_EMBED_GGUF_FILE = "Qwen3-Embedding-0.6B-Q8_0.gguf"
# Corrected Qwen3 reranker GGUF run locally via llama-cpp-python. Random
# community Qwen3 reranker GGUFs can be broken; this ggml-org artifact is still
# smoke-validated and degrades to `no_rerank` when invalid/unavailable.
DEFAULT_RERANK_PROVIDER = "llama-cpp"
DEFAULT_RERANK_MODEL = "qwen3-reranker-0.6b"
# Reranker GGUF auto-download source (HuggingFace resolve/main). Override via
# config `search.reranker_gguf_repo` / `reranker_gguf_file` if these move or you
# prefer a different quant. `wiki models ensure` downloads this and pins
# `search.reranker_model_path`.
DEFAULT_RERANK_GGUF_REPO = "ggml-org/Qwen3-Reranker-0.6B-Q8_0-GGUF"
DEFAULT_RERANK_GGUF_FILE = "qwen3-reranker-0.6b-q8_0.gguf"

# Default reasoning/effort levels per CLI backend. Empty = let the CLI use its
# own default. These map to: claude `--effort`, codex `-c model_reasoning_effort`,
# and an embedded prompt hint for the agy (Antigravity) CLI.
DEFAULT_CLAUDE_EFFORT = "high"
DEFAULT_CODEX_EFFORT = "low"
DEFAULT_ANTIGRAVITY_EFFORT = "medium"

# LLM Provider Backends
BACKEND_OLLAMA = "ollama"
BACKEND_CLAUDE_CODE = "claude-code"
BACKEND_ANTIGRAVITY_CLI = "antigravity-cli"
BACKEND_CODEX_CLI = "codex-cli"
BACKEND_DEEPSEEK_API = "deepseek-api"
BACKEND_CLOUD = "cloud"

# Cloud Providers

CLOUD_CLAUDE = "claude"
CLOUD_OPENAI = "openai"
CLOUD_ANTIGRAVITY = "antigravity"
CLOUD_DEEPSEEK = "deepseek"

# Workspace Scenarios
SCENARIO_EMPTY = "empty"
SCENARIO_AGENT_ONLY = "agent-only"
SCENARIO_FULL = "full"

# Workspace Agents
AGENT_CODEX = "codex"
AGENT_NONE = "none"

# Model name substrings (lowercase, tag stripped) that guarantee vision support.
VISION_CAPABLE_KEYWORDS: frozenset[str] = frozenset({
    "llava",            # LLaVA base
    "llava-llama3",     # LLaVA Llama 3
    "llava-phi3",       # LLaVA Phi-3
    "bakllava",         # BakLLaVA
    "moondream",        # Moondream 2
    "minicpm-v",        # MiniCPM-V
    "llama3.2-vision",  # Llama 3.2 Vision
    "llama-3.2-vision", # (Keyword variation)
    "pixtral",          # Pixtral 12B
    "mistral-pixtral",  # (Keyword variation)
    
    # (Real-world models that require custom GGUF for llama.cpp, etc.)
    "qwen2-vl",         # Qwen2-VL
    "qwen2.5-vl",       # Qwen2.5-VL
    "cogvlm",           # CogVLM
    "internvl",         # InternVL
    "phi3-vision",      # Phi-3 Vision (usually replaced by llava-phi3)
    "phi-3-vision",
    "deepseek-vl",      # DeepSeek-VL
    "idefics",          # IDEFICS
    "fuyu",             # Fuyu
})
