# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.
Repo-wide agent rules live in `AGENTS.md`; keep this file consistent with that contract.

## Agent Rule Synchronization

`AGENTS.md` is the canonical tool-neutral rule source. `CLAUDE.md`
and any future agent/provider-specific instruction files must stay
synchronized with the behavioral and development rules in this file so every
agent follows the same project contract, regardless of whether it is driven by
Claude Code, Antigravity, Codex, Ollama, or another provider/runtime.

When editing agent rules:

- Update `AGENTS.md` and `CLAUDE.md` in the same change.
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

### 2. Investigate User Workspace Before Proposing Solutions

**Never assume you know the user's workflow or project structure without checking.**

- Always use `grep_search`, `find`, or examine configuration files (e.g., `data.json`, `.obsidian/plugins`, etc.) to understand the user's current setup.
- If the user relies on a third-party plugin or specific templates, locate them in the filesystem and read how they are configured before proposing changes.
- Avoid phrases like "you should" or making assumptions about their taxonomy (like "books vs papers"). Look at their actual folder structure first.
- Tailor your architectural plans to exactly match what the user is already doing in their vault/workspace.

### 3. Simplicity First

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

### 5. Environment Integrity

**Always revert testbed-specific changes. Production paths are sacred.**

- If you temporarily point `VAULT_ROOT` or `vault_root` to `testbed/` for validation, you MUST revert it to the original production path (e.g., `second_brain`) before ending the turn.
- Do not leave configuration files in a "test" state.
- If you change a path for debugging, double-check that it is restored to the user's workspace context.

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer
rewrites due to overcomplication, and clarifying questions come before
implementation rather than after mistakes.

### 6. Anti-Compression & Detail Preservation (Antigravity Specific)

**Note: This rule specifically mitigates an Antigravity length-matching bias, but serves as a general reminder for all agents.**

**Never perform "lossy compression" on documentation. Do not artificially bound your output length.**

When editing existing files (especially specs, plans, and research notes):
- **Break the Length Limit**: If you add new concepts to a 100-line file, expand it to 150 or 200 lines. DO NOT summarize the original 100 lines into 50 lines to fit the new content.
- **Additive Editing**: Treat existing architectural details as sacred. Add new sections at the bottom or expand existing ones. Never replace detailed paragraphs with bulleted summaries.
- **Extreme Detail**: When explaining logic or architecture, write exhaustively. Do not use abstract buzzwords to compress complex mechanisms.

## Project Overview

Incurator is an LLM-maintained personal knowledge base (Zettelkasten) integrated with Obsidian. It ingests external sources through a 4-layer curation pipeline (L1 Contexts → L2 Atoms → L3 Concepts → L4 Exhibitions) using a multi-provider LLM backend, building a verifiable cross-linked knowledge graph accessible to both humans and AI agents.

## Core Rule: Documentation & Test Mandate

**Every code change must have matching documentation and test coverage. Skipping either is incomplete work.**

### Documentation Requirements

- If you add or change behavior, find every doc file that describes that behavior and update it.
- If no doc exists for the changed behavior, create one (or add a section to the closest guide in `docs/guides/`).
- Implementation and docs must always be in sync. A PR that changes code without updating docs is not done.
- This applies to: CLI commands, MCP tools, plugin features, config fields, env vars, and workflow behaviors.
- For paired English/Korean guides, edit the English guide first as the source text, then update the matching `_KR.md` guide as a faithful translation. Do not use the Korean guide as the canonical source for new behavior.
- If a `_KR.md` guide changes, the matching English guide must change in the same commit unless the edit is Korean-only wording with no behavioral meaning.

Concrete examples:

- Adding a new MCP tool → update `docs/guides/MCP_USER_GUIDE.md` first, then `docs/guides/MCP_USER_GUIDE_KR.md`
- Changing how `wiki init` works → update `docs/guides/USER_GUIDE.md` / `docs/guides/WORKFLOW_GUIDE.md` first, then their `_KR.md` counterparts
- Adding a plugin setting → update `docs/guides/PLUGIN_GUIDE.md` first, then `docs/guides/PLUGIN_GUIDE_KR.md`
- Changing `.stignore` behavior → update `docs/guides/SYNC_IGNORE_GUIDE.md` first, then `docs/guides/SYNC_IGNORE_GUIDE_KR.md`

