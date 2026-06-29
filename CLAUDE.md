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

### 7. Root Cause Over Workarounds

**Fix the disease, not the symptoms. Do not use workarounds.**

- Never bypass a broken system with a temporary hack or "workaround" just to make a test pass or a command succeed.
- If a function is fundamentally flawed, fix the function. Do not wrap it in a `try...except` that hides the failure or add external scripts to patch its outputs.
- If you find yourself writing logic that "corrects" the output of another buggy component, STOP. Go back and fix the buggy component directly.
- Workarounds accumulate tech debt and cause cascading failures. Your job is to identify the root cause and resolve it definitively.

Incurator is an LLM-maintained personal knowledge base (Zettelkasten) integrated with Obsidian. It ingests external sources through a 4-layer curation pipeline (L1 Contexts → L2 Atoms → L3 Concepts → L4 Synthesis) using a multi-provider LLM backend, building a verifiable cross-linked knowledge graph accessible to both humans and AI agents.

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

## Core Rule: The Development Pipeline State Machine

**GLOBAL PRIORITY RULE**: Every task flows strictly through a cascading pipeline: `User Report → Draft → Plan → Implementation`.
When any agent wakes up, they MUST evaluate the current project state and execute the NEXT logical phase. Never skip steps.

- **State 1 (Inbox Populated)**: If there are raw items in `.agents/USER_REPORT.md`, you may bypass the draft phase entirely and author a Master Plan (`.agents/plans/`) directly from the user report. You do NOT need to create a draft first.
- **State 2 (Drafts Exist, No Plans)**: If a pre-existing draft has been provided in `.agents/drafts/`, you MUST use that draft as the Briefing for your Arena debate to synthesize the `PLAN_TEMPLATE.md`.
- **State 3 (Plans Exist)**: If an approved Master Plan exists in `.agents/plans/`, you MUST execute TDD and Code Implementation.
- **State 4 (Empty Inbox)**: If `USER_REPORT.md` is empty and no active drafts/plans exist, the system is IDLE. There are no pending tasks.

## Core Rule: System Update Workflow (Universal Strict Workflow)

**GLOBAL PRIORITY RULE**: Before starting any `/goal` or architectural planning, agents MUST check `.agents/USER_REPORT.md` for new inbox items, and `.agents/ROADMAP.md`'s To-Do queue. If there are unresolved bugs or pending items in the user report, you MUST prioritize grouping and fixing those first.
**BLOCKED ICEBOX EXCEPTION**: If an item in `USER_REPORT.md` is waiting on an external dependency or cannot be fixed immediately, move it to the `🧊 Blocked / Icebox` section in `.agents/ROADMAP.md` and **delete** it from `USER_REPORT.md`. The Global Priority Rule explicitly IGNORES items in this section.
**HOTFIX EXCEPTION**: If a critical bug is reported while a large Batch Release (e.g., `v0.4.0`) is already being planned or worked on, the agent MUST immediately create a separate `hotfix/...` branch, patch the bug (`+0.0.1`), and open a PR. Do not delay hotfixes by bundling them into ongoing major/minor batch plans.
**VERSION BUMP IS MANDATORY FOR ALL CODE CHANGES**: Step 10 (Version Bump & Changelog) is NON-NEGOTIABLE for any branch that modifies code (`hotfix/*`, `release/*`, `feature/*`, `fix/*`). Only `chore/*` branches (CI, tooling, dependency-only changes) are exempt. `pyproject.toml`, `package.json`, and `manifest.json` must all agree on the same version before the PR is opened. The CI `version-consistency` job will block the merge if they disagree — this is the hard gate. The version bump is what triggers the Obsidian update toast for installed users; skipping it silently breaks the self-update mechanism.

Whenever a user requests a new feature, reports a bug, or uses the `/goal` command, the agent MUST automatically follow this strict 12-step `Universal Strict Workflow`:

