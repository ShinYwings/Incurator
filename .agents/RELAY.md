# Active Relay State

**STATUS: ACTIVE — Urgent hotfix SHIPPED & PUSHED (v0.25.0; commits b9a49a1 +
e3bee56; PR #48 open against master, awaiting user review/merge). System
Stability Overhaul RESUMES: Phase A diagnosis (G01–G06 done-unmerged; G07–G19 +
merge remain — see PHASE A RESUMPTION PROTOCOL below).**

**Branch**: `feature/prompt-architecture-refactoring` (user ordered the hotfix on
THIS branch, not a separate hotfix branch — log #1. User override of CLAUDE.md
hotfix-branch rule.)

---

## 🚨 URGENT HOTFIX — Backend/Plugin Config Isolation & Runtime Collision

Source: `.agents/drafts/urgent_hotfix_backend_plugin_config.md` (raw user log).
A prior PM (Gemini) botched this; its half-done edits are in the working tree.
User is BLOCKED from using the product → fix immediately, no Arena plan (user
explicitly said "draft 말고 당장", log #10).

### Locked architecture (the thing the PM kept missing)
- 1 Incurator backend (per device) ↔ MANY vaults. 1 vault ↔ MANY plugins.
- Backend config is PER-DEVICE (paths differ per machine) → must NOT live in the
  synced `.curator/`, must NOT be shared via the plugin.
- `.curator/settings.yml` = vault/plugin settings (synced). `FILE_SETTINGS_YML`.
- `.cache/config/config.yml` = backend global config, per-device, shared across
  vaults (`get_global_config_dir()` = `<incurator-install>/.cache/config`).
  `FILE_GLOBAL_CONFIG_YML`. **Location LOCKED by user (#14) — do not move.**
- devices.json already lives in `.cache/config/` (per-device) ✓ no change.

### Root causes found (verified)
1. **runtime path collision**: `runtime_state.runtime_dir` = `<vault>/.cache/plugin/
   runtime` — REJECTED by user (#16: every plugin shares one json). Must be
   Incurator-namespaced → `<vault>/.cache/incurator/runtime`.
2. **plugin readers disagree** (desync): `dashboardModal.ts:190` reads
   `.cache/plugin/runtime/`, but `chatSidebar.ts:418-419` still reads OLD
   `.curator/runtime/`. Backend writes a third-ish path. All three must agree.
3. **global-config Apply-revert (smoking gun)**: `cli.py` `config get/set --global`
   (lines 2481, 2492, 2537) use `FILE_SETTINGS_YML` (settings.yml) but
   `config.save_global_config`/`load_config` use `FILE_GLOBAL_CONFIG_YML`
   (config.yml). So `wiki config set --global` writes settings.yml while the
   system reads config.yml → the change is invisible → "Apply reverts after Jobs".
4. **stale test**: `test_runtime_state.py:114` still expects `.curator/runtime`.

### Already-correct (PM did these right — do NOT redo)
- `config.yml`↔`settings.yml` split in constants/config.py (mostly).
- Ollama recommendation conditional (dashboard ~1049-1068): already shows only
  when ollama is in any slot incl. vision/extract (covers "pdf도 ollama", #5/#6) ✓.
- devices.json in `.cache/config/` ✓.

### Exact fix list (execute in order; resume here if interrupted)
1. `constants.py`: add `DIR_PLUGIN_RUNTIME = ".cache/incurator/runtime"` (vault-root-
   relative, Incurator-namespaced).
2. `runtime_state.py:33`: `runtime_dir` → `paths.root / consts.DIR_PLUGIN_RUNTIME`.
3. `cli.py` 2481, 2492, 2537: `FILE_SETTINGS_YML` → `FILE_GLOBAL_CONFIG_YML`.
4. `plugin/src/ui/incuratorDashboardModal.ts:190`: `.cache/plugin/runtime/` →
   `.cache/incurator/runtime/`.
5. `plugin/src/ui/chatSidebar.ts:418-419`: `.curator/runtime/` →
   `.cache/incurator/runtime/`.
6. `backend/tests/test_runtime_state.py:114`: expect `.cache/incurator/runtime`.
7. Validate + version + commit. ← see status below.
- Out of scope (do NOT touch): `db_sync.py:615 .curator/runtime/sync_conflicts`
  (separate backend-internal archive), `.agents/.../curator/runtime` (agent rules).

### STATUS (2026-06-23) — UPDATED after deeper untangle; finishing release
**Architecture clarified with user (untangled together):**
- Backend per-device settings → `<repo>/.cache/config/config.yml` (+ devices.json).
  NOT synced. Location LOCKED.
- Vault syncable settings → `<vault>/.curator/settings.yml` (renamed from
  config.yml to kill the two-`config.yml` name collision that kept confusing
  edits). This rename is WANTED (user point #2).
- runtime snapshot → REVERTED to original `<vault>/.curator/runtime/` (device-local,
  already in `.stignore`). PM's `.cache/plugin/runtime` was wrong (new `.cache` in
  vault + broke sync-exclusion). My `.cache/incurator` was also wrong. All reverted.
- **NEW principle (user): dashboard reads ALL info LIVE via `wiki status --json`,
  not via the stale-prone snapshot file ("중간다리").** Implemented:
  - Backend `wiki status --json` emits live `{status,sources,jobs}` (cli.py status).
  - Dashboard `fetchLiveStatus()` runs it once per render (cached across panels,
    invalidated on tab switch, force-refreshed after mutations). No perf regression
    (dashboard already spawned `wiki status` per render; same call count).
  - Snapshot file kept ONLY as best-effort cache for the high-freq chat status bar.

**Bugs fixed (verified):** (1) `wiki config set --global` wrote settings.yml but
loader read config.yml → Apply-revert; both now config.yml. (2) Dashboard Apply
gated on settings.yml read (removed). (3) LLM Apply + Persona Save didn't refresh
after write (added). (4) model-load setInterval leaked on close (tracked+cleared).

**Validation:** ruff ✅ mypy ✅ · plugin tsc ✅ vitest 567 ✅ · runtime_state tests
✅ (incl. new status --json payload test). Full pytest running (`bssiy5453`).
Version 0.25.0 (Minor: new `--json` CLI surface + config-file contract rename),
3 manifests + 4 spec titles + spec_sync ✅. Docs: USER_GUIDE EN/KR (status --json)
+ `.curator/config.yml`→`settings.yml` sweep. CHANGELOG 0.25.0.

**SHIPPED:** hotfix committed as `b9a49a1` on `feature/prompt-architecture-refactoring`
(full pytest 1014 passed). NOT pushed (awaiting user). Planning artifacts in a
follow-up `chore(agents)` commit.
**Open follow-up (NOT this hotfix): types.ts loosened `codexReasoningEffort`/
`claudeEffort` to `string` (PM change, type-safety regression) — flag for review.**

### (prior status, superseded)
- ✅ Fixes 1–6 applied (constants, runtime_state, cli ×3, dashboardModal,
  chatSidebar, test_runtime_state uses `runtime_dir()` helper).
- ✅ Version bumped 0.24.0 → **0.25.0** (Minor: config-file contract rename) in
  3 manifests + 4 spec titles. `test_spec_sync` ✅. ruff ✅ mypy ✅ tsc ✅.
  Targeted pytest (runtime/config/deepseek/zotero) ✅.
- ✅ Docs drift fixed: `.curator/config.yml` → `.curator/settings.yml` across
  specs+guides (global `.cache/config/config.yml` left intact). CHANGELOG 0.25.0 added.
- ⏳ REMAINING: (a) full pytest `bfyxbjiio` must be green; (b) commit in TWO
  commits on this branch:
    1. `fix(config): backend/plugin config isolation + runtime collision + Apply desync (v0.25.0)`
       — backend/src, backend/tests, plugin/, docs/, CHANGELOG, 3 version manifests.
    2. `chore(agents): system-stability milestone plan + paused for hotfix`
       — `.agents/RELAY.md`, ROADMAP.md, drafts/urgent_hotfix*, plans/*, diagnosis/*.
  (Everything is currently `git add -A` staged together — UNSTAGE the `.agents/`
  group for commit 1, or just split via pathspec.) NO push/PR unless user asks.
- After hotfix ships: set ROADMAP active milestone back to System Stability
  Overhaul; resume Phase A diagnosis (G01–G06 files already on disk).

---

**Goal**: System Stability Overhaul — grand theme "make the system solidly
stable". EXHAUSTIVE whole-codebase diagnosis, then improvement across SIX axes:
(1) correctness/structure (bugs, redundancy, god-file redesign, legacy removal),
(2) prompt v2 cross-model consistency, (3) RAG/DAG performance (measured speedup,
no quality regression), (4) robustness/weakness-hunting (builds on Failure Atlas
F1–F13), (5) UI/UX improvement of existing surfaces, (6) docs↔code reconciliation.
Absorbs the original prompt-only milestone. Consolidated into one milestone,
shipped as many small PRs.

**Scope decisions (locked by user 2026-06-22)**:
1. Breadth: EXHAUSTIVE — entire codebase (44.1k LOC backend + 22.5k LOC plugin).
2. Refactoring boundary: ARCHITECTURAL REDESIGN ALLOWED (god-file re-partition).
3. Execution: SEQUENTIAL single-agent (no workflow fan-out).
4. Prompt architecture v2: REDO with goal = minimize cross-model output divergence
   (Claude/Gemini/OpenAI/Ollama/DeepSeek). (v1 already shipped in `ac46f1d`.)
5. Legacy cleanup: identify + remove legacy/dead/compat-shim code (audit-driven,
   NOT blind file deletion — legacy is embedded in live files).

**Plan Reference**:
- Briefing: `.agents/plans/system_stability_overhaul_arena/00_problem.md`
- Master Plan: `.agents/plans/01_system_stability_overhaul.md` (DRAFT — awaiting approval)
- Folded-in briefings: `prompt_architecture_refactoring.md`, `popover_tool_scope.md`

**Measured baseline (2026-06-22)**: ruff ✅ / mypy ✅ (97 files) / 116 py + 58 ts
tests. God-files: cli.py 7389, db.py 4679, mcp_server.py 3362, chatSidebar.ts 4828,
llmClient.ts 2282. 264 broad-except (backend), 83 any/@ts-ignore (plugin).

**Progress Status**: Master Plan DRAFTED. No implementation code written.

**Critical Context / Blockers**:
- Plan-first: STOP for user approval of the Master Plan before any code.
- Phases P0–P1 (safety-net + diagnosis ledger) run on the current branch; P2+
  each ship as their own minor-release PR off `master` (0.25.0 → 0.26.0 → …).
  Anti-mega-PR: never one monolithic diff.

**Delivery refinements (user 2026-06-22)**: maximize PR granularity (one concern
per PR); every non-trivial PR opens with a PRIOR-ART research note (how external
programs solved the same problem). Diagnosis LEADS; safety-nets built
just-in-time per refactor phase. **Docs in scope**: verify docs↔code consistency,
delete stale/redundant docs, consolidate, re-sync EN↔KR — but NO lossy
compression of valuable detail (CLAUDE.md #6). Phase A diagnosis ledger now spans
categories (a)–(i): bugs, redundancy, error-handling smells, legacy/dead code,
architectural debt, docs drift, performance hotspots, robustness/weaknesses,
UI/UX friction. Dedicated refactor phases exist for each axis.

**Immediate Next Action**: Phase A is RUNNING — exhaustive (A) deep diagnosis via
multi-agent fan-out (user authorized multi-agent 2026-06-23; speed not a concern,
quality is). Durable artifacts below survive rate-limit interruptions.

---

## 🔁 PHASE A RESUMPTION PROTOCOL (read this first if resuming)

**Goal**: complete an EXHAUSTIVE per-module diagnosis (loop-until-dry) into the
ledger, then STOP for user triage. Speed irrelevant; use multi-agent freely.

**Durable artifacts (source of truth for resume)**:
- `.agents/plans/diagnosis/INDEX.md` — module-group checklist with per-group
  STATUS (pending / running / done / merged). **Always update this** as groups
  finish so a fresh session knows exactly what's left.
- `.agents/plans/diagnosis/<group>.md` — each diagnosis agent writes its raw
  findings here. These persist even if the merge step is interrupted.
- `.agents/plans/01_roadmap_evidence.md` — the MERGED, deduped ledger (the
  triage deliverable). First-pass headline findings already recorded.

**How to resume after an interruption**:
1. Read `INDEX.md`. Any group NOT `merged` is unfinished.
2. For groups `done` but not `merged`: read their `<group>.md` and merge into the
   ledger, then mark `merged`.
3. For groups `pending`/`running`: (re)launch a diagnosis agent for them
   (Workflow `resumeFromRunId` reuses cached completed agents; or spawn fresh
   Agent calls per group). Each agent WRITES its own `<group>.md`.
4. When ALL groups are `merged` → run loop-until-dry re-pass on high-risk groups
   → finalize ledger → STOP for user triage (fix-now vs defer).

**Active diagnosis workflow**: `phase-a-diagnosis` run `wf_32efc6f1-136` (19 agents,
G01–G19, each writes `.agents/plans/diagnosis/<group>.md`). Resume cached:
`Workflow({scriptPath: "…/workflows/scripts/phase-a-diagnosis-wf_32efc6f1-136.js",
resumeFromRunId: "wf_32efc6f1-136"})`. If the run is gone, just spawn fresh Agent
calls per group still marked `pending` in INDEX.md.

**Baseline anchor**: ruff ✅ / mypy ✅; full pytest was kicked off as the rollback
anchor (record pass/fail in the ledger §0 once known).

**Backend prompt infra note**: `backend/src/curator/prompting/` already has
`registry.py`, `contracts.py`, `validators.py`, `render.py`, `families/` — the
prompt-v2 cross-model work must reconcile plugin `promptRegistry.ts` WITH this
backend layer, not duplicate it.