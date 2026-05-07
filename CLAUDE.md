# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
Repo-wide agent rules live in `AGENTS.md`; keep this file consistent with that contract.

## Agent Rule Synchronization

`AGENTS.md` is the canonical tool-neutral rule source. `CLAUDE.md`,
`GEMINI.md`, and any future agent/provider-specific instruction files must stay
synchronized with the behavioral and development rules in this file so every
agent follows the same project contract, regardless of whether it is driven by
Claude Code, Gemini CLI, Codex, Ollama, or another provider/runtime.

When editing agent rules:

- Update `AGENTS.md`, `CLAUDE.md`, and `GEMINI.md` in the same change.
- Keep shared rules semantically identical across all agent instruction files.
- If a rule is tool-specific, label it clearly and keep the general contract in
  `AGENTS.md`.
- Treat unsynchronized rule edits as incomplete until every applicable agent
  instruction file is checked.

## Behavioral Guidelines

Behavioral guidelines to reduce common LLM coding mistakes. Merge with
project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial
tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:

- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them; don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes,
simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it; don't delete it.

When your changes create orphans:

- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:

- "Add validation" -> "Write tests for invalid inputs, then make them pass"
- "Fix the bug" -> "Write a test that reproduces it, then make it pass"
- "Refactor X" -> "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```text
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it
work") require constant clarification.

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer
rewrites due to overcomplication, and clarifying questions come before
implementation rather than after mistakes.

## Project Overview

InCurator is an LLM-maintained personal knowledge base (Zettelkasten) integrated with Obsidian. It ingests external sources through a 4-layer curation pipeline (L1 Contexts → L2 Atoms → L3 Concepts → L4 Exhibitions) using a multi-provider LLM backend, building a verifiable cross-linked knowledge graph accessible to both humans and AI agents.

## Development Commands

```bash
# Install (creates venv, installs deps, runs hatch build hook for Node.js)
./install.sh

# Or manually with uv
uv pip install -e ".[dev]"

# Lint / type-check
ruff check src/
mypy src/

# Run tests
pytest

# Run a single test
pytest tests/test_db.py::test_source_deduplication -v

# Build package
hatch build

# Recreate the ignored development validation vault
python scripts/dev/testbed_assets/create_testbed.py --force
```

**CLI entry point** (after install):
```bash
wiki init <path>        # Initialize a Curator vault
wiki add <file>         # Parse source and generate L1 Context
wiki curate             # Run full L2→L3→L4 LLM pipeline
wiki sync               # Verify DAG integrity, rebuild index/ledger
wiki query "<question>" # Search and synthesize answer with citations
wiki reindex            # Rebuild QMD search index
wiki status             # Show config and stats
wiki config provider    # Switch LLM backend
wiki sources list|show|rm  # Manage tracked source files
```

## Architecture

### Data Flow

```
[Source File]
     │  wiki add
     ▼
[ingest_raw.py] — parse via parsers/* → register in db.sources (content-hash dedup)
     │  LLM pass → generate L1
     ▼
[01_Contexts/CTX-<UUID>.md]
     │  wiki curate / Phase A (per-source)
     ▼
[02_Atoms/ATM-<UUID>.md]       ← atomic facts extracted by LLM
     │  Phase B (global clustering)
     ▼
[03_Concepts/CON-<UUID>.md]    ← cross-source thematic groupings
     │  Phase C (global synthesis)
     ▼
[04_Exhibitions/EXH-<UUID>.md] ← terminal context packages for agents
     │
     ├─ wiki query (search.py / QMD + LLM rerank)
     └─ HITL promotion → 02_Wiki/ (becomes new L1 input next cycle)
```

### Key Modules