1. **Triage & Queuing**: Read `.agents/USER_REPORT.md` (the chronological inbox). Register a bullet point in the `To-Do` queue in `.agents/ROADMAP.md` for the items you are planning to handle, and **delete** the raw items from `.agents/USER_REPORT.md`. If a pre-existing draft exists in `.agents/drafts/`, use it; otherwise, you may proceed directly from the raw inbox items.
2. **Batch & Version Planning**: Read the `To-Do` section in `.agents/ROADMAP.md` (ignoring Blocked items) and group related items into a single Batch Release. Cross-reference each candidate item against roadmap drafts to understand which milestone it belongs to. Decide the bump using the **0.x SemVer criteria below — do NOT default to Minor** (the project is pre-1.0):
   - **Patch (Z, e.g. `0.18.0 → 0.18.1`)**: backward-compatible bug fixes, performance tweaks, and small internal refactors with **no** new user-facing capability and **no** schema/contract change. A batch whose `CHANGELOG.md` entry carries only a `### Fixed` section is a Patch (precedent: v0.17.0 was a pure clickable-wikilink fix and should have shipped as `0.16.2`).
   - **Minor (Y, e.g. `0.18.1 → 0.19.0`)**: any new user-facing feature, new CLI command / MCP tool / plugin setting / config field, or any schema/contract change. While in 0.x, **breaking changes also ride the Minor slot** — the public API is not yet frozen, so they do not force a Major.
   - **Major (X, `0.y.z → 1.0.0`)**: reserved for the first stable, production-ready public release — the point at which the DAG schema, CLI surface, MCP tool contracts, and plugin API are declared stable and breaking changes thereafter require a Major bump. This is a deliberate user/product decision, **never** an automatic outcome of a batch; X stays `0` until the user explicitly calls 1.0.

   **CRITICAL**: If the update is Minor/Major and includes breaking schema changes, you MUST plan and write a data migration script.
3. **Branch Creation**: Create and switch to a new Git branch for the release (e.g., `release/v0.3.3` or `feature/issue-name`). NEVER work directly on the `main` branch. You MUST update `.agents/RELAY.md` with the current branch name so other agents know where they are.
4. **Plan Creation (Arena Workflow)**: Using either the pre-existing draft in `.agents/drafts/` or the raw inbox items as the '00_problem.md' Briefing, run the Arena debate and author the final `PLAN_TEMPLATE.md` in `.agents/plans/`. **CRITICAL**: As soon as the plan is finalized, you MUST update `.agents/ROADMAP.md` to reflect the new active milestone. If there are ambiguities, explicitly ask the user clarifying questions. **STOP** and wait for user approval before coding.
5. **Docs Update**: Update `docs/specs/` and `docs/guides/` to define the target behavior. (Crucial: Update the English guides first, then faithfully synchronize the matching `_KR.md` Korean guides).
6. **Test-Driven Development (TDD)**: Write failing tests before writing application logic.
7. **Implementation & Incremental Commits**: Write code to make tests pass. Commit work incrementally using Conventional Commits (e.g., `feat(core): ...`, `fix(plugin): ...`).
8. **Local CI Validation**: Before finalizing, you MUST run all local checks. Keep the service/runtime venv at the repo root as `.venv`; `./setup.sh` updates this environment for real backend/plugin service deployment and MUST NOT install dev-only check tools into it. Keep the backend development/validation venv at the repo root as `.venv-dev`; install `backend[dev,mcp]` there. Run backend checks through the repo-root helper, which calls `.venv-dev/bin` directly, stores tool caches under repository `.cache/`, and never creates backend-local artifacts: `scripts/backend-check pytest`, `scripts/backend-check ruff`, `scripts/backend-check mypy`, and the plugin's `npx vitest run -c ./plugin/vitest.config.ts`. Never create `backend/.venv`, `backend/.venv-dev`, `backend/uv.lock`, or backend-local tool caches. Ensure the entire system is intact.
9. **Report Cleanup**: Once an item is verified, ensure it is marked as completed or removed from `.agents/ROADMAP.md` (since it was already deleted from USER_REPORT.md during planning).
10. **Version Bump & Changelog**: Update the version strings in all relevant configuration files (`pyproject.toml`, `package.json`, `manifest.json`) AND update `CHANGELOG.md` with the release notes for this version. **MINOR/MAJOR SPEC-LINE SYNC (mandatory whenever the `MAJOR.MINOR` line changes — e.g. `0.16.x → 0.17.0`)**: `backend/tests/test_spec_sync.py` derives the active version from the build manifests (`backend/pyproject.toml` plus the two `plugin/` JSON manifests — the single source of truth, read directly, NOT from installed package metadata) and hard-asserts that (a) all three build manifests agree on the version and (b) every static spec title (first line of `docs/specs/curator_schema/SCHEMA.md`, `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`, `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`, and `docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md`) declares the active `vX.Y` line. So on any minor/major bump you MUST also bump the `(vX.Y.Z)` suffix in all four spec-file titles to the new line. There is no `ACTIVE_VERSION` constant to maintain and no dev-venv reinstall is needed — because the test reads the manifest directly, it validates identically locally and in CI. Pure patch bumps that keep the same minor line do not touch the spec titles.
11. **Plan Deletion**: **Delete** the implemented plan file(s) from the workspace. The plan's historical context will be statically preserved in the Git history for this version.
12. **Release Commit**: Create a final release commit explicitly named `chore(release): vX.Y.Z`.
13. **Push & PR (Zero-Interaction Auto-Pilot)**: Push the branch to the remote repository. Create a GitHub Pull Request that includes a detailed PR Description (Why, What, How). **CRITICAL**: Once the workflow begins, agents MUST auto-approve their own steps and operate with zero user interaction. Do not pause to ask the user for confirmation on intermediate code changes or terminal commands. The human user's ONLY responsibility is to review and merge the final Pull Request on GitHub.