### Test Requirements

- Backend changes (Python): write or update a `pytest` test in `backend/tests/`.
- Plugin changes (TypeScript): write or update a `.test.ts` test.
- CLI and MCP changes must pass testbed smoke validation (`VAULT_ROOT=testbed wiki <command>`).
- Do not mark a task complete until tests pass and docs are updated.
- If a test is impossible due to a known blocker (LLM unavailable, external dependency), document the gap explicitly.

---

## Core Rule: Automatic /goal Workflow Mandate

**GLOBAL PRIORITY RULE**: Before starting any `/goal` or architectural planning, agents MUST check `.agents/user_report.md`. If there are unresolved bugs or pending items in the user report, you MUST prioritize fixing those first. Only proceed with architectural planning if the user report is empty or explicitly overridden by the user.

## Core Rule: System Update Workflow (Universal Strict Workflow)

**GLOBAL PRIORITY RULE**: Before starting any `/goal` or architectural planning, agents MUST check `.agents/user_report.md`. If there are unresolved bugs or pending items in the user report, you MUST prioritize grouping and fixing those first.
**BLOCKED ICEBOX EXCEPTION**: If an item in `user_report.md` is waiting on an external dependency or cannot be fixed immediately, move it to a `🧊 Blocked / Icebox` section within the file. The Global Priority Rule explicitly IGNORES items in this section.
**HOTFIX EXCEPTION**: If a critical bug is reported while a large Batch Release (e.g., `v0.4.0`) is already being planned or worked on, the agent MUST immediately create a separate `hotfix/...` branch, patch the bug (`+0.0.1`), and open a PR. Do not delay hotfixes by bundling them into ongoing major/minor batch plans.

Whenever a user requests a new feature, reports a bug, or uses the `/goal` command, the agent MUST automatically follow this strict 12-step `Universal Strict Workflow`:

1. **Batch & Version Planning**: Read `.agents/user_report.md` (ignoring Blocked items) and group related items into a single Batch Release. Cross-reference each candidate item against `.agents/plans/` roadmap skeletons to understand which milestone it belongs to. Decide whether this batch warrants a Patch, Minor, or Major version bump. **CRITICAL**: If the update is Minor/Major and includes breaking schema changes, you MUST plan and write a data migration script.
2. **Branch Creation**: Create and switch to a new Git branch for the release (e.g., `release/v0.3.3` or `feature/issue-name`). NEVER work directly on the `main` branch. You MUST update `.agents/relay.md` with the current branch name so other agents know where they are.
3. **Plan Creation & Report Status Update**: Write a detailed implementation plan in `.agents/plans/` using the `.agents/plans/PLAN_TEMPLATE.md` blueprint. **CRITICAL**: As soon as the plan is drafted, you MUST update `.agents/user_report.md` by moving the target item from the `To-Do` section to the `Planned` section to reflect its active state. If there are ambiguities, explicitly ask the user clarifying questions before proceeding. **STOP** and wait for user approval before coding.
4. **Docs Update**: Update `docs/specs/` and `docs/guides/` to define the target behavior. (Crucial: Update the English guides first, then faithfully synchronize the matching `_KR.md` Korean guides).
5. **Test-Driven Development (TDD)**: Write failing tests before writing application logic.
6. **Implementation & Incremental Commits**: Write code to make tests pass. Commit work incrementally using Conventional Commits (e.g., `feat(core): ...`, `fix(plugin): ...`).
7. **Local CI Validation**: Before finalizing, you MUST run all local checks: `uv run pytest`, `ruff check`, `mypy`, and the plugin's `npx vitest run`. Ensure the entire system is intact.
8. **Report Cleanup**: Once an item is verified, **delete** it from `.agents/user_report.md`.
9. **Version Bump & Changelog**: Update the version strings in all relevant configuration files (`pyproject.toml`, `package.json`, `manifest.json`) AND update `CHANGELOG.md` with the release notes for this version.
10. **Plan Deletion**: **Delete** the implemented plan file(s) from the workspace. The plan's historical context will be statically preserved in the Git history for this version.
11. **Release Commit**: Create a final release commit explicitly named `chore(release): vX.Y.Z`.
12. **Push & PR**: Push the branch to the remote repository. Create a GitHub Pull Request that includes a detailed PR Description (Why, What, How) linking back to the resolved items. Wait for the user to review and merge it into `main`.

