# System Stability Overhaul — Diagnosis Evidence Ledger

Date: 2026-06-23
Status: IN PROGRESS — Phase A diagnosis (diagnosis-only, NO refactoring)
Master Plan: `.agents/plans/01_system_stability_overhaul.md`

This ledger records every diagnosis finding across the nine categories. It is
built incrementally with loop-until-dry per module (a module is "closed" only
when a re-pass surfaces nothing new). When complete → STOP for user triage
(fix-now vs. defer), which sequences the fix PRs.

## Finding categories
- **(a)** correctness bugs
- **(b)** redundancy / duplication
- **(c)** error-handling smells (broad-except masking)
- **(d)** legacy / dead / compat-shim code
- **(e)** architectural debt (god-files, coupling)
- **(f)** docs↔code drift & docs redundancy
- **(g)** performance hotspots (RAG retrieval, DAG build)
- **(h)** robustness / weaknesses (races, failure modes, edge cases)
- **(i)** UI/UX friction

## Severity
- **S1** correctness/data-loss/security — must fix
- **S2** stability/perf/robustness — should fix
- **S3** maintainability/redundancy/docs — nice to fix

---

## 0. Baseline (rollback anchor)

| Check | Result (2026-06-23) |
|---|---|
| `ruff` | ✅ clean |
| `mypy` | ✅ clean (97 files) |
| `pytest` | _(running — recorded below)_ |
| `vitest` | _(to confirm)_ |
| Backend LOC | 44,149 (Python) |
| Plugin LOC | 22,463 (TS, excl. tests) |
| Tests | 116 pytest files + 58 vitest files |

God-file LOC (architectural-debt targets):
`cli.py` 7389 · `db.py` 4679 · `mcp_server.py` 3362 · `ingest_raw.py` 2346 ·
`llm.py` 1740 · `lint.py` 1539 · `prompts.py` 1152 · `context_service.py` 1121 ·
`sync.py` 1089 · `plugin_api.py` 1022 · `chatSidebar.ts` 4828 · `llmClient.ts` 2282 ·
`externalPdfView.ts` 1872 · `incuratorDashboardModal.ts` 1431.

Smell counts: 264 broad-`except` (backend) · 83 `any`/`as any`/`@ts-ignore` (plugin).

---

## Findings

> Format: `### [ID] (cat) Sxx — Title` · **Loc** · **Evidence** · **Fix sketch** ·
> **Blast** · **PR**. Coverage note: this is the FIRST scan-level pass
> (grep + spot-read). Per-finding deep verification continues at fix-time;
> module groups stay open under loop-until-dry until a re-pass finds nothing new.

### Cross-cutting (error-handling, legacy, robustness) — scan done, open

#### XC-1 (c) S2 — Silent broad-except concentration masks failures
- **Loc**: `mcp_server.py` ~48 · `llm.py` 16 · `cli.py` 16 · `ingest_raw.py` 12 ·
  `config.py` 10 (`except …: pass`-style). 264 broad-except total backend-wide.
- **Evidence**: e.g. `ingest_raw.py:155` `except Exception: pass` swallows
  source-path resolution errors → silent fallback to original `source`.
- **Fix sketch**: root-cause pass — narrow to specific exceptions, log+surface,
  delete bug-masking swallows. Keep the few intentionally-defensive ones (those
  already carry a justifying comment, e.g. "must never break instant L1").
- **Blast**: wide but per-site isolated. **PR**: grouped `refactor/error-handling-*`.

#### XC-2 (d, methodology) S3 — "legacy/retired" keyword is overloaded
- **Loc**: `db.py` 54 marker hits.
- **Evidence**: most are the ACTIVE `retired_at` lifecycle column / "legacy
  verified units" data-migration vocabulary — NOT dead code.
- **Fix sketch**: legacy sweep MUST be reachability/usage-audit driven, never
  grep-and-delete. Recorded as a hard constraint for the sweep phase.
- **Blast**: n/a (prevents false-positive deletions). **PR**: n/a (guardrail).

#### XC-3 (d) S3 — Retired URI schemes + dual QueryResult compat shim
- **Loc**: `query.py:35-40` `_LEGACY_SCHEME_RE` (strips retired `legacy://` /
  `qmd://`); `query.py:404` maps `QueryResultV031` → legacy `QueryResult`.
- **Fix sketch**: verify no on-disk data / index still emits these schemes, then
  drop the regex + collapse the dual result types. **Blast**: query output path.
- **PR**: `refactor/legacy-sweep-query`.

