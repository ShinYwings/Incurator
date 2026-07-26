# v0.36.7 Master Implementation Plan

Date: 2026-07-26
Status: APPROVED 2026-07-26 — implementation and validation complete.

## 1. Objective

Stop intermittent Obsidian Agent `jetski/read_file` failures caused by running an
older in-memory plugin after a newer bundle is installed, and make every eligible
open Markdown/PDF tab visible in the context-chip UI without automatically
sending hidden tabs to the model.

Definition of done:

- provider launch is blocked with a reload action whenever the active and
  installed plugin build identities differ;
- the update action performs a real reload after a complete copy;
- every eligible open tab has a stable chip;
- visible splits default eye-on, hidden tab-group leaves default eye-off;
- only eye-on/pinned tabs contribute to any prompt block;
- the narrow `$read_file$()` rule, `--add-dir`, and OS sandbox contracts remain
  intact;
- docs, tests, local CI, live Obsidian validation, and v0.36.7 release metadata
  are complete.

## 2. Explicit Non-Goals

- No `--dangerously-skip-permissions`.
- No approval of write, shell, network, or wildcard tools.
- No automatic PDF registration/ingest from passive tabs.
- No DB schema, MCP/CLI contract, or data migration.
- No automatic inclusion of all hidden tab bodies.
- No changes to user-authored `03_Notes/` or external PDFs.
- No refactor outside plugin update/context boundaries.

## 3. Strict Quality Conditions & Release Gates

- Existing Antigravity settings are losslessly preserved; malformed settings
  remain fail-closed.
- A partial plugin artifact copy never initiates reload.
- Runtime/disk mismatch fails before provider/credential startup.
- Four content leaves in the measured workspace yield four eligible chip
  identities, while only visible leaves enter the default prompt.
- Hidden eye-off tabs are absent from tab lists, bodies, outlines, continuity,
  and edit-target blocks.
- `npx vitest run -c ./plugin/vitest.config.ts` passes.
- `scripts/backend-check pytest`, `ruff`, and `mypy` pass even though backend
  behavior is unchanged.
- Plugin production build and version-consistency tests pass.
- `complex_math_backprop` remains the active testbed scenario; its non-mutating
  status/lint gates pass.
- A live Obsidian reload followed by the previously failing PDF question creates
  or preserves the narrow permission rule and produces an answer without a
  permission denial.

## 4. Locked Design Decisions (Arena Consensus)

- Treat permission activation and tab discovery as separate root causes.
- Keep the v0.36.4 atomic permission merger and invocation-time sync.
- Compare existing build fingerprints when available; use manifest version as a
  fallback. Do not infer active code from the on-disk manifest alone.
- Block generation while reload is required.
- After all required artifacts copy successfully, turn the update action into a
  supported whole-renderer reload action.
- Enumerate all eligible open Markdown/PDF leaves with `isVisible`.
- Render all unique context keys; visible defaults eye-on, hidden defaults
  eye-off.
- Prompt assembly consumes only included/materialized tabs.
- Context key: `(view type, portable source/file identity, page when present)`.
- Preserve different PDF pages; dedupe exact duplicate keys.
- Refresh on layout/tab lifecycle as well as active-leaf changes.
- Release classification: patch v0.36.7, with `Fixed` changelog entries only.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions:** provider error UX queue, chat compaction, schema milestones,
  general updater redesign, and unrelated plugin UI cleanup.
- **Stop Conditions:**
  - stop if Obsidian exposes no supported renderer reload command;
  - stop if a hidden external PDF cannot expose a portable identity without
    persisting an absolute path;
  - stop if tests show all-open-tab discovery requires auto-transmitting hidden
    content;
  - stop if any change would weaken the OS sandbox or approve broader tools.

## 6. Evidence Ledger

- **Current Repository & Schema Reality:** plugin-only internal behavior; SQLite
  and all DAG schemas are untouched.
- **Current Dirty Worktree:** only triage/plan/relay files created by this task.
- **Rollback Requirements:** branch
  `hotfix/v0.36.7-agy-open-tab-context`, rollback anchor `45cd97f`; no production
  data writes.
- Detailed measured facts are in
  `.agents/plans/07_roadmap_evidence.md`.

## 7. Execution Phases (Follow TDD and CI at each phase)

- **P0 — Research & Measured Baseline**
  - Preserve process/bundle/settings timestamps, live failed-turn evidence,
    open-leaf/chip counts, and targeted test baseline.
  - Verify the active scenario is `complex_math_backprop`.
- **P1 — Contract Specification**
  - Update English source docs first:
    `docs/guides/PLUGIN_GUIDE.md`,
    `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`, and
    `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`.
  - Faithfully synchronize `docs/guides/PLUGIN_GUIDE_KR.md`.
  - Specify activation guard and open/visible/included tab semantics.
- **P2 — Failing Tests**
  - Add plugin tests for runtime/disk mismatch, complete-copy reload gating,
    all-leaf discovery, visibility defaults, prompt exclusion, explicit include,
    tab lifecycle refresh, context-key dedupe, and PDF-not-ready fallback.
  - Retain and extend permission-preservation and blanket-bypass regression
    tests only where evidence requires.
  - Verify targeted tests fail for the intended current behavior.
- **P3 — Bundle Activation Implementation**
  - Implement pure build-identity comparison.
  - Block sidechat provider launch on mismatch with an actionable reload error.
  - Make the update banner's post-copy action perform the supported renderer
    reload only after all required artifacts copy.
  - Strengthen `setup.sh` reload wording without mutating CLI settings.
- **P4 — Open-Tab Context Implementation**
  - Add visibility metadata and enumerate all eligible leaves.
  - Render hidden identity chips eye-off.
  - Introduce a session-local inclusion override and materialize only included
    contexts.
  - Gate every prompt consumer and refresh on layout/tab lifecycle.
- **P5 — Local And Live Validation**
  - Run targeted tests after each phase, then full plugin/backend/static checks.
  - Build/deploy the plugin.
  - Reload live Obsidian once, confirm runtime/disk build parity, confirm all
    eligible tabs/chips and eye defaults, and rerun the failed PDF question.
  - Run non-mutating `complex_math_backprop` testbed status/lint validation.
- **P6 — Release**
  - Bump backend/plugin manifests to 0.36.7; patch bump leaves v0.36 spec-title
    lines unchanged.
  - Update `CHANGELOG.md`.
  - Remove implemented plan artifacts, clean roadmap item, and update relay.
  - Commit incrementally, finish with `chore(release): v0.36.7`, push, and open a
    detailed PR.