---

## Core Rule: Cross-Agent Relay Protocol

To prevent context fragmentation and hallucinations when switching between AI coding agents (Antigravity, Claude Code, Cursor/Codex), all agents MUST adhere to the following protocol:

- **On Wakeup**: **CRITICAL INSTRUCTION FOR ALL AGENTS (CODEX, CLAUDE, ANTIGRAVITY)**. At the start of EVERY new conversation or session, the VERY FIRST ACTION you must take is to check if `.agents/relay.md` exists. If it does, you MUST read it in its entirety before taking ANY other action. Do NOT wait for the user to explicitly ask you to "resume work" or "read relay.md". If you fail to do this, you will cause severe context loss and code corruption.
- **Update Frequency**: 
  - Agents MUST update `.agents/relay.md` at the **end of every session** (before stopping execution).
  - Agents MUST always keep `.agents/relay.md` updated during a `/goal` or when an implementation plan is active.
- **Format & Behavior**: 
  - **For Main Architecture Tasks / Goals**: Overwrite `.agents/relay.md` entirely using the standard template (Goal, Plan Reference, Analysis & Reasoning, Progress Status, Critical Context/Blockers, Immediate Next Action). Maintain a single active state for the core task.
  - **For Bug Fixes / Side-Tasks (Antigravity Only)**: When Antigravity is assigned side-tasks or bug fixes, it must NOT overwrite the main relay state. Instead, **APPEND** a new section (e.g., `### Update (YYYY-MM-DD)`) at the bottom of `.agents/relay.md` summarizing what was investigated, fixed, or modified. This ensures the primary agent's context is not destroyed by small interventions.

---

## Core Rule: Testbed-Driven Development

All feature additions, bug fixes, migrations, and system rule changes must be validated in the `testbed/` vault which simulates a real environment. 

### Testbed Scenario Management
The standard scenario template for development and validation is located at `tests/scenarios/`. 
Each scenario is contained in its own folder (e.g., `tests/scenarios/testbed_template/`).
Agents should refer to the specific scenario's `MASTER_PLAN.md` to understand the domain and validation goals.

- **Standard Template**: `tests/scenarios/testbed_template/` is the blueprint for creating new scenarios, but it is rarely the active one.
- **Scenario Discovery**: Because developers often use custom, `.gitignore`d scenario folders, the agent MUST first identify or ask the USER which scenario folder under `tests/scenarios/` is currently active. Do not blindly default to `testbed_template`.
- **Initialization Requirement**: If the `testbed/` directory does not exist, the agent MUST initialize it using the active scenario's name (`wiki testbed init <scenario_name>`). If the USER explicitly refuses, the agent may skip testbed validation but must report the risk of unverified changes.
- **Before Action**: Before changing behavior, reproduce or describe the failing scenario using `testbed/` or the active scenario assets.
- **After Action**: After changing behavior, run the same scenario again and report the result.
- **External Reference Validation**: Any testbed validation must explicitly consider and verify the behavior of Zotero or other external resource directories imported via Reference Mode (without hard copying files into the vault).
- **Blockers**: If a dependency is unavailable, report the exact blocker and run every lower-level validation that does not need that dependency.
- **Completion Criteria**: Do not treat a query/search change as complete until it has been checked with the testbed, or until the qmd/LLM blocker is documented.

## Development Commands

```bash
# Install backend, qmd dependencies, and plugin dependencies
./setup.sh

# Or manually with uv
cd backend
uv pip install -e ".[dev]"

# Lint / type-check
ruff check backend/src/
mypy backend/src/

# Run tests
pytest

# Run a single test
pytest backend/tests/test_db.py::test_source_deduplication -v

# Build package
cd backend
hatch build

# Recreate the ignored development validation vault
# Optional: --llm <provider> --model <model_name>
wiki testbed init <scenario_name> --force
VAULT_ROOT=testbed wiki status
VAULT_ROOT=testbed wiki add
VAULT_ROOT=testbed wiki sync
VAULT_ROOT=testbed wiki lint
```