---

## Core Rule: Review Feedback Loop (Plan-First, Proactively)

**A PR is not the end of the workflow — review feedback re-enters it.** When a review (human PR comment, `/code-review` / `ultrareview` findings, or an in-session design review) surfaces a **new feature request or a non-trivial bug** on work that is already in flight, the agent MUST handle it through the same plan-first discipline as any other item — **without being asked**. Do not wait for the user to say "make a plan"; recognizing review feedback and routing it back through the workflow is the agent's own responsibility.

The mandatory sequence when review feedback arrives:

1. **Capture in `USER_REPORT.md` immediately.** Add the feedback as a new item. Preserve the reviewer's edge cases verbatim — do not compress them away (see Anti-Compression rule).
2. **Author a `PLAN_TEMPLATE.md`-compliant plan BEFORE writing any implementation code.** A non-trivial review-requested feature gets the full Arena treatment (problem statement → persona proposals → cross-critique → master plan), exactly like a fresh milestone. Link the plan from its `USER_REPORT.md` item and vice versa.
3. **STOP for approval on substantial work.** As with Step 3 of the Universal Strict Workflow, pause for user approval of the plan before coding a substantial feature. (Trivial nits — see exception below — skip this.)
4. **Then implement** through TDD + incremental commits + local CI, and only then push the follow-up onto the same release branch / PR.

**TRIVIAL-NIT EXCEPTION**: Pure review nits with no behavioral or architectural impact — typos, lint, formatting, a rename, a one-line guard, a doc-only fix — may be patched directly into the open PR without a separate plan. Use judgment: if it touches schema, control flow, a public contract, a new file/module, or introduces a new user-facing behavior, it is NOT trivial and needs a plan.

