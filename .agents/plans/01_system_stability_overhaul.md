# System Stability Overhaul — Master Implementation Plan

Date: 2026-06-22
Status: DRAFT — awaiting user approval (planning phase; no code yet)
Briefing: `.agents/plans/system_stability_overhaul_arena/00_problem.md`
Supersedes: the prompt-only milestone (folds in `prompt_architecture_refactoring.md`
and `popover_tool_scope.md`).

## 1. Objective

**Grand theme: make the system solidly stable ("단단하게 안정화").** This is not
just bug-fixing/refactoring — it spans correctness, performance, robustness, and
UX. Concretely, (a) produce an **exhaustive diagnosis ledger** across the entire
codebase, then (b) **improve** the prioritized findings along these axes:

1. **Correctness & structure** — bugs, redundancy, architectural redesign of
   god-files, legacy/dead-code removal.
2. **Prompt v2** — cross-model output consistency (minimize tier-to-tier drift).
3. **Performance** — measurably speed up the **RAG retrieval** and **DAG build**
   pipelines (no quality regression).
4. **Robustness / weakness-hunting** — proactively find system flaws (race
   conditions, failure modes, edge cases) and harden them, building on the
   existing **Failure Atlas (F1–F13)** quality contract.
5. **UI/UX** — explore and adopt better UX approaches for the existing surfaces
   (chat sidebar, popover, diff viewer, dashboard) where friction is found.