**CLI entry point** (after install):
```bash
wiki init <path>        # Initialize a Curator vault
wiki update             # One-shot pipeline: add → build → embed → sync
wiki add <file>         # Parse source and generate L1-L3 layers
wiki curate             # Stage L4 Exhibitions for workspace
wiki sync               # Verify DAG integrity, rebuild index/ledger
wiki lint               # Health check: broken links, orphans, contradictions
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
     │  LLM pass → generate L1-L3
     ▼
[01_Contexts/CTX-<UUID>.md]
[02_Atoms/ATM-<UUID>.md]       ← atomic facts extracted by LLM
[03_Concepts/CON-<UUID>.md]    ← cross-source thematic groupings
     │
     │  wiki curate (workspace scoped)
     ▼
[04_Exhibitions/EXH-<UUID>.md] ← terminal context packages for agents
     │
     ├─ wiki query (search.py / QMD + LLM rerank)
     └─ HITL promotion → 02_Wiki/ (becomes new L1 input next cycle)
```

### Key Modules

| Module | Role |
|--------|------|
| `cli.py` | Typer CLI; auto-selects LLM backend by available RAM (<16 GB → Antigravity cloud, ≥16 GB → Ollama local) |
| `db.py` | SQLite state (`state.sqlite`): source deduplication (SHA256 hash), ingest run history, source→page provenance |
| `ingest_raw.py` | File discovery, hash-based dedup, parser dispatch, L1 Context generation |
| `ingest_llm.py` | Three-phase DAG construction: Phase A (atoms), Phase B (concepts), Phase C (exhibitions) |
| `sync.py` | DAG integrity verification; Mode A (global reverse L4→L1) and Mode B (targeted bidirectional) |
| `search.py` | Wraps the globally installed `qmd` binary (BM25 + vector + LLM rerank); builds Obsidian-compatible index |
| `query.py` | Retrieval + LLM synthesis with citation management |
| `llm.py` | Multi-provider clients: `OllamaClient`, `AntigravityClient`, `ClaudeClient`, `OpenAIClient`, `FailoverClient` |
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

The **entire `docs/` tree is source of truth**. The system design becomes increasingly concrete across three distinct levels of documentation. Agents must read the relevant docs before implementing or changing behavior, and respect this hierarchy:

1. **Philosophy (`docs/philosophy/`)**: The abstract intent and high-level principles of the system.
2. **User Guides (`docs/guides/`)**: The concrete user-facing behavior and operational workflows.
    - Guides are authoritative for CLI commands, MCP tools, plugin features, config fields, env vars, and workflow behaviors.
3. **Static Specs (`docs/specs/`)**: The absolute concrete implementation details, system contracts, and schemas.
    - `docs/specs/curator_schema/` for Curator DAG schema contracts.
    - `docs/specs/system_behavior/` for Curator system behavior.
    - `docs/specs/plugin_schema/` for Obsidian plugin API contracts.

When they conflict, the more concrete layer (spec) dictates the implementation reality, but any divergence means both are wrong until reconciled. Do not treat guides as subordinate to specs — fix both together.

**Dynamic Planning**: `.agents/plans/` for implementation sequencing and context.
- **CRITICAL RULE - PLAN TEMPLATE MANDATE**: When creating architectural or feature implementation plans, all agents (Codex, Claude, Antigravity) MUST FIRST read `.agents/plans/PLAN_TEMPLATE.md` and strictly copy/adhere to its Markdown skeleton. You MUST write your final plan artifacts into `.agents/plans/` (instead of default temporary directories).
- **Three mandatory documents** (per PLAN_TEMPLATE.md) before any code is written:
  1. **Domain Analysis docs** (`A_*.md`, `B_*.md`, …) — one per major component. Each must cover: design constraints from codebase, docs/specs invariants, alternatives & trade-offs, final decision, and implementation pseudocode/SQL.
  2. **Master Implementation Plan** (`[XX]_[feature].md`) — locked design decisions, contracts preserved, multi-agent role reviews, and strict phases (`P1 → P2 → …`). Each phase must pass `pytest` + `ruff` before the next begins.
  3. **Evidence Ledger** (`[XX]_roadmap_evidence.md`) — created immediately before coding starts. Records rollback anchor, current schema reality, and pre/post validation results.
