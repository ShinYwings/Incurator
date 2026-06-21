# Defense / Synthesis

Date: 2026-06-21 | Agent Persona: system_synthesizer (Closer)

All red-team points accepted. Resolutions folded into the Master Plan:

- **R1/R8 (hallucination + provenance)** — VLM L1 is NOT blind ground truth.
  Per page, store both `metadata.parser_text` (pymupdf4llm) and the VLM
  transcription; L1 text uses the VLM output but the parser text is retained for
  audit. Reuse `_formula_tokens` / `_is_formula_subsequence` to cross-check
  formulas: structural divergence raises an audit-visible signal, never a silent
  trust. `parser_used="vlm"` at source level; VLM-derived formulas obey the same
  evidence gate as §26 (no auto-`verified`).

- **R2 (total-spend rail)** — always-on per source, but a `vision_max_pages_per_run`
  guard (default ~300) on a single `add` run: beyond it, require explicit opt-in /
  report remaining pages as `vision_skipped` (logged, never silent). This keeps
  "그냥 vlm" for a paper while preserving the corpus-scale rail §26 cared about.
  §26 is revised to permit *user-elected* page VLM, not *implicit* whole-corpus VLM.

- **R3 (validate model)** — backend verifies the chosen `vision_model` advertises
  vision at client build; otherwise logs a clear error and falls back to
  pymupdf4llm (ingest never returns garbage). Plugin dropdown filters to
  `supportsVision`.

- **R4 (client reuse)** — build the dedicated vision client ONCE per ingest run and
  thread it through; preserve the legacy main-client path when `vision_model` is
  empty.

- **R5 (single source of truth)** — backend `llm.vision_model` is canonical. The
  plugin READS the resolved value from the Dashboard runtime snapshot; any plugin
  setting is write-through to backend config, never a parallel persisted copy.

- **R6 (snip latency)** — attach the raw crop image immediately, show
  "Transcribing region…", then replace with the transcription when it returns
  (progressive). A slow/local model never blocks the chip.

- **R7 (latexModel) — SUPERSEDED by branch decision (2026-06-21)**: `latexModel` is
  unreleased (PR #45 unmerged, same branch), so there is no migration. It is removed
  / reshaped in place into `latex_extract_model`; its v0.21.0 CHANGELOG/guide entries
  fold into the vision feature. No deprecation hint needed.

- **R9 (fallback transparency)** — Dashboard light row shows the EFFECTIVE resolved
  model ("↳ using <vision_model>") when empty; both dropdowns filter to
  vision-capable models; validate-vision-at-use with graceful fallback.

- **R10 (resolver separation)** — two distinct resolvers; ingest uses
  `_resolve_vision_client` ONLY. Unit test asserts ingest never picks
  `latex_extract_model`.

- **R11 (light-model scope)** — `latex_extract_model` documented as region/equation-
  grade; the snip prompt is region-scoped, not page-scoped.

## Reviewer corrections (2026-06-21) — accepted, folded into the plan

- **R12 (cache invalidation)** — the per-page VLM cache key is
  `(page_content_hash, resolved_vision_model)`, NOT content hash alone. A Dashboard
  model switch invalidates prior extractions and forces re-extraction on next
  `add`/build; without the model in the key, the system would silently serve the old
  model's L1. (Backend 1.3a.)
- **R13 (fallback ONLY on empty, raise on configured-failure)** — the resolver chain
  advances only when a slot is empty/unconfigured. A configured slot that is
  non-vision/unreachable/auth-failing RAISES and HALTS — it must NOT silently
  escalate (a failing light model must not quietly fall to the heavy `vision_model`,
  which would spike latency/cost and hide broken config). Ingest config-failure
  raises upfront; only transient per-page runtime errors degrade to pymupdf4llm for
  that page (logged + provenance). (Backend 1.2.)
- **R14 (render bound)** — concrete bound, not just the P0 stop condition:
  `vision_render_dpi`=170 (150–200) + `vision_max_image_px`=1600 longest-edge cap
  with downscale, so dense pages never blow the image-payload/token limit. (Backend
  1.4; P0 confirms exact per-provider caps.)
- **§26 STOP gate** — reviewer verified the P1 explicit-approval constraint for the
  SYSTEM_BEHAVIOR §26.2 revision is the correct procedural control. Unchanged.

Consensus reached. Proceed to Master Plan. Implementation continues on the existing
branch `feature/chat-decay-quick-wins` as one combined `v0.22.0` (no merge-first).
