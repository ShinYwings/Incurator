# v0.36.8 Master Implementation Plan

Date: 2026-07-30
Status: APPROVED — existing contract restoration; user supplied the expected output.

## 1. Objective

Restore PDF **Convert to LaTeX** under Antigravity so the clipboard contains the
selected prose faithfully and converts its mathematics to Markdown LaTeX,
instead of accepting Antigravity scratch-agent planning narration as a
successful transcription.

Definition of done: the exact reported failure reproduces before the code change,
the corrected live `wiki plugin pdf transcribe` call returns original text plus
LaTeX, and all required docs/tests/release gates pass.

## 2. Explicit Non-Goals

- No PDF annotation or geometric crop-selection redesign.
- No new model/effort configuration fields.
- No change to `latex_extract_model → vision_model → main-if-vision`.
- No content-specific filtering of “I will” or scratch filenames.
- No refactor of the other provider clients.

## 3. Strict Quality Conditions & Release Gates

- The full prompt is the exact argument following `agy --print`.
- `--model` carries the selected model.
- `--effort` uses an explicit setting when present, otherwise the catalogue
  default for a model that declares efforts; no-effort models omit it.
- Existing timeout, log, quota, and error contracts remain intact.
- Focused pytest fails on the old code and passes on the fix.
- Full `pytest`, `ruff`, `mypy`, plugin `vitest`, and plugin build pass.
- Testbed status/lint and a live Antigravity transcription pass.
- English docs are updated first, then Korean counterparts.
- All manifests agree on `0.36.8`; changelog records the hotfix.

## 4. Locked Design Decisions (Arena Consensus)

- Fix the shared backend Antigravity transport, not the clipboard layer.
- Use the installed CLI's documented prompt/model/effort arguments.
- Reuse `models.get_default_effort()`; do not add configuration.
- Preserve the existing interactive prompt and normalization contract.
- Treat this as a patch release because it restores documented behavior without
  adding a public capability or schema.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: rendered-region image cropping and provider-independent
  constrained decoding remain outside this hotfix.
- **Stop condition**: stop if passing the prompt as `--print` breaks a backend
  prompt above the existing 18,000-character client budget.
- **Stop condition**: stop if live validation requires changing user auth or
  broadening filesystem permissions.

## 6. Evidence Ledger

- Reproduction and rollback details:
  `.agents/plans/02_latex_transcribe_hotfix_evidence.md`.
- Current schema remains v12 and is unaffected.
- Worktree was clean before branch creation.
- Rollback is a normal revert of this isolated hotfix; there are no data changes.

## 7. Execution Phases

- **P0 — Research & measured baseline**
  - Record the failing command/output and installed `agy` contract.
  - Verify corrected direct CLI syntax.
- **P1 — Contract specification**
  - Update `SYSTEM_BEHAVIOR`, `PLUGIN_SCHEMA`, and EN/KR plugin guides.
- **P2 — TDD**
  - Add failing backend command-construction and interactive transcription tests.
- **P3 — Core logic**
  - Correct `AntigravityCliClient._run()` prompt/model/effort forwarding.
  - Verify focused pytest and Ruff before proceeding.
- **P4 — Integration**
  - Re-run the live testbed transcription and confirm normalized JSON.
- **P5 — Release gates**
  - Run full backend/plugin CI and testbed smoke.
  - Bump `0.36.8`, update changelog, clean roadmap/report/plan artifacts, create
    the release commit, push, and open the PR.