- The skeleton plan files in `.agents/plans/` (e.g., `02_stabilization.md`, `03_knowledge_sync_bridge.md`) are **scope notes only**, not implementation plans. They must be replaced or accompanied by the full three-document set before implementation begins.
- To read historical plans, you MUST use `git show` or `git log` on the `.agents/plans/` directory, as completed plans are deleted from the active workspace.
- Plans describe *how* to implement; specs describe *what* to implement.
  When they conflict, specs and guides win over plans.

Treat older root-level specs as historical unless the user explicitly points to them for comparison.

### Docs-First Development

Before implementing any behavior change, the agent MUST:

1. Read the relevant spec in `docs/specs/` to understand the schema and behavior contract.
2. Read the relevant guide in `docs/guides/` to understand the expected user experience.
3. Read any relevant plan in `.agents/plans/` to understand implementation sequencing.
4. After implementing, update ALL three areas that describe the changed behavior.

### Spec-First Version Development

Before implementing any new architecture work, the agent MUST first create or update the matching `docs/specs/` contract:

- Schema changes go in `docs/specs/curator_schema/SCHEMA.md`.
- Runtime behavior changes go in `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`.
- Plugin API changes go in `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`.

**CRITICAL RULE - STATIC SPECS MANDATE:** 
1. **Static Filenames**: Spec files MUST maintain static names (e.g., `SCHEMA.md`). Do NOT append version suffixes (e.g., `_v0.3.2.md`) to the filenames. The current version should only be noted inside the markdown title or frontmatter.
2. **No Archives**: Do NOT use or create `archives/` folders for specs. Old versions of specs are tracked entirely via Git. If you need historical context, use `git log` and `git show`.
3. **Synchronization**: When updating behavior for a new version, update all three core domains (`curator_schema`, `plugin_schema`, `system_behavior`) synchronously so they reflect the same target version in their titles.

- If code has already been written before the spec exists, stop and add the missing spec and guide entries before continuing implementation.

## System Invariants

- The Curator DAG layers are `01_Contexts`, `02_Atoms`, `03_Concepts`, and `04_Exhibitions`.
- Valid node prefixes are `CTX-`, `ATM-`, `CON-`, and `EXH-`.
- `qmd.yml` or qmd `index.yml` is search-engine configuration. `curate.yml` is the workspace Knowledge Requirement Specification.
- `03_Notes/` is human-verified source truth. Do not edit it autonomously.
- `04_Resources/` and `06_Archives/` are read-only source/reference spaces.
- `.curator/` is machine-readable Curator state. Modify it only through the project code or explicit testbed setup scripts.


## Multi-Agent Development Roles

When a change is broad, split review or implementation thinking into these roles and then integrate the result in one coherent patch:

- `schema_guardian`: checks v0.2.0 schema, layer names, prefixes, and frontmatter shape.
- `source_pair_analyst`: checks that `03_Notes/Papers` notes and `04_Resources` references can merge into shared higher-level DAG concepts.
- `topic_boundary_checker`: checks that unrelated `02_Wiki` topics remain distinguishable from the paper/resource topic.
- `cli_regression_runner`: checks `wiki init/status/add/curate/lint/reindex/query` smoke behavior in the testbed.
- `local_slm_simulator`: when the primary cloud LLM validation is too slow or unavailable, quickly simulates the expected small-model judgment using the seeded testbed Collections and source files. It must stay conservative and mark uncertain claims as "needs real LLM validation".
- `legacy_sweeper`: searches for qmd-excluded legacy terms and stale docs.

As the orchestrator, gather these findings, avoid conflicting edits, and report a concise verification result.

## Simulated LLM Fallback

Use the primary LLM backend first for LLM-sensitive changes. If it is too slow or blocked, run the `local_slm_simulator` role as a fast approximation:

- Compare the seeded L1-L4 testbed pages against the raw scenario files.
- Verify that paper/resource claims merge above L1 and that the RAG page remains a separate topic.
- Prefer short, explicit reasoning over exhaustive analysis.
- Clearly label the result as simulated validation, not a replacement for a later real model run.
