# Briefing: Deep System-Defect Audit → Consolidated Stability Batch

Date: 2026-08-04 | Author: Main agent (Claude Code)
Status: Arena briefing for multi-inspector diagnosis + batch plan synthesis.

## Mission

Run a deep, adversarially-verified system diagnosis of Incurator (v0.41.0,
master @ `521b420`), then synthesize ONE consolidated Master Plan that merges:

- the new audit findings (below),
- ROADMAP item 1 — regression-audit plan `02_v032_regression_audit.md` **P10**
  (P9 dry passes were executed 2026-08-04; P10 = fix batches + closure),
- ROADMAP item 2 — `01_system_stability_overhaul.md` remaining workstreams
  (prompt architecture v2, safe decomposition + exception hardening, measured
  performance, existing-surface UX).

## Ground Rules (all inspectors and critics)

1. **Read-only.** Do NOT modify any code, test, doc, or config. Your ONLY
   writes are your own arena document in this folder.
2. Never touch `testbed/`, any production vault, or `.cache/` state. Never run
   `wiki` commands that mutate state. Do not rerun the consumed D2 holdout.
3. Every finding needs `file:line` evidence read from the actual repo at
   `/Users/shin/shinywings/Incurator`. Claims without direct code evidence are
   inadmissible.
4. Before reporting a defect, check `backend/tests/` / plugin `*.test.ts` —
   if an existing test already pins the correct behavior, your claim is wrong
   or needs a sharper failure scenario.
5. Specs are authoritative: `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`,
   `docs/specs/curator_schema/SCHEMA.md`, `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`,
   `docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md`. Spec-vs-code divergence
   is a finding even when the code "works" (both are wrong until reconciled).
6. Severity rubric: P0 = data loss/corruption or serving wrong knowledge;
   P1 = user-visible breakage with no workaround; P2 = contract violation,
   silent degradation, or edge-case breakage with workaround; P3 = hygiene/doc
   drift. Max 8 findings per inspector — prioritize depth over breadth.

## Baseline Update (2026-08-04, after v0.42.0 merged)

The repo is now at **v0.42.0** (master `1ca26f0`). The items below are ALREADY
FIXED and merged — do NOT report them again:

- Deferred-view crash: `main.ts` narrowed external-PDF leaves on the view-type
  string and called `getRuntimePath()`, throwing from `getLeafFile()` and taking
  the context pins, sidechat Send, and the popover down together. Fixed via the
  capability guard `asLoadedExternalPdfView` (PLUGIN_SCHEMA §1.4.1).
- PDF.js canvas collision: per-page render tasks are now cancelled and awaited
  before the next render claims the reused canvas (PLUGIN_SCHEMA §1.4.2).
- Version checking now reads `build.backend_version` only; installed package
  metadata is no longer consulted at all (SYSTEM_BEHAVIOR §11.2.1).
- `setup.sh` provisions the `wiki` alias idempotently with PATH-conflict
  warning (SYSTEM_BEHAVIOR §11.2.1).
- Popover shows elapsed seconds during long provider waits
  (PLUGIN_SCHEMA §1.4.3).

**Measured performance facts (do not re-derive, and do not propose work that
ignores them):** a CLI provider round-trip (`agy --print`) costs 8.2–12.2 s and
is flat across model and effort; the CLI binary starts in 0.29 s; an Incurator
backend round-trip is 0.20 s; a warm local Ollama round-trip is 0.26–0.32 s.
The dominant latency is the provider service handshake, which Incurator cannot
shorten. Micro-optimizing Incurator-side paths that are already sub-second is
NOT a useful finding.

## Already-Confirmed Findings (do NOT re-report; deepening/superseding is allowed)

- CAND-01 [P2] `lint.py:1326-1329` — `wiki lint --fix` swallows
  `search.update_index` failure with bare `except Exception: pass`; violates
  SYSTEM_BEHAVIOR §32 observable-degradation contract.
- CAND-02 [P3] `llm_identity.py:60,89` — broad `except Exception: pass` without
  reason/logging (account-display fallback).