**WHY THIS RULE EXISTS (anti-pattern to avoid)**: Hot-patching a substantial feature directly in response to a review comment — coding first, skipping the Arena plan — produces buggy, hard-to-review changes that often have to be reverted wholesale. A real precedent: a cross-device auto-sync feature was implemented straight from review feedback with no Arena plan; its hash-based loop-prevention silently broke `wiki db import` (reported 0 changes) and the entire feature had to be reverted, then re-planned from scratch. Plan-first is cheaper than revert-then-replan. **The disease is "code-first on review feedback"; the cure is "capture → plan → approve → implement," done proactively.**

---

## Core Rule: Cross-Agent Relay Protocol

To prevent context fragmentation and hallucinations when switching between AI coding agents (Antigravity, Claude Code, Cursor/Codex), all agents MUST adhere to the following protocol:

- **On Wakeup**: **CRITICAL INSTRUCTION FOR ALL AGENTS (CODEX, CLAUDE, ANTIGRAVITY)**. At the start of EVERY new conversation or session, the VERY FIRST ACTION you must take is to check if `.agents/RELAY.md` exists. If it does, you MUST read it in its entirety before taking ANY other action. Do NOT wait for the user to explicitly ask you to "resume work" or "read RELAY.md". If you fail to do this, you will cause severe context loss and code corruption.
- **Update Frequency**: 
  - Agents MUST update `.agents/RELAY.md` at the **end of every session** (before stopping execution).
  - Agents MUST always keep `.agents/RELAY.md` updated during a `/goal` or when an implementation plan is active.
- **Format & Behavior**: 
  - **For Main Architecture Tasks / Goals**: Overwrite `.agents/RELAY.md` entirely using the standard template (Goal, Plan Reference, Analysis & Reasoning, Progress Status, Critical Context/Blockers, Immediate Next Action). Maintain a single active state for the core task.
  - **For Bug Fixes / Side-Tasks (Any Agent)**: When any agent handles a side-task or bug fix while a main goal is active, it must NOT overwrite the main relay state. Instead, **APPEND** a new section (e.g., `### Update (YYYY-MM-DD, AgentName)`) at the bottom of `.agents/RELAY.md` summarizing what was investigated, fixed, or modified. This ensures the primary agent's context is not destroyed by small interventions.
  - **Antigravity Fallback Execution**: If primary executors (e.g., Claude Code) are rate-limited or resting, Antigravity may temporarily act as the Executor. However, any code written by Antigravity MUST be explicitly marked in `.agents/RELAY.md` for mandatory verification by the primary Executor upon wakeup.
  - **IDLE Cleanup**: When the goal is fully shipped (PR merged, no active task), truncate `.agents/RELAY.md` to a minimal IDLE stub — do NOT accumulate session history. Git log is the history; RELAY.md is live state only.

---

## Core Rule: Branch Naming & Merge Safety

### Branch Naming Convention (GitHub Flow)

All branches are created from `master` and merged back to `master` via PR. Never nest branches (no feature-from-release, no fix-from-feature).

| Pattern | Base | When to use |
|---|---|---|
| `release/vX.Y.Z` | `master` | Batch releases planned from `USER_REPORT.md` |
| `feature/short-description` | `master` | New standalone features |
| `fix/short-description` | `master` | Bug fixes and post-release cleanup |
| `chore/short-description` | `master` | CI, tooling, config, dependency changes |
| `hotfix/vX.Y.Z-description` | `master` | Critical production fixes (bypass normal release cycle) |

> **Note**: This repo uses `master` (not `main`). Do not rename the branch.

### Rollback Procedure (Bad Merge)
If a merged PR introduces a regression that cannot be quickly patched forward:

```bash
# 1. Find the bad merge commit hash
git log --oneline master | head -5

# 2. Revert it safely — creates a new "undo" commit, keeps history intact
git checkout master
git revert -m 1 <merge-commit-hash>

# 3. Push and open a follow-up PR explaining the revert
git push origin master   # only if user explicitly approves a direct push to master
```

**Never use `git reset --hard` on a shared branch.** `git revert` is always
safe because it is additive — it can itself be reverted if the original fix
was actually correct.

