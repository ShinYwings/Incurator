# Cross-Agent Relay State

## Status: IMPLEMENTING (P1 specs approved; P2→P6 auto-pilot)

**§26 approved (2026-06-21).** P1 specs written: SYSTEM_BEHAVIOR §26.2 scoped +
new §26.2a; SCHEMA §2.5 (two slots + render/cost knobs) + `parser_used:vlm` +
`pdf_pages[].parser_text`; PLUGIN_SCHEMA §2.1.2 (two Dashboard rows) + region rule;
PLUGIN_GUIDE EN+KR Convert-to-LaTeX reshaped. Spec titles bump to v0.22 deferred to
P6 (atomic with manifests). `test_spec_sync` green.


**Milestone:** Dedicated PDF-extraction (VLM) model → `v0.22.0`
**Plan:** `.agents/plans/01_pdf_vlm_extraction.md` (Arena: `.agents/plans/pdf_vlm_extraction_arena/`)

**Locked decisions (user, 2026-06-21):**
- A — always-on: when `llm.vision_model` is set, every `add source` PDF is
  page-VLM transcribed to LaTeX L1 (empty = pymupdf4llm).
- B — unify: retire v0.21.0 text `latexModel`; Convert-to-LaTeX + Cmd+Shift+X
  transcribe the region image via the new vision model.

**Branch strategy (user decision 2026-06-21):** No merge-first. Continue on the
EXISTING branch `feature/chat-decay-quick-wins`; PR #45 grows into one combined
`v0.22.0`. `latexModel` is unreleased → reshaped in place, no migration.

**Model design (resolved 2026-06-21):** TWO slots + fallback.
- `vision_model` — heavy full-page model for `add source` ingest + image description.
- `latex_extract_model` — light region-OCR model for Cmd+Shift+X + Convert-to-LaTeX;
  empty → `vision_model` → main-model vision. Ingest uses `vision_model` ONLY.
- Rationale: region OCR vs full-page layout are different task/capability classes
  (Mathpix/Nougat full-doc vs pix2tex/texify region specialists); interactive snips
  are latency/cost-sensitive, ingest is accuracy-first. The unreleased v0.21.0 text
  `latexModel` reshapes in place into `latex_extract_model` (image-based, no migration).

**Blockers:**
- P1 (spec §26 revision) requires a STOP for approval — changes a locked invariant.

**Immediate next action:** Plan is fully revised for the two-slot design. Execute
P0 (read-only research) → P1 (spec/docs) → STOP for §26 approval before any code.

**Prior shipped:** v0.21.0 (chat-decay suppression, latexModel, Zotero recent-first)
on PR #45.