6. **Docs↔code** — fix drift, delete stale/redundant docs, consolidate, re-sync
   EN↔KR — without lossy compression of valuable detail (CLAUDE.md #6).

**Definition of done**: every triaged finding from P1 is either fixed (with test +
doc coverage) or explicitly deferred to the Icebox with a reason; `ruff`/`mypy`/
`pytest`/`vitest` green; testbed `wiki add/sync/query` parity holds; cross-model
prompt-consistency harness shows measured improvement over baseline.

## 2. Explicit Non-Goals

- NOT a 1.0 stabilization / public-API freeze (X stays 0).
- NOT a feature milestone. UI/UX work is limited to **improving existing
  surfaces** (reduce friction, better interaction on chat/popover/diff/dashboard)
  — NOT building the deferred roadmap features. The big roadmap items (PDF
  annotation, web search, storage governance, chat compaction) stay deferred.
- Performance work optimizes the EXISTING RAG/DAG pipelines; it does NOT redesign
  the retrieval algorithm or DAG schema (RRF+rerank, L1–L4 stay).
- NOT a rewrite. Architectural redesign is allowed at module-boundary level;
  full subsystem rewrites are out of scope.
- NOT a single monolithic PR (see §5 delivery model).

## 3. Strict Quality Conditions & Release Gates

- Every phase ends green on `scripts/backend-check {ruff,mypy,pytest}` +
  `npx vitest run -c ./plugin/vitest.config.ts`. No phase merges red.
- God-file refactors: characterization tests written FIRST; refactor proven
  behavior-identical before any redesign step.
- Prompt-v2: measurable reduction in cross-model output-shape divergence vs the
  baseline harness captured in P0. No regression in single-model quality.
- Legacy removal: each deletion cites usage-audit evidence proving it is
  unreachable/safe. No "delete and hope."
- Testbed smoke parity (`wiki add/sync/query`) holds at the end of every
  backend-touching phase.
- Docs↔code consistency: every behavior changed in a PR has its specs + guides
  (+ `_KR.md`) updated in the same PR; no doc describes removed behavior.
  Docs cleanup removes only stale/redundant/useless content — never lossy
  compression of valuable detail (CLAUDE.md #6).
- Performance: each perf PR shows a **measured** before/after speedup on a fixed
  benchmark, with **zero retrieval-quality regression** vs the Failure Atlas
  evaluation baseline / qrels. No "it feels faster."
- Robustness: hardening PRs add a regression test reproducing the flaw first
  (and, where it maps to a Failure Atlas case F1–F13, update that case record).
- UI/UX: each UX change cites the friction it removes and is validated by `/verify`
  (real plugin smoke), not just unit tests.

## 4. Locked Design Decisions (Arena Consensus)

- **Diagnosis-first.** P1 (exhaustive ledger) precedes all refactor phases; you
  cannot safely redesign god-files without the full debt map. STOP for user
  triage approval after P1.
- **Safety-net-before-surgery.** Architectural refactors are gated by
  characterization tests (P0). Behavior-preserving extraction first, redesign
  second — never both blind in one step.
- **Prompt-v2 = contract + normalization, not just text.** Cross-model
  consistency is achieved with (1) model-tier-aware prompt profiles, (2) strict
  output contracts (edit-block / tool-boundary invariants), and (3) a response
  normalization layer — measured by a golden-fixture harness, not vibes.
- **Sequential, hotspot-at-a-time.** One subsystem in flight at a time; RELAY.md
  updated each session.
- **Maximize PR granularity.** Deliver as MANY small PRs as is reasonable — one
  concern per PR (e.g. each god-file split is its own PR, not "all backend
  god-files" in one). A reviewable PR beats a complete-but-unreviewable one.
  Delivered as a chain of minor releases (0.25.0 → 0.26.0 → …) off `master`.
- **Prior-art research is mandatory per PR.** Before designing any non-trivial
  fix/refactor, research how comparable external programs solved the same
  problem (e.g. other Obsidian plugins & LLM clients for prompt/multi-model
  consistency; mature CLIs like git/kubectl/typer apps for command-module
  decomposition; ORMs/repositories for DB-layer splitting; established
  error-handling guidance for the broad-except pass). Record the findings and
  the chosen approach (with the why, incl. why rejected alternatives were
  rejected) in that PR's evidence note. No "invent in a vacuum."

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: roadmap items #4–#8 (wikilink validation, chat compaction,
  storage governance, PDF annotation, web search) remain deferred.
- **Delivery model**: each phase below is a standalone PR. Branch per phase off
  `master` (e.g. `refactor/prompt-v2-consistency`, `refactor/backend-cli-split`).
  The current `feature/prompt-architecture-refactoring` branch hosts P0–P1
  (diagnosis + harness) only.
- **Stop conditions** — agent MUST halt and ask the user when:
  - P1 diagnosis triage is ready (which findings to fix vs. defer).
  - any DB schema change is required (P1-contract approval gate).
  - a characterization test reveals existing behavior is itself buggy (decide:
    preserve vs. fix).
  - `qa_runner` fails 3× consecutively on a phase (invoke `rollback_strategist`).
  - a "legacy" removal cannot be proven safe by the usage audit.

## 6. Evidence Ledger

- **Repo/schema reality**: baseline captured 2026-06-22 — ruff/mypy clean; 116 py
  + 58 ts test files; god-file LOC table and 264 broad-except / 83 any-type counts
  recorded in `00_problem.md §2`. Prompt registry already shipped in `ac46f1d`.
- **Dirty worktree**: only `.agents/RELAY.md` modified (this planning session).
  No in-flight user code changes to clobber.
- **Rollback anchor**: tag the green `master` HEAD (or the merge-base) before P2
  surgery begins; each phase PR is independently revertible via `git revert -m 1`.
- **Per-phase evidence**: P1 produces `01_roadmap_evidence.md` (the findings
  ledger) with pre/post validation results recorded as phases land.

## 7. Execution Phases

Diagnosis LEADS (the user's primary ask is "deeply diagnose the system").
Safety-nets (characterization tests, the consistency harness) are built
JUST-IN-TIME inside the refactor phase that needs them, not as a big upfront
phase. Each refactor phase is split into as many small PRs as reasonable, and
each PR opens with a prior-art research note (§4).

- **Phase A — Baseline lock + Exhaustive Diagnosis Ledger** (branch: current)
  → **STOP for triage approval. This is a diagnosis-only phase: NO refactoring.**
  - Lock green ruff/mypy/pytest/vitest as the rollback anchor; note coverage gaps.
  - Systematic per-module audit → `.agents/plans/01_roadmap_evidence.md`,
    categorized: (a) correctness bugs, (b) redundancy/duplication, (c)
    error-handling smells (the 264 broad-excepts), (d) legacy/dead/compat-shim
    code (incl. `query.py` retired schemes, `config.py` aliases,
    `model_setup.py` legacy_model), (e) architectural debt (god-files, coupling),
    (f) **docs↔code drift & docs redundancy** — specs/guides that describe
    behavior the code no longer has (or vice-versa), duplicated/overlapping
    sections across the 27 docs (15.6k LOC), stale/useless docs, and EN↔KR
    divergence (16 paired guides),
    (g) **performance hotspots** — slow paths in RAG retrieval
    (`retrieval/`: chunking/embedding/vector/lexical/fusion/rerank) and DAG build
    (`pipeline/`: source_spans→knowledge_units→synthesis), N+1 DB queries,
    redundant LLM calls, missing caches/indexes,
    (h) **robustness / weaknesses** — race conditions, unguarded failure modes,
    edge cases; cross-referenced against the existing Failure Atlas F1–F13,
    (i) **UI/UX friction** — confusing/slow/inconsistent interactions on the chat
    sidebar, popover, diff viewer, and dashboard.
  - Each finding: location, severity, fix sketch, blast radius, suggested PR
    grouping.
  - Verify: loop-until-dry (2 consecutive passes find nothing new in a module
    before it's closed). User then triages fix-now vs. defer, and we sequence the
    fix PRs from the triaged list.

Refactor phases below are TARGETS; the triaged ledger from Phase A determines the
exact PR list and order. Each carries the standard gate (ruff/mypy/pytest/vitest
green + testbed parity for backend) and starts with prior-art research.

- **Prompt Architecture v2 — cross-model consistency** (≥1 PR, `refactor/prompt-v2-*`)
  - Build the cross-model consistency harness (golden fixtures + output-shape diff
    metric across Claude/Gemini/OpenAI/Ollama/DeepSeek) as the FIRST PR here — it
    is both the safety net and the success measure.
  - Then redesign `promptRegistry.ts` → model-tier-aware profiles + strict output
    contracts + response normalization; fully unify Sidechat/Popover; keep popover
    tool-isolation invariant. Spec: `docs/specs/plugin_schema/`.
  - Prior-art: how other Obsidian LLM plugins / agent clients tame multi-model
    output drift. Verify: harness improves vs. baseline; prompt tests extended.

- **Backend god-file decomposition** (one PR per file, `refactor/backend-*`)
  - Characterization tests FIRST (per file), then split `cli.py`, `db.py`,
    `mcp_server.py`, `ingest_raw.py` along cohesive seams. Spec: `system_behavior`.
  - Prior-art: command-module patterns (typer/click apps, git/kubectl),
    repository/DAO splits for the DB layer. Verify: pytest+mypy+testbed parity.

- **Plugin god-file decomposition** (one PR per file, `refactor/plugin-*`)
  - Decompose `chatSidebar.ts`, `llmClient.ts`, `externalPdfView.ts`; reduce
    `any`/`@ts-ignore`. Verify: vitest green + manual plugin smoke (`/verify`).

- **Error-handling root-cause pass** (grouped PRs, `fix/error-handling-*` /
  `chore/error-handling-*` — AGENTS.md prefixes only; not `refactor/`)
  - Triage the 264 broad-excepts: narrow to specific exceptions, surface real
    failures, remove bug-masking try/excepts. Prior-art: established
    exception-handling guidance. Verify: pytest green; no swallowed-error regress.

- **Legacy & dead-code sweep** (grouped PRs, `refactor/legacy-sweep-*`)
  - Remove ledger-identified legacy paths/shims/orphans, each citing usage-audit
    evidence; update specs to drop retired contracts.
  - Verify: ruff/mypy/pytest green; grep confirms zero live references.

- **RAG/DAG performance** (one PR per optimization, `perf/rag-*`, `perf/dag-*`)
  - FIRST PR: a repeatable benchmark harness (fixed corpus + timing on retrieval
    and DAG-build stages) — there is no perf infra today. It is both safety net
    and success measure; reuse the Failure Atlas fixture corpus/qrels to prove
    no quality regression.
  - Then optimize ledger-(g) hotspots one at a time (caching, batching LLM/embed
    calls, DB indexes, removing redundant passes). Prior-art: RRF/hybrid-search
    and vector-index tuning in mature RAG stacks.
  - Verify: measured speedup + qrels quality unchanged; pytest green.

- **Robustness hardening** (grouped PRs, `fix/harden-*`)
  - Fix ledger-(h) weaknesses; each PR adds a failing regression test first, then
    the fix. Where a flaw maps to a Failure Atlas case, update F1–F13 + its
    contract test. Prior-art: how comparable systems guard the same failure mode.
  - Verify: new regression tests green; `test_failure_atlas_eval.py` green.

- **UI/UX improvements** (one PR per surface, `feat/ux-*` or `fix/ux-*`)
  - Address ledger-(i) friction on existing surfaces only (chat/popover/diff/
    dashboard). Prior-art: how leading Obsidian plugins / AI chat UIs handle the
    same interaction. Spec: `docs/specs/plugin_schema/` + `PLUGIN_GUIDE`.
  - Verify: vitest green + `/verify` real-plugin smoke.

- **Docs reconciliation & cleanup** (grouped PRs, `docs/reconcile-*`)
  - Fix every docs↔code drift from Phase A category (f): make specs/guides match
    the code's actual behavior (more-concrete spec wins, but reconcile both —
    CLAUDE.md). Delete stale/useless docs and consolidate duplicated/overlapping
    sections; re-sync each EN guide with its `_KR.md` (edit EN first, KR follows).
  - **Anti-compression guardrail (CLAUDE.md #6)**: "cleanup" = remove
    stale/redundant/useless content and de-duplicate — it does NOT mean lossy
    summarization of valuable architectural detail. Preserve substantive design
    detail; only cut what is wrong, dead, or genuinely duplicated. When unsure
    whether content is "useless" vs "detailed-but-valuable", STOP and ask.
  - Verify: a docs↔code consistency check (CLI/MCP/plugin/config surfaces named
    in docs all exist in code and vice-versa); `test_spec_sync.py` green.

- **Finalization (per PR, not a separate phase)**
  - Each PR: version bump (`pyproject.toml`/`package.json`/`manifest.json` agree),
    `CHANGELOG.md`, spec-title vX.Y sync on minor bumps, docs + `_KR.md` sync,
    `USER_REPORT.md`/`ROADMAP.md` cleanup, release commit, PR with Why/What/How.

---

> Versioning: pre-1.0, so architectural/breaking changes ride **Minor** slots.
> Expect a chain 0.25.0 → 0.26.0 → … (one per shipped PR), NOT a single bump.
