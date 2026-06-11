# Agent Relay State

## Current Active Goal
**[Minor Update] PDF Add-Source Asset Routing + "Added" State** (ROADMAP To-Do #1)

## Status
On clean `master` (post PR #22 merge). The previous blocker (PR #22) is now merged and pulled.

## Last action
Merged PR #22 to `master`, which successfully shipped the "Partial-selection LaTeX copy" feature (proving it feasible!) and urgent bugfixes. Cleaned up ROADMAP.md and truncated old RELAY.md session logs.

## Worktree note
Ready to create branch `feature/pdf-add-source-assets` off `master`.

## Next candidate
Begin implementation of the **PDF Add-Source** plan (`.agents/plans/04_pdf_add_source_assets.md`).
After that, To-Do #2 **RAG & Knowledge Quality Stabilization** (which has a full Arena plan) will follow.

### Update (2026-06-11, Claude — PDF add-source plan DRAFTED, NOT implemented)

- User promoted **PDF Add-Source Asset Routing + "Added" State** to ROADMAP
  **To-Do #1 (TOP priority)**; RAG dropped to #2; Native-PDF item (#6) notes the
  split-out. Plan written: `.agents/plans/04_pdf_add_source_assets.md` (+ arena).
- **PLANNING ONLY — no code written. User said "계획까지가 끝" (stop at the plan).**
  Do NOT implement until the user explicitly says go.
- Verified behavior (for the plan): add-source ingests **L1 immediately + queues
  L2/L3** (`source import` → `source register --build`); PDF images hard-dumped to
  `05_Assets/<slug>/` (`ingest_raw.py::_save_pdf_images`); badge has no "added"
  state (falls to "Check source"); PDF parser = pymupdf4llm (math-weak → VLM is RAG
  plan B, OUT of scope here).
- Locked user decisions: (A) plugin passes `--asset-dir` (05_Assets fallback);
  (B) tracked/built (`l1_ready…l4_ready/ready`) → non-clickable "Added" badge.
- **Branch decision + BLOCKER**: user chose a fresh `fix/pdf-add-source-assets` off
  `master`. BUT `master` is still v0.5.3 — it lacks v0.5.5's
  `assetLocalization.ts::resolveProfileAssetSpec` (which the plan reuses) and the
  add-source files (`chatSidebar.ts`/`incuratorClient.ts`) were changed in PR #22,
  so branching off master now risks conflicts. **Recommended: merge PR #22 to master
  FIRST, then branch off the updated master → v0.5.6.** (User merges PRs, not the
  agent.) When implementation is greenlit, start at P0 in the plan.

### Update (2026-06-11, Codex — RAG planning completed, implementation blocked)

- Completed planning-only RAG stabilization structure:
  one umbrella plan (`03`) plus six independent Master Plans (`A-F`), each with
  its own Arena.
- The three ordered execution batches are:
  `D1 → E → D2` (diagnosis/research/final observatory), `B → C` (compiler integrity), and
  `A → F` (retrieval substrate/ContextService).
- Removed the main overlap: Plan A owns retrieval, provenance continuity,
  authoritative retrieval transaction, and locator resolution; Plan F owns
  ContextService, progressive packs, public adapters, external/Obsidian parity,
  and feedback lineage.
- Preserved Vault quota/storage requirements as the separate
  `.agents/drafts/vault_storage_governance.md` milestone.
- This work is planning only. Do not begin RAG implementation until PR #22 is
  merged and the relevant component plan is explicitly approved. The separate
  PDF add-source plan remains ROADMAP priority #1.