---

## Shared Architecture Memory

All agents (Claude Code, Codex, Antigravity) MUST treat the following decisions as locked unless the user explicitly overrides them. These are condensed here so every agent starts with the same mental model regardless of which tool-specific memory system it uses.

### Storage Model
- **`state.sqlite` = single source of truth.** Holds source_spans, knowledge_units, graph entities/relations, community_reports, synthesis_nodes, dag_edges, job queue.
- **`.curator/Collections/` markdown = derived disposable search corpus.** Regenerated from DB at any time. Not authoritative. Do not treat stale markdown as ground truth — re-emit from DB if in doubt.
- **Search is DB-native (v0.3.2+).** SQLite FTS5/BM25 + chunk vector + RRF fusion + LLM reranking. Do not add external search-binary dependencies.
- **No backward-compat shims.** New runs use the current code path directly.

### Curation Model
- **Static/frozen Exhibition files (EXH-*.md) are REMOVED.** `wiki curate`, `curator_curate_workspace`, EXH answer-cache, and EXH reverse-parse backprop were deleted. Do not reintroduce them.
- **Curation = dynamic KRS-biased lens applied at retrieval time.** `curate.yml` (KRS) + insight promotions = a retrieval policy; never stored as a file.
- **Layer stack: L1 spans → L2 atoms → L3 concepts → L4 Synthesis (shared stored SYN-*) → Curation lens (dynamic, not stored).**
- **Durable human artifacts = `02_Wiki/` promotions only.** Chat history lives in plugin `sessions.json`, not the vault.

### Where to Find Extended Decisions
- Claude-specific memory: `~/.claude/projects/-Users-shin-shinywings-Incurator/memory/`
- Project-local memory (all agents): `.claude/projects/-Users-shin-shinywings-Incurator/memory/`
- Specs (authoritative): `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`, `docs/specs/curator_schema/SCHEMA.md`

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
- **Completion Criteria**: Do not treat a query/search change as complete until it has been checked with the testbed, or until the search/LLM blocker is documented.

## Development Commands

```bash
# Runtime/service venv policy: ./setup.sh updates <repo>/.venv for the real
# backend/plugin service deployment. Do not install dev-only check tools there.
./setup.sh

# Backend dev/validation venv policy: checks use <repo>/.venv-dev directly,
# never backend/.venv, backend/uv.lock, or backend-local caches.
uv venv "$(git rev-parse --show-toplevel)/.venv-dev"
uv pip install --python "$(git rev-parse --show-toplevel)/.venv-dev/bin/python" \
  -e "$(git rev-parse --show-toplevel)/backend[dev,mcp]"

# Lint / type-check / test. Use the root helper; it calls .venv-dev/bin
# directly and pins mypy stubs/cache without exporting VIRTUAL_ENV.
scripts/backend-check ruff
scripts/backend-check mypy
scripts/backend-check pytest

# Run a single test
scripts/backend-check pytest backend/tests/test_db.py::test_source_deduplication -v

# Build package
hatch backend/build

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
wiki add <file>         # Parse source and generate L1-L4 layers
wiki sync               # Verify DAG integrity, rebuild index/ledger
wiki lint               # Health check: broken links, orphans, contradictions
wiki query "<question>" # Search and synthesize answer with citations
wiki reindex            # Force rebuild of DB-native FTS5 search index
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
     │  LLM pass → generate L1-L4
     ▼
[01_Contexts/CTX-<UUID>.md]
[02_Atoms/ATM-<UUID>.md]       ← atomic facts extracted by LLM
[03_Concepts/CON-<UUID>.md]    ← cross-source thematic groupings
[04_Synthesis/SYN-<UUID>.md]   ← shared stored synthesis (workspace-independent)
     │
     │  Curation lens (dynamic, applied at query time via curate.yml KRS)
     ▼
     ├─ wiki query (search.py / DB-native FTS5+vector+RRF+rerank)
     └─ HITL promotion → 02_Wiki/ (becomes new L1 input next cycle)
```

