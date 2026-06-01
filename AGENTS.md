# AGENTS.md

This file is the repository-level rule source for Codex and other coding
agents. `CLAUDE.md` may mirror these rules for Claude Code, but this file is
the tool-neutral development contract.

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

Whenever a user requests a new feature, major change, or uses the `/goal` command, the agent MUST automatically follow this strict 4-step workflow without being explicitly prompted:

1. **Plan First (Research & Design)**: Read the existing `docs/` to understand the current architecture. Then, write a detailed implementation plan in `.agents/plans/`. If there are design decisions or ambiguities, you MUST recommend the `/grill-me` slash command to align with the user through an interactive interview. **STOP** and wait for user approval before coding or changing docs.
2. **Docs Update**: Once the plan is approved, update or create the relevant specifications in `docs/specs/` and user guides in `docs/guides/` to define the target behavior.
3. **Test-Driven Development (TDD)**: Write failing tests (e.g., `pytest` or `testbed` scenarios) before writing the application logic.
4. **Implementation**: Write the code to make the tests pass, referencing the updated docs and plan, keeping changes surgical and minimal.

Do not skip straight to implementation. This workflow is non-negotiable for architectural changes or `/goal` requests.

---

## Core Rule: Cross-Agent Relay Protocol

To prevent context fragmentation and hallucinations when switching between AI coding agents (Antigravity, Claude Code, Cursor/Codex), all agents MUST adhere to the following protocol:

- **On Wakeup**: **CRITICAL INSTRUCTION FOR ALL AGENTS (CODEX, CLAUDE, ANTIGRAVITY)**. At the start of EVERY new conversation or session, the VERY FIRST ACTION you must take is to check if `.agents/relay.md` exists. If it does, you MUST read it in its entirety before taking ANY other action. Do NOT wait for the user to explicitly ask you to "resume work" or "read relay.md". If you fail to do this, you will cause severe context loss and code corruption.
- **Update Frequency**: 
  - Agents MUST update `.agents/relay.md` at the **end of every session** (before stopping execution).
  - Agents MUST always keep `.agents/relay.md` updated during a `/goal` or when an implementation plan is active.
- **Format**: Overwrite `.agents/relay.md` entirely using the standard template (Goal, Plan Reference, Analysis & Reasoning, Progress Status, Critical Context/Blockers, Immediate Next Action). Do not archive old states; maintain a single active state.

---

## Core Rule: Testbed-Driven Development

All feature additions, bug fixes, migrations, and system rule changes must be validated in the `testbed/` vault which simulates a real environment. 

### Testbed Scenario Management
The standard scenario template for development and validation is located at `scripts/dev/`. 
Each scenario is contained in its own folder (e.g., `scripts/dev/testbed_template/`). 
Agents should refer to the specific scenario's `MASTER_PLAN.md` to understand the domain and validation goals.

- **Standard Template**: `scripts/dev/testbed_template/` is the blueprint for creating new scenarios, but it is rarely the active one.
- **Scenario Discovery**: Because developers often use custom, `.gitignore`d scenario folders (e.g., `GS_Testbed`), the agent MUST first identify or ask the USER which scenario folder under `scripts/dev/` is currently active. Do not blindly default to `testbed_template`.
- **Initialization Requirement**: If the `testbed/` directory does not exist, the agent MUST initialize it using the active scenario's name (`wiki testbed init <scenario_name>`). If the USER explicitly refuses, the agent may skip testbed validation but must report the risk of unverified changes.
- **Before Action**: Before changing behavior, reproduce or describe the failing scenario using `testbed/` or the active scenario assets.
- **After Action**: After changing behavior, run the same scenario again and report the result.
- **External Reference Validation**: Any testbed validation must explicitly consider and verify the behavior of Zotero or other external resource directories imported via Reference Mode (without hard copying files into the vault).
- **Blockers**: If a dependency is unavailable, report the exact blocker and run every lower-level validation that does not need that dependency.
- **Completion Criteria**: Do not treat a query/search change as complete until it has been checked with the testbed, or until the qmd/LLM blocker is documented.

Recommended baseline:

