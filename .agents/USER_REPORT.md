# User Report

This document is a **plain Inbox (backlog) log** that records bugs reported by the user, required features, ideas, etc., in chronological order without any filtering.

Agents must check this document and triage the received items into the `To-Do (Queuing)` area or `Icebox` area of `.agents/ROADMAP.md`. Once the triage is complete, **immediately delete** the item from this document.

## 📝 User Inbox

### Dedicated PDF-extraction (VLM) model, separate from the Incurator LLM (2026-06-21)
- **Problem**: `add source` PDF ingest uses pymupdf4llm (text-layer), which does
  not produce reliable LaTeX for math. Proper LaTeX requires a vision model (VLM)
  that reads the rendered page.
- **Requirement**:
  - Add a **separate, independently-selectable "PDF extraction model" (VLM)**,
    chosen like the existing provider/model selector but **distinct from the
    Incurator main LLM**.
  - The **Dashboard** must show this PDF model's current status and allow
    selecting it there.
  - When set, PDF extraction (`add source`) runs through this VLM so L1 LaTeX is
    correct. (User's stance: "L1에서 latex만 제대로 추출되면 뭘 해도 상관없음.")
  - **Cmd+Shift+X** (PDF snip to chat) must also run on this selected PDF
    extraction model, not the main chat model's vision. (User noted Cmd+Shift+X
    "already uses VLM" — actually it attaches an image that the *main* chat model
    interprets; reroute it to the dedicated model.)
- **Code reality / context**:
  - Backend already has `_build_vision_client` / `_describe_images_with_vision`
    (`ingest_raw.py:1365`) for standalone + md-linked images, but it only reuses
    the main client when vision-capable; the `llm.vision_model` config key is
    mid-migration (stripped in `_migrate_llm_config`). PDFs never use it.
  - v0.21.0 just shipped a TEXT-based `latexModel` for right-click Convert-to-LaTeX
    — overlaps conceptually; consolidation TBD (see open decisions).
  - Spec conflict: SYSTEM_BEHAVIOR §26 currently REJECTS whole-corpus/every-page
    VLM. Always-on PDF VLM ingest needs a spec revision.
- **Open decisions (pending user)**: (A) ingest trigger always-on vs opt-in vs
  hybrid gate; (B) fold the v0.21.0 text `latexModel` into the new vision model or
  keep separate.
