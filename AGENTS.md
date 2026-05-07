# AGENTS.md

This file is the repository-level rule source for Codex and other coding
agents. `CLAUDE.md` may mirror these rules for Claude Code, but this file is
the tool-neutral development contract.

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

## Core Rule: Testbed-Driven Development

All feature additions, bug fixes, migrations, and system rule changes must be validated in the `testbed/` vault which simulates a real environment. 

### Testbed Scenario Management
The standard scenario template for development and validation is located at `scripts/dev/`. 
Each scenario is contained in its own folder (e.g., `scripts/dev/testbed_template/`). 
Agents should refer to the specific scenario's `MASTER_PLAN.md` to understand the domain and validation goals.

- **Standard Template**: `scripts/dev/testbed_template/` is the blueprint for creating new scenarios.
- **Initialization Requirement**: If the `testbed/` directory does not exist, the agent MUST ask the USER to create one using the setup script for the appropriate scenario. If the USER explicitly refuses, the agent may skip testbed validation but must report the risk of unverified changes.
- **Before Action**: Before changing behavior, reproduce or describe the failing scenario using `testbed/` or the active scenario assets.
- **After Action**: After changing behavior, run the same scenario again and report the result.
- **Blockers**: If a dependency is unavailable, report the exact blocker and run every lower-level validation that does not need that dependency.
- **Completion Criteria**: Do not treat a query/search change as complete until it has been checked with the testbed, or until the qmd/LLM blocker is documented.

Recommended baseline:

```bash
# Replace <scenario_name> with the folder name (e.g., testbed_template or GS_Testbed)
wiki testbed init <scenario_name> --force
WIKI_ROOT=testbed wiki status
WIKI_ROOT=testbed wiki add
WIKI_ROOT=testbed wiki sync
```

The generated `testbed/` vault is configured to use Gemini CLI as its primary
LLM backend (`llm.primary: gemini-cli`). Before running LLM-sensitive testbed
commands, make sure the `gemini` command is installed and authenticated.

When qmd and the configured LLM backend are available, also run:

```bash
WIKI_ROOT=testbed wiki reindex
WIKI_ROOT=testbed wiki query "지식의 원자화와 합성이란 무엇인가?"
```

## Architecture Source Of Truth

When discussing or changing the system architecture, use these areas as the source-of-truth:

- **Static Specs**: `docs/spec/` for system contracts and schemas.
    - `docs/spec/curator_schema/` for Curator DAG schema contracts.
    - `docs/spec/system_behavior/` for Curator system behavior.
- **Dynamic Planning**: `docs/plans/` for implementation context.
    - `docs/plans/update_plan/` for migration and feature implementation plans.

Treat older root-level specs as historical unless the user explicitly points to them for comparison.

## v0.1.0 Invariants

- The Curator DAG layers are `01_Contexts`, `02_Atoms`, `03_Concepts`, and
  `04_Exhibitions`.
- Valid node prefixes are `CTX-`, `ATM-`, `CON-`, and `EXH-`.
- `qmd.yml` or qmd `index.yml` is search-engine configuration. `curate.yml` is
  the workspace Knowledge Requirement Specification.
- `03_Notes/` is human-verified source truth. Do not edit it autonomously.
- `04_Resources/` and `06_Archives/` are read-only source/reference spaces.
- `.curator/` is machine-readable Curator state. Modify it only through the
  project code or explicit testbed setup scripts.
- Exclude `src/qmd/**` from incurator v0.1.0 legacy sweeps unless the task is
  explicitly about qmd itself.

## Multi-Agent Development Roles

When a change is broad, split review or implementation thinking into these
roles and then integrate the result in one coherent patch:

- `schema_guardian`: checks v0.1.0 schema, layer names, prefixes, and
  frontmatter shape.
- `source_pair_analyst`: checks that `03_Notes/Papers` notes and
  `04_Resources` references can merge into shared higher-level DAG concepts.
- `topic_boundary_checker`: checks that unrelated `02_Wiki` topics remain
  distinguishable from the paper/resource topic.
- `cli_regression_runner`: checks `wiki init/status/add/curate/lint/reindex/query`
  smoke behavior in the testbed.
- `deepseek_8b_simulator`: when local `deepseek-r1:8b` validation is too slow,
  quickly simulates the expected small-model judgment using the seeded testbed
  Collections and source files. It must stay conservative and mark uncertain
  claims as "needs real LLM validation".
- `legacy_sweeper`: searches for qmd-excluded legacy terms and stale docs.

Codex orchestrates these roles: gather their findings, avoid conflicting edits,
and report a concise verification result.

## Simulated Gemini CLI Fallback

Use the real Gemini CLI path first for LLM-sensitive changes. If it is too slow
or blocked, run the `deepseek_8b_simulator` role as a fast approximation:

- Compare the seeded L1-L4 testbed pages against the raw scenario files.
- Verify that paper/resource claims merge above L1 and that the RAG page remains
  a separate topic.
- Prefer short, explicit reasoning over exhaustive analysis.
- Clearly label the result as simulated validation, not a replacement for a
  later real model run.
