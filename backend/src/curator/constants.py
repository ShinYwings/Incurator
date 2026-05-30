from __future__ import annotations

# Directory constants
DIR_SYSTEM = "00_System"
DIR_WORKSPACES = "01_Workspaces"
DIR_WIKI = "02_Wiki"
DIR_NOTES = "03_Notes"
DIR_RESOURCES = "04_Resources"
DIR_ASSETS = "05_Assets"
DIR_ARCHIVES = "06_Archives"

# System Files
FILE_CURATE_YML = "curate.yml"
FILE_CONFIG_YML = "config.yml"
FILE_QMD_YML = "qmd.yml"
FILE_INDEX_YML = "index.yml"
FILE_OVERVIEW_MD = "overview.md"
FILE_LEDGER_MD = "ledger.md"
FILE_LOG_MD = "log.md"
FILE_INDEX_MD = "index.md"

# Layer directories
LAYER_L1 = "01_Contexts"
LAYER_L2 = "02_Atoms"
LAYER_L3 = "03_Concepts"
LAYER_L4 = "04_Exhibitions"

# Layer Types
TYPE_L1 = "context"
TYPE_L2 = "atom"
TYPE_L3 = "concept"
TYPE_L4 = "exhibition"

# Node prefixes
PREFIX_L1 = "CTX"
PREFIX_L2 = "ATM"
PREFIX_L3 = "CON"
PREFIX_L4 = "EXH"

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

# LLM Provider Backends
BACKEND_OLLAMA = "ollama"
BACKEND_CLAUDE_CODE = "claude-code"
BACKEND_ANTIGRAVITY_CLI = "antigravity-cli"
BACKEND_CODEX_CLI = "codex-cli"
BACKEND_CLOUD = "cloud"

# Cloud Providers
CLOUD_GEMINI = "gemini"
CLOUD_CLAUDE = "claude"
CLOUD_OPENAI = "openai"
CLOUD_ANTIGRAVITY = "antigravity"

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
