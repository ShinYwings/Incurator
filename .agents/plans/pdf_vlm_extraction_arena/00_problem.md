# Arena Briefing: Dedicated PDF-extraction (VLM) model

Date: 2026-06-21
Source: `.agents/USER_REPORT.md` — "Dedicated PDF-extraction (VLM) model"
Branch: continues on `feature/chat-decay-quick-wins` as one combined `v0.22.0` (user
decision 2026-06-21 — no merge-first). `latexModel` is unreleased on this same branch,
so it is reshaped in place into the vision flow; nothing to migrate.

## Problem

`add source` PDF ingest uses pymupdf4llm (text-layer → Markdown). The text layer
cannot reconstruct reliable LaTeX for math, so L1 math is approximate/garbled. The
user wants proper LaTeX at L1, and is explicit: **"L1에서 latex만 제대로 추출되면
뭘 해도 상관없음"** — fixing L1 extraction is the goal, downstream patching is not.

The sanctioned way to get LaTeX from a rendered page is a **vision model (VLM)**
that reads the page image. The user wants this as a **first-class, separately
selectable model**, decoupled from the Incurator main LLM, visible and selectable
in the Dashboard, and also driving the plugin's region-snip flows.

## Locked decisions (from the user)

- **A — Always-on when configured.** If a PDF ingest model is set, every
  `add source` PDF is extracted page-by-page through it. Empty/unset = today's
  pymupdf4llm path. (Not opt-in-per-source, not a heuristic gate.)
- **B (revised 2026-06-21) — TWO model slots + fallback chain.** The three LaTeX/
  extraction surfaces are NOT one task. Full-page document parsing (ingest) and
  interactive region/equation OCR (snip, Convert-to-LaTeX) differ in latency need,
  cost tolerance, and *capability class* — mirroring how the field splits (Mathpix/
  Nougat full-document engines vs pix2tex/texify/LaTeX-OCR small region specialists).
  So:
  - `vision_model` — **heavy, layout-aware** full-page model. Used by `add source`
    PDF ingest (and standalone/markdown image description).
  - `latex_extract_model` — **light/cheap region-OCR** vision model. Used by
    `Cmd+Shift+X` snip and right-click `Convert-to-LaTeX`. **Empty → falls back to
    `vision_model` → falls back to the current behavior (main chat model vision).**
  - Both empty = today's behavior (pymupdf4llm ingest + main-model snip vision).
  - The v0.21.0 text `latexModel` is reshaped in place into `latex_extract_model`
    (now an image-based light VISION model, robust to scanned/garbled text layers),
    not retired-with-migration (it is unreleased on this same branch).
  - Single-model users set only `vision_model` and everything works (fallback);
    power users (esp. local heavy ingest) set a small `latex_extract_model` so
    interactive snips stay fast/cheap.

## Scope (from the request)

1. **Two dedicated model slots**, both independent from the main Incurator LLM:
   `vision_model` (heavy, ingest) and `latex_extract_model` (light, interactive;
   falls back to `vision_model`).
2. **Dashboard**: show BOTH models' current status + allow selecting each, with the
   fallback relationship made explicit on the light row.
3. **`add source` PDF ingest**: page→`vision_model`→Markdown+LaTeX (always-on when set).
4. **`Cmd+Shift+X`** (PDF snip): transcription runs on `latex_extract_model`
   (→ `vision_model` → main-model vision), not unconditionally the main chat model.
5. **Convert-to-LaTeX** (right-click): same `latex_extract_model`, image-based
   (reshapes the unreleased text `latexModel`).

## Code reality (verified)

- Backend already has `_build_vision_client` / `_describe_images_with_vision`
  (`ingest_raw.py:1365`, `:469`) for standalone image files and markdown-linked
  images, but `_build_vision_client` only reuses the **main** client when it is
  vision-capable — there is no dedicated model. PDFs never reach this path.
- `llm.vision_model` config key exists historically but is **stripped** by
  `_migrate_llm_config` (`config.py:447-452`). The ingest error text still tells
  users to set `llm.vision_model` (`ingest_raw.py:1453`) — a half-migrated state to
  reconcile.
- Config has first-class `provider::model` slots: `primary`, `fallback`,
  `embedding`, `reranker` (`config.py`). A `vision_model` slot fits this pattern.
- PDF parser (`parsers/pdf.py`) is a pure parser with NO client; it has an explicit
  "Hybrid Pipeline placeholder: if config enables VLM … route here" comment
  (`pdf.py:135`). Vision work lives in `ingest_raw.py`, not the pure parser.
- Plugin: Dashboard "LLM Provider" card edits backend `.cache/config/config.yml`
  via `wiki config` and renders Primary/Fallback/Embed/reranker model rows
  (`incuratorDashboardModal.ts:582`+). Vision-capability is known per model
  (`modelSupportsVision`, `supportsVision` in the bundled catalogue).
- Plugin `LLMClient.complete(messages, opts?: { model })` (v0.21.0) already accepts
  a per-call model override — the exact hook plugin-side Cmd+Shift+X / Convert can
  reuse to run on the PDF model.

## Hard constraints

- **Separate model**: the PDF/vision model must never silently fall back to the
  main LLM when the user has chosen one. Empty = disabled, not "use main".
- **Spec conflict**: SYSTEM_BEHAVIOR §26 currently REJECTS whole-corpus/every-page
  VLM ("Whole-corpus/every-page VLM processing is rejected"). Decision A
  contradicts this; the spec MUST be revised to allow user-elected always-on PDF
  VLM while keeping the selective-recovery path for the no-vision-model case.
- **Cost/time are real** (per earlier analysis): per paper a few cents–$1 cloud;
  local VLM can be minutes–hours. Always-on must ship with progress + guardrails
  (page concurrency, per-page timeout, max-page warning, content-hash caching),
  even though the user accepted the cost.
- Backend change (Python) is in-scope here — the "no backend changes" rule is for
  trivial plugin-only batches, not for a feature that is inherently backend ingest.
- Minor bump `0.21.0 → 0.22.0` (new config slot + new behavior + spec change).