- CAND-03 [P2] `db_sync.py::_archive_conflict` — `Path.rename` from vault
  `.curator/sync/` to repo-cache `runtime/sync_conflicts/` fails permanently
  (EXDEV) when vault and repo cache are on different filesystems; autosync then
  fails on every retry, contradicting §13.1 "retry is safe".
- CAND-04 [P2] `retrieval/evidence.py::_build_locator` AND
  `context_service.py::_locator_from_span` — locator_status derived from DB
  metadata only; `exact` fabricated without file existence/heading verification;
  `duplicate_anchor`/`stale`/file-level `unavailable` never emitted; `block_id`
  always None. Violates §29.3/§29.4, SEARCH_ENGINE_SCHEMA §12.2, §31.5.
- CAND-05 [P3] SCHEMA §7 MCP payload examples stale vs `mcp/server.py`
  (`l4_complete`/`relpath`/`source` missing; `ok` wrapper and
  `deepseek`/`ollama` provider keys missing).
- CAND-06 [P2] `plugin/src/ui/chat/ChatSidebarView.ts:1868` — sidechat always
  passes the vault ROOT as `workspacePath`; no ancestor `curate.yml` binding
  anywhere in the plugin, so workspace KRS curation is inert for the entire
  chat surface; misleading comment; root-level curate.yml would silently bind.

## Enhancement Candidates Already Recorded (context, not defects)

ENH-01 incremental L4 synthesis (wholesale regen today —
`pipeline/synthesis.py:10,145`); ENH-02 PPR local expansion; ENH-03 DRIFT-style
explore; ENH-04 passive related-concepts sidebar; ENH-05 community-hierarchy
dashboard view.

## Inspector Domains

1. `compile_pipeline` — `backend/src/curator/pipeline/*`, `ingest_llm.py`,
   `ingest_orchestrator.py`, `ingest_worker.py`: staged generations (§26.3),
   reconciliation (§26.4/§27.8), publish gates, zero-unit publish, temp-id
   reconcile, projection recovery, L2 no-partial-publish (§6.1), terminal
   layer statuses (§4.1).
2. `sync_db` — `db_sync.py`, `db/*`, `durable_io.py`, `secret_store.py`:
   LWW/tombstones (§13.1), composite codec (§11.17/SCHEMA), conflict files,
   fail-closed state (§13.3), atomic config writes (§11.1), portability edges
   (cross-filesystem, clock skew, second-precision timestamps).
3. `retrieval_context` — `retrieval/*`, `context_service.py`, `search.py`,
   `query.py`: degradation contracts (§12.2/SEARCH_ENGINE §8), policy
   enforcement (§28), locators (§29), RTR/QTR tracing (§30), ContextService
   budget/snapshot/expand (§31), explore route (§31.8).
4. `plugin_lifecycle` — `plugin/src/**`: provider lifetimes/cancellation
   (PLUGIN_SCHEMA §1.4), session/secret stores (§2.2), tool policy profiles +
   CLI sandbox (§13.5-13.7), language bridge (§11/13.2), PDF context flows
   (§6), MCP client dispatch, update/reload gate.
5. `exception_hygiene` — repo-wide §32 sweep (backend + plugin): swallowed
   exceptions, false success, silent maintenance skips, missing warnings
   surfaces, and *its plugin-side equivalents* (empty catch blocks, dropped
   promise rejections).
6. `docs_parity` — spec/guide claims vs code for surfaces NOT covered above:
   CLI surface policy (§11.4), MCP tool list vs MCP_USER_GUIDE, EN↔KR guide
   sync sampling, WORKFLOW/USER guide command accuracy, README/setup accuracy.

## Debate Protocol

Per domain: the inspector writes `01_proposal_<domain>.md`; a red-teamer then
writes `02_critique_<domain>.md` attempting to REFUTE every finding (wrong
line? already tested? misread spec? not reachable? wrong severity?). Only
findings surviving critique enter the Master Plan. The synthesizer writes
`03_synthesis.md` proposing batch groupings and the ROADMAP merge.