#### XC-4 (h/i) S2 — Timing/race & observability signals (plugin)
- **Loc**: 32 `setTimeout`/`setInterval`, 26 `console.*` in plugin src.
- **Evidence**: diff-viewer already had a documented race history (v0.14.1).
- **Fix sketch**: audit each timer for ordering assumptions; route console.* to a
  gated logger. **Blast**: UI behavior. **PR**: `fix/harden-*`, `fix/ux-*`.

### Module group: ingest pipeline — scan done, open

#### ING-1 (e/d/g) S3 — `ingest_orchestrator.py` is a 35-line remnant
- **Loc**: `ingest_orchestrator.py` (whole file).
- **Evidence**: docstring states the v0.2.x batch-L2 machinery was removed in
  v0.3.1; only `_expand_downstream_via_sql` (BFS over `dag_edges`) remains,
  consumed by `sync`. The BFS issues one SQL query PER node (`SELECT to_id …
  WHERE from_id=?` in a `while queue` loop).
- **Fix sketch**: inline the fn into `sync.py`/`db.py`; replace per-node queries
  with a recursive CTE (perf). **Blast**: sync downstream expansion. **PR**:
  `refactor/backend-ingest-orchestrator`.

### Module group: DB & sync — scan done, open

#### DB-1 (positive) — batching is healthy, keep
- `db.py` uses `_chunked` 900-row IN-clause batching (e.g. :973, :2095) — NOT
  naive N+1. No change; documented so the refactor preserves it.

#### DB-2 (e) S2 — `db.py` 4679-LOC god-file
- **Loc**: `db.py`.
- **Evidence**: schema DDL + idempotent migrations (`_add_column_if_missing`) +
  repository queries + lifecycle reconciliation all in one module.
- **Fix sketch**: split into `db/schema.py` (DDL+migrations), `db/repository_*`
  (queries by entity), keep `connect()` shared. Characterization tests first.
- **Blast**: very wide (imported everywhere). **PR**: several `refactor/backend-db-*`.

### Module group: retrieval / query / search — scan done, open

#### RT-1 (positive/g) S3 — engine batches well; perf needs a harness first
- **Evidence**: `retrieval/engine.py` batches reranker scoring + RRF fusion; no
  per-item LLM-in-loop spotted. No perf infra exists (no pytest-benchmark).
- **Fix sketch**: build the benchmark harness (reuse Failure Atlas fixture
  corpus/qrels) BEFORE optimizing, so hotspots are measured not guessed.
- **PR**: `perf/rag-benchmark-harness` (first perf PR).

### Module group: CLI & MCP — scan done, open

#### CM-1 (e) S2 — top backend god-files
- **Loc**: `cli.py` 7389 (94 `@command`s) · `mcp_server.py` 3362 (92 tools).
- **Fix sketch**: decompose by command-group / tool-group (typer sub-apps;
  tool modules registered into the server). Prior-art: typer/click multi-file
  apps. **Blast**: CLI + MCP surface (contract-preserving). **PR**: many
  `refactor/backend-cli-*`, `refactor/backend-mcp-*`.

### Module group: plugin agent / UI — scan done, open

#### PL-1 (e) S2 — plugin god-files + type escapes
- **Loc**: `chatSidebar.ts` 4828 · `llmClient.ts` 2282 · `externalPdfView.ts` 1872 ·
  `incuratorDashboardModal.ts` 1431. `any`/`@ts-ignore`: dashboard 28, llmClient
  16, chatSidebar 14.
- **Fix sketch**: decompose per surface into cohesive modules; replace `any` with
  real types. **PR**: per-file `refactor/plugin-*`.

### Module group: LLM & prompts — pending deeper pass
- `llm.py` 1740 (16 silent excepts) · `prompts.py` 1152 · `prompting/`. Prompt-v2
  cross-model consistency lives here (see Master Plan). Deep pass pending.

### Docs↔code consistency — scan started, open

#### DC-1 (f) S2 — ~47 MCP tools undocumented
- **Evidence**: 92 MCP tools registered in `mcp_server.py` vs 45 named in
  `MCP_USER_GUIDE.md`. **Fix sketch**: reconcile guide + `_KR.md` to full tool
  set (or intentionally mark internal-only). **PR**: `docs/reconcile-mcp`.

#### DC-2 (f) S3 — large specs need section-level drift/redundancy audit
- 15.6k LOC docs; `SYSTEM_BEHAVIOR.md` 2729, `SCHEMA.md` 2241, `PLUGIN_SCHEMA.md`
  1852. Section-by-section drift + cross-doc duplication audit pending (detailed
  pass). Anti-compression guardrail applies (CLAUDE.md #6).
