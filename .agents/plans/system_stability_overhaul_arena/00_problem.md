# Briefing: System-Wide Stability, Diagnosis & Refactoring Overhaul

Date: 2026-06-22 | Historical planning branch:
`feature/prompt-architecture-refactoring` (closed; current delivery branches
start from `master`)

## 1. Core Problem Definition

The user has mandated a comprehensive, system-wide effort to raise stability by
**deeply diagnosing the entire codebase** (bugs, refactoring opportunities,
redundancy) and **refactoring it well**. This supersedes the original
prompt-only milestone and absorbs it.

Locked scope decisions (from user, 2026-06-22):

1. **Breadth**: EXHAUSTIVE — the whole codebase (44.1k LOC backend Python + 22.5k
   LOC plugin TS), not just hotspots.
2. **Refactoring boundary**: ARCHITECTURAL REDESIGN ALLOWED — god-file
   responsibility re-partitioning and module-boundary redesign are in-scope, not
   only behavior-preserving cleanups.
3. **Execution**: SEQUENTIAL SINGLE-AGENT — the main agent drives diagnosis →
   plan → fix one hotspot at a time (no multi-agent workflow fan-out). Chosen for
   context coherence and control.
4. **Prompt architecture REDO**: redo/redesign the prompt architecture (already
   partially shipped in commit `ac46f1d` — shared `promptRegistry.ts`) with a new
   primary goal: **minimize output divergence across multiple model tiers**
   (Claude / Gemini / OpenAI / Ollama / DeepSeek) so behavior is consistent.
5. **Legacy cleanup**: identify and remove legacy files / dead code / retired
   compat shims across the system.

## 2. Measured Baseline (Evidence — 2026-06-22)

- `ruff` ✅ clean. `mypy` ✅ clean (97 source files). Tests: 116 pytest files +
  58 vitest files.
- **God-files (architectural debt hotspots)**:
  - Backend: `cli.py` 7,389 · `db.py` 4,679 · `mcp_server.py` 3,362 ·
    `ingest_raw.py` 2,346 · `llm.py` 1,740 · `lint.py` 1,539 · `prompts.py` 1,152.
  - Plugin: `chatSidebar.ts` 4,828 · `llmClient.ts` 2,282 ·
    `externalPdfView.ts` 1,872 · `incuratorDashboardModal.ts` 1,431.
- **Error-handling smell**: 264 broad `except Exception/except:` in backend —
  candidate Root-Cause-Over-Workarounds violations that can mask bugs.
- **Type-escape smell**: 83 `any` / `as any` / `@ts-ignore` in plugin source.
- **Legacy is embedded, not orphaned**: legacy lives as in-file compat paths, not
  standalone dead files — e.g. `query.py::_LEGACY_SCHEME_RE` (retired
  `legacy://` / `qmd://` schemes), `config.py` backward-compat aliases,
  `model_setup.py` `legacy_model`. Blind file deletion is unsafe; removal must be
  driven by a real reachability/usage audit.

## 3. Constraints & Success Criteria

- Every phase MUST keep `ruff` + `mypy` + `pytest` + `vitest` green before the
  next phase starts (CLAUDE.md Step 8). No phase ships red.
- Architectural refactors of god-files MUST be guarded by characterization tests
  written BEFORE the refactor, so behavior parity is provable.
- Prompt v2 success is **measurable**: a cross-model consistency harness shows
  reduced output-shape divergence vs the current baseline.
- Legacy removal MUST cite the audit evidence proving the path is dead/safe.
- Docs (`docs/specs/`, `docs/guides/` + `_KR.md`) updated in lockstep per phase.
- Anti-mega-PR: one coordinated milestone, but delivered as a SEQUENCE of
  independently-reviewable sub-release PRs — never one monolithic diff (this is
  the explicit cure for the "code-first → revert-then-replan" anti-pattern in
  CLAUDE.md).

## 4. Open Risks for the Arena to Resolve

- How to bound an "exhaustive" audit so it terminates (loop-until-dry criteria).
- Version strategy: one big minor vs. a chain of minors (0.25 → 0.26 → …).
- Ordering: prompt-v2 first (user-visible win) vs. diagnosis-ledger first
  (de-risks everything else).
- How aggressive the god-file split should be without destabilizing the DAG
  pipeline and MCP contracts.
