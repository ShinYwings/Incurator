# Briefing: PDF Handling Unification & Simplification

Date: 2026-06-19 | Author: Claude (main agent)
Source: User request (2026-06-19) + Plan F P6 Reference Mode audit findings in
`.agents/USER_REPORT.md`.

## 1. Problem Statement

The user reports that the PDF handling logic is "too complex" and asks whether the
system can be made **simpler, faster, and easier to understand**. They identify
three distinct PDF concerns that currently feel tangled:

1. **Reference Mode** — registering a PDF as an *external* source without copying
   it into the vault (an in-vault markdown stub + an external file path).
2. **Add source** — the "pin PDF as source" flow (status badge → ingest → L1–L4).
3. **Obsidian agent ↔ PDF viewer reference** — the agent grounding itself on a
   PDF open in the plugin's external PDF viewer (context capture, page refs,
   `zotero://` link interception, cross-references).

This briefing is the input constraint set for the Arena debate. The goal of the
debate is a Master Plan that (a) fixes the open audit items and (b) reduces the
structural complexity of PDF handling **without changing user-visible behavior**
except where that behavior is already a bug.

## 2. Measured Complexity (evidence, not opinion)

Line counts and coupling measured 2026-06-19 on `feature/agent-context-service`:

| Module | LOC | Responsibility (today) |
|---|---|---|
| `plugin/src/ui/externalPdfView.ts` | **2057** | PDF.js render + zoom/scroll/page state + persistence + registration + Zotero resolution + snipping + text layout + context capture (god class) |
| `plugin/src/ui/chatSidebar.ts` (PDF refs) | **249 refs** | badge state machine, ingest orchestration, pinned PDF context, source-path resolution |
| `plugin/src/context/crossReferenceResolver.ts` | 511 | cross-reference (`see §X`) resolution |
| `plugin/src/context/pdfCapture.ts` | 439 | capture current page / region for LLM context |
| `plugin/src/context/pdfTextLayout.ts` | 264 | text layout reconstruction |
| `plugin/src/context/quickQueryContext.ts` | 166 | quick-query PDF context |
| `plugin/src/context/providerContextFormat.ts` | 136 | format pack/context for provider |
| `plugin/src/ui/externalPdfState.ts` | 64 | persisted-doc retention + path resolution |
| `backend/src/curator/zotero_tools.py` | 340 | `resolve_pdf` + tools |
| `backend/src/curator/zotero.py` | 266 | Zotero DB/prefs parsing |
| `backend/src/curator/zotero_integration.py` | 254 | integration glue |
| `backend/src/curator/ingest_raw.py` (pdf/ref) | 91 refs | reference stub ingest, `_resolve_reference_source` |

## 3. Root Complexity Drivers (the disease, not the symptoms)

**D1 — PDF identity has no single representation.** A PDF is referred to by, and
ad-hoc converted between, at least five identifiers:
- vault `relpath` (for Reference Mode this is the *stub* `.md`, not the PDF);
- absolute filesystem path;
- Zotero `attachment_key`;
- content `hash` (SHA256);
- `logical_source_id` (e.g. `zotero:<key>`).

Each flow has its own resolver: backend `_resolve_reference_source`,
`_default_logical_source_id`, `zotero_tools.resolve_pdf`; plugin
`getPdfRefSourcePath`, `resolvePdfRefSourcePath`, `resolveExternalPdfPath`,
`resolveZoteroAttachmentPath`, `toAbsolutePath`, `buildSyncedExternalPdfState`.
There is no one authority that maps "whatever I have" → "the canonical source +
the thing to open."

**D2 — Two parallel Zotero resolvers.** `plugin resolveZoteroAttachmentPath`
(scans `<base>/storage/<key>/*.pdf`) and backend `zotero_tools.resolve_pdf`
(prefs-aware) can disagree. The plugin one is a degraded copy.

**D3 — `externalPdfView.ts` is a 2057-LOC god class.** Rendering is entangled
with identity/registration/persistence/Zotero, so any PDF identity change forces
edits deep inside the renderer.

**D4 — The badge/source-state machine in `chatSidebar` keys status
inconsistently** (sometimes by `sourcePath`, sometimes by `zotero:<key>`), and
decides `isZoteroPdf` via `leaf.view.getState()` `as any` casts.

**D5 — Reference stub vs `external_uri` precedence was unspecified** (the
locator open-target bug, item 1, fixed in P6; the same ambiguity can recur
anywhere a consumer prefers `relpath`).

## 4. Audit Items In Scope (from USER_REPORT.md)

- Item 1 (locator open target) — FIXED in P6; carry forward only the
  "audit other relpath-first consumers" follow-up.
- Item 2 (contract precedence) — RESOLVED via spec clarification; carry forward
  the consumer audit.
- Item 3 (badge cache key) — uncertain; this plan must produce a concrete repro
  or close it.
- Item 4 (`getState()` any-cast Zotero detection) — in scope.
- Item 5 (`isAddedState` excludes queued/running) — clarify intended states.
- Item 6 — closed (verified not a bug).

## 5. Hard Constraints (locked, non-negotiable)

- **Storage model unchanged.** `state.sqlite` remains source of truth; Reference
  Mode keeps the stub-in-vault + external-file model (no hard-copying into the
  vault). See Shared Architecture Memory in CLAUDE.md.
- **No behavior regressions.** Existing pin/reference/agent-PDF flows must pass
  their current tests; only already-buggy behavior may change.
- **No new external dependencies** for PDF parsing/rendering.
- **Spec-first.** Any contract change updates `docs/specs/` + EN/KR guides first.
- **Backward compatibility** of persisted plugin state (external-PDF docs map)
  and of the `sources` schema (additive migrations only).

## 6. Definition of Done (for the eventual Master Plan)

1. A single PDF-identity resolution authority on each side (backend + plugin),
   with the others delegating to it.
2. `externalPdfView.ts` reduced to rendering + view-state; identity/registration/
   Zotero extracted to small testable modules.
3. Badge state machine keys status by one canonical id; `as any` Zotero
   detection removed.
4. Audit items 3/4/5 closed (fixed or proven non-issues) with tests.
5. Net LOC reduction in PDF handling, measured, with no test regressions.
