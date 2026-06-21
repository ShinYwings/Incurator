# Plugin Proposal: Dashboard PDF-model selector + region-snip reroute

Date: 2026-06-21 | Agent Persona: lead_architect (Plugin/UX)

## 1. Core Logic & Implementation

### 1.1 Canonical source of truth = backend config (both slots)
Both models are **backend** values (`llm.vision_model`, `llm.latex_extract_model`)
edited via `wiki config`, exactly like Primary/Fallback/Embed. The plugin READS the
resolved ids from the Dashboard runtime snapshot — no parallel persisted copy, no
drift. The interactive surfaces resolve in the plugin as:
`latex_extract_model → vision_model → (main chat model if vision-capable)`.

### 1.2 Dashboard: TWO rows
In the Dashboard "LLM Provider" card (`incuratorDashboardModal.ts:582`+), mirroring
the Primary/Fallback rows, add:
- **PDF ingest model (full-page)** → `llm.vision_model`. Dropdown of
  **vision-capable** catalogue models (`supportsVision === true`) + "— (disabled,
  use pymupdf4llm)". Status = model + health (installed/exceeds-RAM for Ollama,
  reachable for cloud).
- **LaTeX/region extract model (light)** → `llm.latex_extract_model`. Same
  vision-only dropdown + "— (use PDF ingest model)". Its status line shows the
  EFFECTIVE resolved model when empty (e.g. "↳ using <vision_model>") so the
  fallback is visible, never a mystery.
- Both persist via `wiki config`.

### 1.3 Region flows use the LIGHT model (reshape `latexModel` in place)
Reuse the v0.21.0 `LLMClient.complete(messages, opts?: { model })` hook with the
plugin-resolved `latex_extract_model` (or its fallback):
- **Convert-to-LaTeX (right-click)**: render the selected region to an **image**
  (`getActivePdfContext("image")`; if only a text selection bbox is available,
  investigate region-image capture — else send the selection image + text together)
  and transcribe via the light model. The unreleased text `latexModel` setting +
  its text-only wiring are REMOVED in place (no migration; same branch).
- **Cmd+Shift+X (snip)**: attach the raw crop image immediately, show
  "Transcribing region…", then transcribe via the light model and replace the chip
  with transcription + image (progressive — a slow/local model never blocks the
  chip). Chat ANSWER still uses the main model; only the crop *extraction* uses the
  light model. This is exactly "Cmd+Shift+X runs on the selected (light) model."
- **Why light here**: a single region is latency-sensitive; a small region-OCR
  vision model (pix2tex/texify-class behavior, or a small VLM like qwen2-VL-2B) is
  fast/cheap and is the right capability class for isolated equations/regions — the
  heavy ingest model would make interactive snips sluggish (esp. local).

### 1.4 Provider/model selection UX
- Vision-only filter prevents picking a text model as the PDF model.
- Ollama vision models (`qwen2.5-vl:7b`, `llava`, `gemma3` vision, …) get the
  existing Pull button treatment; cloud vision models (Gemini/Claude/GPT vision)
  show reachability.

## 2. Pros & Cons

**Pros**
- Canonical backend config; Dashboard is already the model surface, so two rows are
  consistent with Primary/Fallback/Embed.
- Reuses the just-shipped `complete(opts.model)` override — no new client plumbing.
- Matches the task split (full-page layout vs region OCR) and the latency/cost
  reality: interactive snips stay fast/cheap on a small model while ingest gets the
  heavy one. Single-model users still set only `vision_model` (fallback covers them).
- Image-based light extraction is robust to scanned/garbled text layers (the exact
  failure of the v0.21.0 text path).

**Cons / limits**
- Plugin must read BOTH backend-resolved ids; reuse the existing Dashboard snapshot
  path, don't invent a second source of truth.
- Cmd+Shift+X gains a VLM round-trip at snip time; mitigated by progressive
  attach-image-then-replace + "Transcribing…" notice.
- Two model rows is slightly more config surface; mitigated by the explicit
  "↳ using <vision_model>" fallback hint so an empty light slot is never confusing.
- Region-image capture for a right-click *text* selection (vs a Cmd+Shift+X crop)
  may need extra work — investigate in P0/P5; fall back to selection-image+text.
