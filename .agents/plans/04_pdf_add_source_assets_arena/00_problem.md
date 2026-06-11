# Problem Definition: PDF Add-Source Asset Routing + Button State + Behavior

Date: 2026-06-11 | Pulled to TOP roadmap priority at user's request.
Split out of ROADMAP #5 (Native PDF Annotation & Asset System) per the draft's own
note that these are "independent bug-class fixes … could be prioritized ahead of
the full annotation system."

## Verified current behavior (investigation, not assumption)

- **"Add source" DOES ingest into the curation pipeline.** The purple-pin / context
  badge "Add source" (shown when backend status = `untracked`,
  [chatSidebar.ts:2070]) calls `ingestPdf` → `wiki plugin source import`
  (`--policy reference|mirror`) then `wiki plugin source register --build`. Per
  [incuratorClient.ts:216-220] this generates **L1 immediately (structural, no LLM)**
  and **queues L2/L3 (/L4)** to the background worker. Status then progresses
  `l1_ready → l2_ready → l3_ready → l4_ready` (see `normalizeStatus`,
  incuratorClient.ts:684-711).

- **Images are hard-dumped to `05_Assets/<slug>/`.** `_save_pdf_images`
  ([ingest_raw.py:1092]) builds `paths.root / DIR_ASSETS / slug` from the relpath
  stem and ignores any per-source/profile asset location. PDFs usually come from a
  Zotero library whose profile has its own asset folder, so the assets land in the
  wrong place.

- **The add-source button has no "added/tracked" terminal state.** The badge label
  map ([chatSidebar.ts:2055-2073]) handles `running/stale/missing/moved/hash_drift/
  error/untracked` and everything else (including `l1_ready…l4_ready`, i.e. a
  successfully tracked source) falls to **default `"Check source"`** and stays
  clickable. The user expects an **"Added"** indicator that is no longer clickable.

- **PDF text/math reading is `pymupdf4llm` ("Math-Aware hybrid",
  [parsers/pdf.py]).** It is insufficient for complex formulas (formulas evaporate
  into L1/L2). The **VLM-based math extraction upgrade is owned by RAG-stabilization
  plan B** (math-preserving extraction/distillation), NOT this plan.

## Scope of THIS plan

IN:
1. Route add-source PDF extracted images to the **plugin-resolved asset folder**
   (`--asset-dir`), with `05_Assets/<slug>/` as fallback. (User decision A.)
2. Add an **"Added" (disabled) badge** for tracked/built sources
   (`l1_ready…l4_ready`), non-clickable, re-activating on `stale/moved/hash_drift`.
   (User decision B.)
3. **Verify** the end-to-end add-source behavior (L1 instant + L2/L3 queued + assets
   in the chosen folder) in the testbed, and document it.

OUT (cross-referenced, not implemented here):
- PDF math/VLM extraction quality → **RAG-stabilization plan B**.
- Full native annotation system, in-PDF full-text search → **ROADMAP #5 remainder**.
- External-image-attachment-to-`.md` routing → noted as a near-neighbor follow-up
  (same `--asset-dir` mechanism) but optional for this batch.

## Hard constraints / invariants

- Non-Zotero / no-profile PDFs must still work: missing `--asset-dir` → unchanged
  `05_Assets/<slug>/` behavior (zero regression).
- `_save_pdf_images` must never write outside the vault root; sanitize the asset dir.
- The "Added" state must NOT mask `stale/moved/hash_drift/error` (those keep their
  actionable, clickable badges).
- Testbed must cover Zotero Reference-Mode PDFs and non-Zotero local PDFs.
