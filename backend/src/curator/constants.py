from __future__ import annotations

# Directory constants
DIR_SYSTEM = "00_System"
DIR_WORKSPACES = "01_Workspaces"
DIR_WIKI = "02_Wiki"
DIR_NOTES = "03_Notes"
DIR_RESOURCES = "04_Resources"
DIR_ASSETS = "05_Assets"
DIR_ARCHIVES = "06_Archives"
DIR_QMD = "qmd"

# System Files
FILE_CURATE_YML = "curate.yml"
FILE_CONFIG_YML = "config.yml"
FILE_QMD_YML = "qmd.yml"
FILE_INDEX_YML = "index.yml"
FILE_OVERVIEW_MD = "overview.md"
FILE_LEDGER_MD = "ledger.md"
FILE_LOG_MD = "log.md"
FILE_INDEX_MD = "index.md"
FILE_DASHBOARD_MD = "dashboard.md"
FILE_DISMISSED_CONTRADICTIONS = "contradiction_dismissed.json"
FILE_LAST_ROOT = "last_root"
FILE_QMD_INDEX_SQLITE = "index.sqlite"
FILE_AGENTS_MD = "AGENTS.md"
FILE_CLAUDE_MD = "CLAUDE.md"
FILE_ZOTERO_SQLITE = "zotero.sqlite"
FILE_ZOTERO_PREFS = "prefs.js"

# Layer directories
LAYER_L1 = "01_Contexts"
LAYER_L2 = "02_Atoms"
LAYER_L3 = "03_Concepts"
LAYER_L4 = "04_Exhibitions"
# Shared corpus-wide synthesis layer (v0.3.1 L4 Synthesis; SCHEMA §15).
LAYER_SYN = "04_Synthesis"

# Layer Types
TYPE_L1 = "context"
TYPE_L2 = "atom"
TYPE_L3 = "concept"
TYPE_L4 = "exhibition"
TYPE_SYN = "synthesis"

# Node prefixes
PREFIX_L1 = "CTX"
PREFIX_L2 = "ATM"
PREFIX_L3 = "CON"
PREFIX_L4 = "EXH"
PREFIX_SYN = "SYN"

# Claim & Domain Types
CLAIM_TYPE_FACT = "fact"
DOMAIN_GENERAL = "general"

# Database & State
INTERNAL_DIR = ".curator"
STATE_DB = "state.sqlite"
INDEX_FILE = "index.md"
OVERVIEW_FILE = "overview.md"
LOG_FILE = "log.md"
LEDGER_FILE = "ledger.md"
CONFIG_FILE = "config.yml"
STAGING_DIR = ".curator/staging"
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
PHASE_L4 = "l4_exhibitions"

# Default Configs
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"
DEFAULT_TIMEOUT = 120.0

DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"
DEFAULT_CODEX_MODEL = "gpt-5.5"
DEFAULT_ANTIGRAVITY_MODEL = "gemini-3.5-flash"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"

# Default reasoning/effort levels per CLI backend. Empty = let the CLI use its
# own default. These map to: claude `--effort`, codex `-c model_reasoning_effort`,
# and an embedded prompt hint for the agy (Antigravity) CLI.
DEFAULT_CLAUDE_EFFORT = "medium"
DEFAULT_CODEX_EFFORT = "medium"
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