### Key Modules

| Module | Role |
|--------|------|
| `cli.py` | Typer CLI; auto-selects LLM backend by available RAM (<16 GB → Antigravity cloud, ≥16 GB → Ollama local) |
| `db/` | SQLite state (`state.sqlite`): source deduplication (SHA256 hash), ingest run history, source→page provenance. Package (decomposed from the former `db.py`, DB-2): `db/schema.py` (DDL, migrations, `connect`, `init_db`), `db/_entities.py` (entity repository queries), `db/__init__.py` re-export facade — still imported as `from . import db` and used via `db.<name>` |
| `ingest_raw.py` | File discovery, hash-based dedup, parser dispatch, L1 Context generation |
| `ingest_llm.py` | Three-phase DAG construction: Phase A (atoms), Phase B (concepts/communities), Phase C (synthesis) |
| `sync.py` | DAG integrity verification; Mode A (global reverse L4→L1) and Mode B (targeted bidirectional) |
| `search.py` | DB-native search: SQLite FTS5/BM25 + chunk vector + RRF fusion + LLM reranking |
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
    ├── settings.yml   Vault-scoped portable settings (persona, sync policy, etc.)
    ├── state.sqlite   Dedup hashes, run history, provenance
    ├── index.md       DAG routing table (all L1-L4 node IDs)
    ├── overview.md    Domain manifest
    ├── log.md         Append-only event log
    ├── ledger.md      HITL correction record
    └── Collections/
        ├── 01_Contexts/
        ├── 02_Atoms/
        ├── 03_Concepts/
        └── 04_Synthesis/
