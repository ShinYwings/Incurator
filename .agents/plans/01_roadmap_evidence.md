# System Stability Overhaul — Diagnosis Evidence Ledger

Date: 2026-06-23 (started) · 2026-06-27 (Phase A diagnosis complete)
Status: ACTIVE DELIVERY — all 19 module groups are diagnosed and consolidated.
Phase B is triaged into independently reviewable stability workstreams;
v0.37.0 composite-primary-key tombstones shipped in PR #98, v0.37.1
query-provider failure UX shipped in PR #99, and v0.38.0 Sidechat vault-page
wikilinks shipped in PR #100. Failure Atlas F9 authored-note topology is the
active v0.39.0 planning slice.
Master Plan: `.agents/plans/01_system_stability_overhaul.md`
Per-group detail: `.agents/plans/diagnosis/G01..G19-*.md` (the authoritative,
deep record). The sections below are the FIRST scan-pass (2026-06-23); the Phase
A Completion section at the bottom consolidates the full per-group results and
supersedes scan-pass estimates where they differ (e.g. DC-1).

This ledger records every diagnosis finding across the nine categories. Phase A
is closed; current delivery state lives in the Master Plan, ROADMAP, and RELAY.

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

---

## Phase A Completion (2026-06-27)

All 19 module groups are diagnosed. Each has a deep per-group report under
`.agents/plans/diagnosis/Gxx-*.md` (that is the authoritative record — the
scan-pass findings above remain for history). `INDEX.md` tracks per-group status;
every row is now `merged`.

### Consolidated severity tally (G01–G19)
- **S1 (must-fix): 10** · **S2 (should-fix): 118** · **S3 (nice-to-fix): 97**
- Source: `grep '### \[' .agents/plans/diagnosis/G*.md` by severity.

### S1 must-fix queue (Phase B P1) — completed before this handoff
1. **[G01-1]** (a/h) `remove_source` leaves orphans — never deletes `dag_edges`, `ingest_jobs`, `job_events` (IntegrityError / orphan rows).
2. **[G03-1]** (a) LWW/`since` uses `sources.last_ingested` (NULL for pending) → pending-source edits never sync / never export incrementally.
3. **[G04-1]** (a) Incremental-sync fast path is dead — DAG pages never carry a `content_hash` frontmatter key.
4. **[G06-1]** (d) ~230 lines of dead, unreachable code after an unconditional `return` in `run_query`.
5. **[G06-3]** (h) `_append_context_action` resets trace `created_at` on every expand/verify/feedback (timestamp + ordering corruption).
6. **[G07-1]** (a) `wiki config models use <ollama-model>` writes a legacy key stripped on load → active Ollama model never changes.
7. **[G11-4]** (a,h) `curate.yml` parser silently changes boolean and source-scope policy.
8. **[G13-4]** (h) OS sandbox grants every provider write access to every CLI state dir (cross-provider write).
9. **[G14-1]** (a,c,h) Context-build failure can leave a stuck streaming assistant turn.
10. **[G14-2]** (a,h,i) Manual continuation on an old assistant message renders into the last assistant bubble.

These 10 were verified against `CHANGELOG.md` and current tests/code on
2026-06-27. They are already fixed in the 0.25.4–0.25.8 release chain:

- 0.25.4: G11-4
- 0.25.5: G13-4
- 0.25.6: G14-1, G14-2
- 0.25.7: G01-1, G03-1, G04-1, G06-1, G06-3
- 0.25.8: G07-1

### New groups merged this session (G17–G19)

**G17 plugin-rest** (`auth/`, `zotero/`, `types.ts`, `settings.ts`, `main.ts`) —
12 findings, 0 S1. Highlights:
- (S2) Auth-status poll `setInterval` never cleared on settings-tab close → detached-DOM writes + repeated CLI probes (`fix/settings-auth-poll-cleanup`). **Fixed in `fix/phase-b-plugin-rest-cleanup`: auth poll timer is instance-owned and cleared on `hide()`/`display()`; settings source guard added.**
- (S2) Zotero "Reload Source" always uses `profiles[0]` → corrupts notes imported with another profile (`fix/zotero-refresh-profile-binding`). **Fixed in `fix/phase-b-plugin-rest-cleanup`: imports stamp `zotero_profile` in note frontmatter, reload resolves the matching profile first, and guide/spec docs describe the binding.**
- (S2) Global `window.open`/`shell.openExternal` monkeypatch teardown clobbers later plugins' patches (`fix/zotero-open-patch-identity-guard`). **Fixed in `fix/phase-b-plugin-rest-cleanup`: unload restores only when Incurator still owns the patched function, with source guard and guide updates.**
- (S2) `data.json` written from ~7 uncoordinated `saveData` call sites — no single writer (`refactor/plugin-settings-single-writer`). **Fixed in `fix/phase-b-plugin-rest-cleanup`: all settings `data.json` writes now flow through serialized `persistSettings()`, with a source guard and schema invariant.**
- (S3) Dead code: `startProviderLogin`/`providerLabel` (settings.ts), `normalizeExpiry` (cliAuth.ts). **Fixed in `fix/phase-b-plugin-rest-cleanup`: helpers removed with source guards.**
- (S3) `migrateUnavailableModelDefaults` hardcodes an unbounded model denylist already subsumed by the catalogue check. **Fixed in `fix/phase-b-plugin-rest-cleanup`: migration now resets unavailable models from the bundled catalogue check without a stale literal denylist.**
- (S3) Device-registry writers duplicate inline `require("path")`/sync mkdir logic. **Fixed in `fix/phase-b-plugin-rest-cleanup`: backend-command caching and Syncthing registry refresh share one async `writeDeviceRegistry` helper.**
- (S3) "Check DeepSeek API Key" command never checks — always throws the help notice. **Fixed in `fix/phase-b-plugin-rest-cleanup`: command now checks a saved plugin key or `DEEPSEEK_API_KEY`, with source guard and guide updates.**

