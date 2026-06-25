# Active Relay State

**STATUS: ACTIVE — v0.25.1 User Report Stability Bug Batch pushed as draft PR #49; System Stability Phase A diagnosis can resume after review/merge (G01–G06 done-unmerged; G07–G19 + merge remain).**

**Branch**: `feature/system-stability-overhaul`

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

**Progress Status**: System Stability master plan drafted; urgent user-report
stability hotfix batch completed as v0.25.1 on this branch. The hotfix plan was
committed for history, then removed from active `.agents/plans/` per workflow.

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

**Immediate Next Action**: review/merge draft PR #49
(`https://github.com/ShinYwings/Incurator/pull/49`), then resume Phase A
diagnosis from `.agents/plans/diagnosis/INDEX.md`.

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

### Update (2026-06-25, Codex)

User asked to handle `.agents/USER_REPORT.md` bug reports before continuing the
System Stability Overhaul. Triaged urgent stability reports into:

- Briefing: `.agents/plans/user_report_stability_hotfix_arena/00_problem.md`
- Domain analysis: `.agents/plans/user_report_stability_hotfix_arena/A_backend_cli_pipeline.md`
- Domain analysis: `.agents/plans/user_report_stability_hotfix_arena/B_plugin_pdf_popover.md`
- Review critique: `.agents/plans/user_report_stability_hotfix_arena/02_critique_plan_review.md`
- Revision response: `.agents/plans/user_report_stability_hotfix_arena/03_defense_revision.md`
- Master plan: `.agents/plans/02_user_report_stability_hotfixes.md`
- Evidence ledger: `.agents/plans/02_user_report_stability_evidence.md`

Updated `.agents/ROADMAP.md` urgent hotfix queue and emptied
`.agents/USER_REPORT.md` per triage rules.
User clarified: source badge may keep `Queued`/`Building...` but must not show
actionable Add Source after registration; Convert-to-LaTeX must remain LLM-backed
through the dedicated extractor; PDF reference lookup should follow sidechat's
local-first/backend-fallback policy. Plan was revised to address reviewer findings
on sanitizer placement, L2 English validation, `source rm` caller audit, L4 build
contract, and Arena file placement.

### Update (2026-06-25, Gemini)

**v0.25.1 Hotfixes**: Fully implemented, rigorously tested (60/60 tests passing in the affected domains, 1031/1031 across the backend), and audited by the PM (Gemini).
**PR Audit Findings**:
- Found and fixed 3 trivial nits: removed cosmetic blank lines in `vision.py`, stripped a dead `source_stem` parameter in `ingest_raw.py`, and corrected an inaccurate test docstring in `test_compile_pipeline.py`.
- The core architecture (balanced parenthesis scanning, ratio-based validation thresholds, L4 retry decoupling, and multi-stem cross-doc wikilink preservation) is logically sound and mathematically verified.

**Next Action**: The workspace is perfectly clean. We are ready to begin the main **System Stability Overhaul (Phase A Diagnosis)** as outlined in the roadmap.

### Immediate Next Action
- Gemini: Waiting for user approval to begin Phase A (Database Integrity & Concurrency Constraints analysis).