```

### Architecture Source Of Truth

The **entire `docs/` tree is source of truth**. The system design becomes increasingly concrete across three distinct levels of documentation. Agents must read the relevant docs before implementing or changing behavior, and respect this hierarchy:

1. **Philosophy (`docs/philosophy/`)**: The abstract intent and high-level principles of the system.
3. **User Guides (`docs/guides/`)**: The concrete user-facing behavior and operational workflows.
    - Guides are authoritative for CLI commands, MCP tools, plugin features, config fields, env vars, and workflow behaviors.
4. **Static Specs (`docs/specs/`)**: The absolute concrete implementation details, system contracts, and schemas.
    - `docs/specs/curator_schema/` for Curator DAG schema contracts.
    - `docs/specs/system_behavior/` for Curator system behavior.
    - `docs/specs/plugin_schema/` for Obsidian plugin API contracts.

When they conflict, the more concrete layer (spec) dictates the implementation reality, but any divergence means both are wrong until reconciled. Do not treat guides as subordinate to specs — fix both together.

**Dynamic Planning**: `.agents/plans/` for implementation sequencing and context.
- **CRITICAL RULE - PLAN TEMPLATE MANDATE**: When creating architectural or feature implementation plans, all Executors MUST FIRST read `.agents/PLAN_TEMPLATE.md` and strictly copy/adhere to its Markdown skeleton. You MUST write your final plan artifacts into `.agents/plans/` (instead of default temporary directories).
- **Draft to Plan Pipeline**: If skeleton files exist in `.agents/drafts/`, they are **problem definitions (Briefings)**. You MUST read these drafts, treat them as the input constraints, and run the Arena debate to replace them with the full three-document set before implementation begins.
- **Three mandatory documents** (per PLAN_TEMPLATE.md) before any code is written:
  1. **Domain Analysis docs** (`A_*.md`, `B_*.md`, …) — one per major component. Each must cover: design constraints from codebase, docs/specs invariants, alternatives & trade-offs, final decision, and implementation pseudocode/SQL.
  2. **Master Implementation Plan** (`[XX]_[feature].md`) — locked design decisions, contracts preserved, multi-agent role reviews, and strict phases (`P1 → P2 → …`). Each phase must pass `pytest` + `ruff` before the next begins.
  3. **Evidence Ledger** (`[XX]_roadmap_evidence.md`) — created immediately before coding starts. Records rollback anchor, current schema reality, and pre/post validation results.
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
3. **No Archives**: Do NOT use or create `archives/` folders for specs. Old versions of specs are tracked entirely via Git. If you need historical context, use `git log` and `git show`.
4. **Synchronization**: When updating behavior for a new version, update all three core domains (`curator_schema`, `plugin_schema`, `system_behavior`) synchronously so they reflect the same target version in their titles.

- If code has already been written before the spec exists, stop and add the missing spec and guide entries before continuing implementation.

## System Invariants

- The Curator DAG layers are `01_Contexts`, `02_Atoms`, `03_Concepts`, and
  `04_Synthesis`. The `04_Exhibitions` directory exists as an inert no-op
  (static EXH files were removed in v0.3.1). Do not write new EXH files.
- Valid node prefixes are `CTX-`, `ATM-`, `CON-`, `SYN-`. `EXH-` is retired.
- `curate.yml` is the workspace Knowledge Requirement Specification.
  Search is DB-native (FTS5 + vector + RRF + reranking).
  Do not add external search-binary dependencies or generated search-backend
  config files.
- `03_Notes/` is human-verified source truth. Do not edit it autonomously.
- `04_Resources/` and `06_Archives/` are read-only source/reference spaces.
- `.curator/` is machine-readable Curator state. Modify it only through the
  project code or explicit testbed setup scripts.


## Multi-Agent Execution Roles (Development & CI Workflow)

During the execution phase (after the Arena Master Plan is approved), the implementation must be driven by a structured, role-based execution pipeline (similar to MetaGPT/ChatDev software company models). Agents must adopt these personas sequentially to ensure robust code quality:

- **`coder_engineer`**: Focuses purely on implementing the feature logic according to the Master Plan and writing initial tests. Does not touch unrelated files or "improve" adjacent code.
- **`peer_reviewer`**: Conducts a strict static analysis of the `coder_engineer`'s PR before it goes to QA. Checks for tight coupling, memory leaks, missing error handling, and hardcoded variables.
- **`schema_guardian`**: Reviews the implementation to strictly ensure `SCHEMA.md`, layer names, prefixes (`CTX-`, `ATM-`, `CON-`, `SYN-`), and frontmatter shape conform to the spec without regressions.
- **`qa_runner` (CI/Testbed)**: Executes the E2E verification. Runs `pytest`, `ruff check`, `mypy`, and `wiki testbed init`. Simulates edge cases (e.g., `local_slm_simulator` for LLM failure, verifying topic boundary isolation).
- **`rollback_strategist`**: Activates if the `qa_runner` fails more than 3 times in a row. Analyzes the failure loop, cleanly reverts the Git branch to the last stable state, and forces a return to the planning phase (prevents LLM infinite-looping).
- **`docs_sync_manager`**: Ensures that `docs/specs/` and `docs/guides/` are faithfully updated immediately after the code passes QA, maintaining the English -> Korean `_KR.md` translation sync.
- **`legacy_sweeper`**: Performs cleanup before finalizing the PR. Searches for unused imports, deleted API references, orphaned test functions, and stale comments left behind by the new implementation.

As the orchestrator, you must route the workflow through these execution roles sequentially, ensuring code passes through the `peer_reviewer`, `schema_guardian`, and `qa_runner` validations before considering the implementation phase complete.

## Simulated LLM Fallback

Use the primary LLM backend first for LLM-sensitive changes. If it is too slow or blocked, run the `local_slm_simulator` role as a fast approximation:

- Compare the seeded L1-L4 testbed pages against the raw scenario files.
- Verify that paper/resource claims merge above L1 and that the RAG page remains a separate topic.
- Prefer short, explicit reasoning over exhaustive analysis.
- Clearly label the result as simulated validation, not a replacement for a later real model run.