**G18 docs-code-parity** — 4 findings, all docs-drift:
- (S2) **DC-1 CORRECTION**: the scan-pass "~47 MCP tools undocumented (92 vs 45)" is **stale/wrong**. Re-counted: 50 MCP tools are registered (48 `@mcp.tool()` + 2 `mcp.tool()(fn)`), and **all 50 are documented** in `MCP_USER_GUIDE.md`; EN/KR both list 45 `curator_*` names. MCP doc parity is healthy — close DC-1.
- (S2) `PLUGIN_SCHEMA §2.1 PluginSettings` interface omits 6 live persisted fields: `agentEffort`, `ollamaHost`, `autoSyncEnabled/OnLoad/Watch/Notify` (`docs/plugin-schema-settings-parity`). **Fixed in `chore/docs-surface-parity-guards`: schema interface/rules updated.**
- (S3) `wiki migrate` is a non-hidden CLI command absent from USER_GUIDE — document or mark `hidden=True`.
- (S3) No automated guard ties MCP-tool / plugin-settings surfaces to their docs (`test/docs-surface-parity-guards`). **Fixed in `chore/docs-surface-parity-guards`: `backend/tests/test_docs_surface_parity.py`.**

**G19 docs-redundancy** — 4 findings, no S1:
- (S2) `curate.yml` field reference duplicated across 6 guides + 2 specs, no canonical home (`docs/curate-yml-single-source`). **Fixed in `chore/docs-surface-parity-guards`: USER_GUIDE/USER_GUIDE_KR are the canonical usage reference with the structured KRS shape; WORKFLOW_GUIDE/WORKFLOW_GUIDE_KR now link to that reference instead of re-listing fields; parity guard added.**
- (S3) `wiki` lifecycle / CLI command reference triplicated (USER_GUIDE / WORKFLOW_GUIDE / PLUGIN_GUIDE) (`docs/cli-reference-single-source`). **Fixed in `chore/docs-surface-parity-guards`: USER_GUIDE/USER_GUIDE_KR now expose a stable `#cli-reference` anchor; WORKFLOW_GUIDE/WORKFLOW_GUIDE_KR and PLUGIN_GUIDE/PLUGIN_GUIDE_KR link to it for exact CLI flags/definitions instead of owning separate command contracts; parity guard added.**
- (S3) `failure_atlas/` mixes frozen test fixtures + a historical v0.7.0 handoff doc under `docs/specs/`, none linked from any index (`docs/failure-atlas-index-and-roles`). **Fixed in `chore/docs-surface-parity-guards`: added `docs/specs/failure_atlas/README.md` and a docs parity guard.**
- **Positive (verified)**: EN↔KR structural parity is healthy (PLUGIN_GUIDE H2 18/18, H3 25/26, code-fences 26/26; MCP H3 10/10) — the anti-compression guardrail is being honored, not violated.

### Active Phase B delivery

The historical G17–G19 cleanup listed here has shipped. Composite-primary-key
tombstones shipped in v0.37.0 / PR #98, query-provider failure UX shipped in
v0.37.1 / PR #99, and Sidechat vault-page wikilinks shipped in v0.38.0 /
PR #100.

The active v0.39.0 slice is canonical Failure Atlas F9. Planning verified that
schema v13 already has authored/extracted edge class, lifecycle, topology
weight, generation ownership, and source-span fields, but no compiler creates
authored relations. The existing F9 oracle also bypasses the real compiler.
The approved design must therefore re-pin the oracle, add deterministic
note-native extraction and cross-device identity, reconcile relations inside
successful generation publication, filter authoritative traversal to active
rows, and keep authored topology out of factual report support. Detailed
evidence lives in `.agents/plans/02_authored_note_topology_evidence.md`.