| Module | Role |
|--------|------|
| `cli.py` | Typer CLI; auto-selects LLM backend by available RAM (<16 GB → Gemini cloud, ≥16 GB → Ollama local) |
| `db.py` | SQLite state (`state.sqlite`): source deduplication (SHA256 hash), ingest run history, source→page provenance |
| `ingest_raw.py` | File discovery, hash-based dedup, parser dispatch, L1 Context generation |
| `ingest_llm.py` | Three-phase DAG construction: Phase A (atoms), Phase B (concepts), Phase C (exhibitions) |
| `sync.py` | DAG integrity verification; Mode A (global reverse L4→L1) and Mode B (targeted bidirectional) |
| `search.py` | Wraps `src/qmd/bin/qmd` binary (BM25 + vector + LLM rerank); builds Obsidian-compatible index |
| `query.py` | Retrieval + LLM synthesis with citation management |
| `llm.py` | Multi-provider clients: `OllamaClient`, `GeminiClient`, `ClaudeClient`, `OpenAIClient`, `FailoverClient` |
| `config.py` | Vault topology, `.curator/config.yml` loading, path resolution |
| `page_writer.py` | Frontmatter parse/write, wikilink extraction, index and log file updates |
| `parsers/` | Normalize PDF, HTML, plain-text, image → `ParsedDocument` |
| `lint.py` | Detects contradictions, orphan nodes, broken wikilinks, malformed frontmatter |
| `mcp_server.py` | MCP server interface (in progress) |

### Vault Structure

```
<vault>/
├── .obsidian/         Obsidian configuration and plugins
├── 00_System/         User-defined folders (e.g., sandbox, inbox, daily, etc.)
├── 01_Workspaces/     [Artist Space] Project-specific studios
│   └── <project_name>/
│       ├── curate.yml     Knowledge Requirement Spec (Required)
│       ├── .agents/       Agent-specific workspace (Auto-generated)
│       └── <notes/scripts>Human artifacts related to this project
├── 02_Wiki/           [Human Space] Human-curated knowledge (promoted from L4)
├── 03_Notes/          [Source] Human notes — READ-ONLY
├── 04_Resources/      [Source] External references — READ-ONLY
├── 05_Assets/         Media assets (images, PDF attachments, etc.)
├── 06_Archives/       Archives for deprecated or old sources
└── .curator/          [Machine Space] Hidden core (managed by wiki CLI)
    ├── config.yml     LLM backend, model, raw_dirs, collections_dir
    ├── state.sqlite   Dedup hashes, run history, provenance
    ├── index.md       DAG routing table (all L1-L4 node IDs)
    ├── overview.md    Domain manifest
    ├── log.md         Append-only event log
    ├── ledger.md      HITL correction record
    └── Collections/
        ├── 01_Contexts/
        ├── 02_Atoms/
        ├── 03_Concepts/
        └── 04_Exhibitions/
```

### Architecture Source Of Truth

When discussing or changing the system architecture, use these areas as the source-of-truth:

- **Static Specs**: `docs/spec/` for system contracts and schemas.
    - `docs/spec/curator_schema/` for Curator DAG schema contracts.
    - `docs/spec/system_behavior/` for Curator system behavior.
- **Dynamic Planning**: `docs/plans/` for implementation context.
    - `docs/plans/update_plan/` for migration and feature implementation plans.

Treat older root-level specs as historical unless the user explicitly points to them for comparison.

## Critical Invariants

- **Node IDs are prefixed UUIDs** (`CTX-`, `ATM-`, `CON-`, `EXH-`), never human slugs. Human-readable titles live in frontmatter only.
- **Pipeline is sequential, not parallel**: Phase B (clustering) must run after all Phase A (atom) outputs are complete, because concepts are cross-source constructs.
- **`03_Notes/` and `06_Archives/` are immutable** from the curator's perspective. Contradictions must be escalated to the human (HITL), never auto-resolved by modifying original notes.
- **`state.sqlite` is the source of truth** for deduplication and provenance — do not bypass `db.py` functions to write pages directly.
- **QMD binary** (`src/qmd/bin/`) is a bundled native binary installed via `scripts/hatch_build.py`, not a Python package. `wiki reindex` must be run after bulk changes before `wiki query` will see new content.
- **LLM backend selection** happens at CLI startup in `cli.py`; downstream code receives a pre-constructed `FailoverClient`. Do not call provider SDKs directly from pipeline modules.

## Testing

Use `/home/shin/Workspace/llm_wiki/testbed` for testbed-driven development against a live vault. For every feature addition, bug fix, removal, migration, or system-rule update, reproduce or validate the scenario in `testbed/` whenever practical, then rerun the same check after the change.

Baseline:

```bash
python scripts/dev/testbed_assets/create_testbed.py --force
WIKI_ROOT=testbed wiki status
WIKI_ROOT=testbed wiki add
WIKI_ROOT=testbed wiki sync
```

When qmd and the configured LLM backend are available, also run `WIKI_ROOT=testbed wiki reindex` and a relevant `wiki query` smoke test.