```bash
# Replace <scenario_name> with the folder name (e.g., testbed_template or GS_Testbed)
# Optional: --llm <provider> --model <model_name>
wiki testbed init <scenario_name> --force
VAULT_ROOT=testbed wiki status
VAULT_ROOT=testbed wiki add
VAULT_ROOT=testbed wiki sync
VAULT_ROOT=testbed wiki lint
```

The generated `testbed/` vault is configured to use a primary LLM backend (default: `antigravity-cli`). Before running LLM-sensitive testbed commands, make sure the configured primary LLM tool is installed and authenticated.

When qmd and the configured LLM backend are available, also run:

```bash
VAULT_ROOT=testbed wiki reindex
VAULT_ROOT=testbed wiki query "Summarize the core concepts in this vault."
```

## Architecture Source Of Truth

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
- `.agents/plans/2024-05_v0.2.1_update/` for migration and feature implementation plans.
- **CRITICAL**: When creating architectural or feature implementation plans, all agents (Codex, Claude, Antigravity) MUST write their plan artifacts into `.agents/plans/` (instead of default temporary directories). You MUST read `.agents/plans/` for historical context before modifying existing systems.
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

Before implementing any new versioned architecture work (for example v0.2.1,
v0.2.2, or a new DAG/schema/MCP behavior change), the agent MUST first create or
update the matching `docs/specs/` contract:

- Schema changes go in `docs/specs/curator_schema/SCHEMA_vX.Y.Z.md`.
- Runtime behavior changes go in `docs/specs/system_behavior/incurator_vX.Y.Z.md`.
- Plugin API changes go in `docs/specs/plugin_schema/PLUGIN_SCHEMA_vX.Y.Z.md`.
- `.agents/plans/2024-05_v0.2.1_update/` may then reference those spec files as implementation
  plans, but plans alone are not sufficient ground truth.
- If code has already been written before the spec exists, stop and add the
  missing spec and guide entries before continuing implementation.
- Tests should include a lightweight guard when practical so version plans cannot
  drift away from the required `docs/specs/` contract.

## v0.2.0 Invariants

- The Curator DAG layers are `01_Contexts`, `02_Atoms`, `03_Concepts`, and
  `04_Exhibitions`.
- Valid node prefixes are `CTX-`, `ATM-`, `CON-`, and `EXH-`.
- `qmd.yml` or qmd `index.yml` is search-engine configuration. `curate.yml` is
  the workspace Knowledge Requirement Specification.
- `03_Notes/` is human-verified source truth. Do not edit it autonomously.
- `04_Resources/` and `06_Archives/` are read-only source/reference spaces.
- `.curator/` is machine-readable Curator state. Modify it only through the
  project code or explicit testbed setup scripts.


## Multi-Agent Development Roles

When a change is broad, split review or implementation thinking into these
roles and then integrate the result in one coherent patch:

- `schema_guardian`: checks v0.2.0 schema, layer names, prefixes, and
  frontmatter shape.
- `source_pair_analyst`: checks that `03_Notes/Papers` notes and
  `04_Resources` references can merge into shared higher-level DAG concepts.
- `topic_boundary_checker`: checks that unrelated `02_Wiki` topics remain
  distinguishable from the paper/resource topic.
- `cli_regression_runner`: checks `wiki init/status/add/curate/lint/reindex/query`
  smoke behavior in the testbed.
- `local_slm_simulator`: when the primary cloud LLM validation is too slow or unavailable,
  quickly simulates the expected small-model judgment using the seeded testbed
  Collections and source files. It must stay conservative and mark uncertain
  claims as "needs real LLM validation".
- `legacy_sweeper`: searches for qmd-excluded legacy terms and stale docs.

Codex orchestrates these roles: gather their findings, avoid conflicting edits,
and report a concise verification result.

## Simulated LLM Fallback

Use the primary LLM backend first for LLM-sensitive changes. If it is too slow
or blocked, run the `local_slm_simulator` role as a fast approximation:

- Compare the seeded L1-L4 testbed pages against the raw scenario files.
- Verify that paper/resource claims merge above L1 and that the RAG page remains
  a separate topic.
- Prefer short, explicit reasoning over exhaustive analysis.
- Clearly label the result as simulated validation, not a replacement for a
  later real model run.
