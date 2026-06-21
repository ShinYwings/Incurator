# v0.22.0 Master Implementation Plan — Dedicated PDF-extraction (VLM) model

Date: 2026-06-21
Status: APPROVED (direction + branch strategy) — Arena concluded. Implementation
proceeds on the EXISTING branch `feature/chat-decay-quick-wins`; PR #45 grows to a
single combined `v0.22.0` release. P1 (spec §26 change) STOPs for approval before code.
Arena record: `.agents/plans/pdf_vlm_extraction_arena/`

**Branch strategy (user decision 2026-06-21):** No merge-first. Because `latexModel`
(v0.21.0) is NOT yet released (PR #45 unmerged), it is reshaped IN PLACE into the
vision-model flow — nothing to migrate or "retire." The chat-decay + Zotero work
already on this branch ships together with the VLM feature as one `v0.22.0`.

## 1. Objective

Introduce **two dedicated, separately-selectable extraction models**, both decoupled
from the Incurator main LLM, matched to the two distinct tasks (full-page layout vs
region OCR):

- `llm.vision_model` — **heavy, layout-aware** full-page model.
- `llm.latex_extract_model` — **light/cheap region-OCR** model;
  empty → falls back to `vision_model` → falls back to current main-model vision.

Wired to:

1. **`add source` PDF ingest** — when `vision_model` is set, every PDF is transcribed
   page-by-page into Markdown with proper LaTeX (`$…$`/`$$…$$`), becoming L1; empty =
   today's pymupdf4llm path. (Decision A: always-on when configured.) Ingest uses
   `vision_model` ONLY (never the light model).
2. **Dashboard** — TWO rows ("PDF ingest model (full-page)" and "LaTeX/region extract
   model (light)"), vision-capable dropdowns, the light row showing its effective
   resolved model when empty; persisted to backend config via `wiki config`.
3. **`Cmd+Shift+X`** snip and **right-click Convert-to-LaTeX** — transcribe the region
   **image** via `latex_extract_model` (→ `vision_model` → main vision). The
   unreleased v0.21.0 text `latexModel` is reshaped in place into
   `latex_extract_model` (Decision B revised: two slots + fallback).

**Definition of done**: with `vision_model` set, `add source` on a math PDF produces
L1 Markdown whose central formulas are valid LaTeX; the Dashboard shows/sets both
models with a visible fallback; Cmd+Shift+X and Convert-to-LaTeX use the light model
(or its fallback); with both slots empty, behavior equals v0.21.0 minus the removed
`latexModel` field.

## 2. Explicit Non-Goals

- NOT removing pymupdf4llm — it remains the default and the per-page fallback +
  structural/ToC/image source.
- NOT auto-detecting math regions (no heuristic gate) — always-on or off.
- NOT making VLM L1 unconditional ground truth — parser text is retained for audit
  and formula cross-check (no silent trust).
- NOT a general per-task model registry — exactly two slots, scoped to PDF/region
  extraction.
- NOT making `latex_extract_model` a page-grade parser — it is region/equation-grade;
  ingest never borrows it.
- NOT changing the chat answer model — only the *extraction* of PDF/crop content
  moves to the dedicated models.
- NOT adding direct vision-API clients / provider API keys. Cloud backend vision
  goes through the existing CLI **subscription** auth via the agentic-CLI
  file-path→Read approach (no API keys). A provider that fails the P0 image-read
  test stays text-only and is excluded from the ingest-model dropdown.
- NOT adding poppler/`pdf2image`/Ghostscript — PyMuPDF `get_pixmap` is the optimal
  PDF→image path (chosen on merit, not dependency-avoidance).

## 3. Strict Quality Conditions & Release Gates

- Both-slots-empty path is a strict no-op vs v0.21.0 (minus `latexModel`): existing
  ingest + `parser_used="pymupdf4llm"` and current snip behavior unchanged; tested.
- `vision_model` set → `parser_used="vlm"`; per-page VLM failure/timeout falls back
  to pymupdf4llm text for that page (ingest never hard-fails).
- A configured-but-bad model (text-only / unreachable / auth-fail) in EITHER slot
  **RAISES and halts** — it does NOT silently fall through to the next model (R13).
  Fall-through happens ONLY for an empty slot. Asserted by test (configured-failure
  raises; empty-slot falls through).
- **Ingest never selects `latex_extract_model`** (R10) — asserted by test.
- Interactive resolve order `latex_extract_model → vision_model → main-vision` (on
  EMPTY slots) is unit-tested; the Dashboard light row renders the effective
  fallback model.
- Per-page VLM cache key includes the resolved model (R12): a model switch
  re-extracts; same-model rebuild is a cache hit. Asserted by test.
- Page renders are bounded: ≤ `vision_max_image_px` longest edge at
  `vision_render_dpi` (R14); a dense/large page never exceeds the cap. Asserted by test.
- **Temp PNG location + cleanup (user requirement)**: temp PNGs live under the
  project cache `<repo>/.cache/vision_render/<run-id>/` (NOT system `/tmp`; `.cache/`
  is gitignored), and are deleted in a `finally` — guaranteed on success, exception,
  AND timeout; the per-run subdir is removed wholesale at run end and stale dirs are
  swept on startup. No temp PNG survives the run. Asserted by test on both success
  and failure paths.
- Cloud vision uses CLI **subscription** auth (no API keys); Ollama path is
  in-memory base64 (no disk). Pipeline renders + transcribes pages with bounded
  concurrency (not sequential).
- Per-provider **output normalization** strips `$$` wrappers / codex banners +
  "tokens used" lines / code fences / commentary so L1 is clean LaTeX. Asserted by
  test with captured real-CLI output samples. No unsafe auto-approve flags are ever
  passed to the CLIs.
- Backend `pytest` + `ruff` + `mypy` green; plugin `vitest` + `tsc` green.
- Testbed smoke: `VAULT_ROOT=testbed wiki add` a math PDF with a (simulated/real)
  vision model → L1 shows LaTeX; without → pymupdf4llm path.
- All three manifests `0.22.0`; four spec titles `v0.22`; `test_spec_sync` green.
- Docs (EN first, then `_KR`): SYSTEM_BEHAVIOR §26 revision, SCHEMA both slots +
  fallback + `parser_used:"vlm"`, PLUGIN_SCHEMA settings + two Dashboard rows,
  USER/WORKFLOW/PLUGIN guides, and the `latexModel`→`latex_extract_model` reshape.

## 4. Locked Design Decisions (Arena Consensus)

1. **Config (two slots)**: first-class `llm.vision_model` (heavy) and
   `llm.latex_extract_model` (light), both `provider::model`, empty=disabled; stop
   stripping `vision_model` in `_migrate_llm_config`; canonical source of truth.
2. **Two resolvers (independent clients), fallback ONLY on empty slot (R13)**:
   `_resolve_vision_client` (`vision_model`→main-if-vision→None) for ingest/image
   description; `_resolve_extract_client`
   (`latex_extract_model`→`vision_model`→main-if-vision) for interactive surfaces.
   The chain advances ONLY when a slot is empty/unconfigured. A **configured** slot
   that is non-vision / unreachable / auth-failing **RAISES and HALTS** — never a
   silent fall-through to a heavier model (which would spike latency/cost and hide
   broken config). Ingest config-failure raises upfront; only transient per-page
   runtime errors degrade to pymupdf4llm for that page (logged + provenance). Ingest
   uses the vision resolver ONLY (R10).
3. **Ingest (A: always-on)**: PDF → pymupdf4llm (structure) + page-render→`vision_model`
   transcription (L1 text). `parser_used="vlm"`. Per-page fallback to parser text.
4. **Bounded render (R14)**: `vision_render_dpi`=170 (150–200) + `vision_max_image_px`
   =1600 longest-edge cap with downscale, so dense pages never exceed image-payload/
   token limits (P0 confirms exact per-provider caps).
5. **Cache key incl. model (R12)**: per-page VLM cache key is
   `(page_content_hash, resolved_vision_model)` — a Dashboard model switch
   invalidates stale extractions and re-extracts; content hash alone would silently
   serve the old model's L1.
6. **Anti-hallucination (R1/R8)**: retain `metadata.parser_text` per page; formula
   cross-check via `_formula_tokens`/`_is_formula_subsequence`; no auto-`verified`.
7. **Total-spend rail (R2)**: `vision_max_pages_per_run` guard (default ~300);
   beyond it requires explicit opt-in, remainder logged `vision_skipped`.
8. **Plugin SoT (R5)**: plugin READS both resolved model ids from the Dashboard
   runtime snapshot; any plugin setting is write-through to backend config.
9. **Reshape `latexModel` in place (B)**: Convert-to-LaTeX + Cmd+Shift+X render the
   region image and call `LLMClient.complete(messages, { model: resolvedExtractModel })`.
   Since `latexModel` is unreleased (same branch), it is REMOVED/RESHAPED into
   `latex_extract_model` directly — no migration, no deprecation hint.
   `complete(opts.model)` (the general override) stays and is reused.
10. **Spec**: revise SYSTEM_BEHAVIOR §26 to permit user-elected page VLM while
    keeping selective measured-loss recovery for the no-vision-model case.
11. **Cloud vision = CLI subscription, no API keys (P0 LIVE-VERIFIED)**: Ollama uses
    in-memory base64 (httpx, no disk); agentic CLIs **claude + agy + codex ALL passed
    a live image-read test** and get `describe_image` via a temp PNG + path-in-prompt +
    their Read tool (`claude -p --allowedTools Read --add-dir`; `agy --print`;
    `codex exec`). NO unsafe auto-approve flags (policy-blocked). **Per-provider output
    normalization REQUIRED** (strip `$$`/codex banners/fences/commentary → clean LaTeX).
    Direct vision-API clients are a non-goal. Temp PNGs live under
    `<repo>/.cache/vision_render/<run-id>/` (NOT `/tmp`; `.cache/` gitignored) and are
    **removed in a `finally` — guaranteed on success, exception, and timeout; per-run
    subdir wiped at end; stale dirs swept on startup; no leaks.** Optimal pipeline:
    PyMuPDF `get_pixmap` render, bounded concurrency, in-memory for Ollama.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: heuristic math-region gating; per-source opt-in UI; non-PDF
  ingest changes; chat-answer model changes.
- **Stop Conditions**:
  - **STOP after P1** (spec/contract incl. §26 revision) for user approval — this
    changes a locked architectural invariant. (No merge-first gate; same branch.)
  - **STOP** if the provider client factory cannot build an independent vision
    client without entangling main-LLM auth/state → reassess client design.
  - **STOP** if rendering pages (`get_pixmap`) + cloud image payloads exceed model
    input limits for large pages → define a tiling/downscale contract first.

## 6. Evidence Ledger

See `.agents/plans/01_pdf_vlm_extraction_roadmap_evidence.md`. Key pre-facts: vision
infra exists but half-migrated (`vision_model` stripped in `_migrate_llm_config`);
config has first-class `provider::model` slots to mirror for both new keys; PDF
parser is client-free with a hybrid placeholder (`pdf.py:135`); Dashboard already
edits backend model config; plugin `complete(opts.model)` override exists (v0.21.0),
reused for the light interactive model.

## 7. Execution Phases (TDD + CI per phase) — same branch `feature/chat-decay-quick-wins`

- **P0 — Research & Baseline** (mostly done): ✅ independent client via
  `_make_by_key(provider,{model})`; ✅ Ollama `describe_image` (httpx base64,
  in-memory); ✅ `wiki config set llm.<key>` for Dashboard IO; ⚠️ cloud clients are
  CLI-subscription + text-stdin → cloud vision goes via agentic-CLI temp-PNG→Read.
  ✅ **image-read feasibility test PASSED for claude + agy + codex** (live, distinctive-
  token OCR) — all three enabled; output-normalization + no-unsafe-flags required;
  ✅ `fitz.get_pixmap(dpi=170)` renders (test PNG 1464×567 < 1600 cap). REMAINING
  (P5-side, non-blocking): confirm plugin snapshot exposes BOTH model ids; region-image
  capture for a right-click text selection (else selection-image+text fallback).
- **P1 — Contract & Spec (docs-first, STOP for approval)**: SYSTEM_BEHAVIOR §26
  revision; SCHEMA both slots (`vision_model`, `latex_extract_model`) + fallback
  chain + `parser_used:"vlm"` + per-page `parser_text` provenance; PLUGIN_SCHEMA
  settings + two Dashboard rows; bump 4 spec titles to `v0.22`. EN then `_KR`.
- **P2 — Backend config slots**: `vision_model` + `latex_extract_model` defaults +
  migration preserve + validation; `split/join_provider_model` reuse. (pytest+ruff+mypy)
- **P3 — Backend resolvers + per-provider vision call**: `_resolve_vision_client` +
  `_resolve_extract_client` (independent clients; vision-validated; **fall through
  ONLY on empty slot, RAISE on configured-failure** — R13); add `describe_image` to
  the agentic-CLI clients (ALL THREE P0-verified: claude/agy/codex) — temp PNG under
  `.cache/vision_render/<run-id>/` → path-in-prompt → CLI Read → strict transcribe →
  **per-provider output normalizer** (strip `$$`/codex banners/fences/commentary);
  **temp PNG removed in `finally` + per-run subdir wiped**; no unsafe CLI flags;
  ensure standalone/md-image
  paths still work; **tests: ingest never selects `latex_extract_model`** (R10);
  **configured-bad model raises, empty slot falls through** (R13); **temp PNG cleaned
  on success + failure**. (tests)
- **P4 — Backend VLM-PDF ingest (optimal pipeline)**: `fitz.get_pixmap` bounded
  render (`vision_render_dpi` + `vision_max_image_px` downscale — R14, in-memory) +
  bounded-concurrency transcription via `vision_model` (Ollama base64 / CLI temp-PNG)
  + per-page runtime fallback + `parser_text` retention + formula cross-check +
  `vision_max_pages_per_run` guard + **cache keyed by
  `(page_content_hash, resolved_model)`** (R12). `parser_used="vlm"`. No leaked temp
  files. (tests incl. simulated VLM: model-switch invalidation, render-bound,
  page-fallback, temp-cleanup)
- **P5 — Plugin Dashboard (two rows) + region reroute**: ingest-model + light-model
  rows (vision-only dropdowns, effective-fallback hint, `wiki config` persist);
  Convert-to-LaTeX + Cmd+Shift+X image→`latex_extract_model` (resolved) via
  `complete(opts.model)` with progressive attach-then-replace; REMOVE the unreleased
  `latexModel` in place (setting + text convert wiring) — no migration; update
  settings tests/docs + fold v0.21.0 `latexModel` CHANGELOG/guide entries into this
  feature. (vitest+tsc)
- **P6 — Testbed smoke + release**: `wiki add` math PDF with/without `vision_model`;
  snip/convert with/without `latex_extract_model` (fallback path); version bump
  `0.22.0`; CHANGELOG; spec titles; full CI; delete plan; release commit; update PR #45.

> Versioning: single Minor `0.21.0 → 0.22.0` (two new config slots, new behavior,
> spec change) — chat-decay + Zotero + VLM ship together on this branch.
