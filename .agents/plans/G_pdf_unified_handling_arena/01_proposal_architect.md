# Architecture Proposal: Single PDF-Identity Authority + Renderer Slimming

Date: 2026-06-19 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

The unifying idea: **a PDF is one canonical `source` row; everything else is a
key into it.** Stop converting identifiers ad hoc; resolve once, at the boundary.

### 1.1 Backend — one resolver: `pdf_identity.resolve(...)`

New thin module `backend/src/curator/pdf_identity.py` (pure, no I/O beyond DB +
the existing Zotero helpers) exposing:

```python
@dataclass(frozen=True)
class PdfIdentity:
    source_id: int | None          # canonical sources.id if tracked
    abs_path: str | None           # resolved absolute file path (real PDF)
    relpath: str | None            # in-vault path (stub for Reference Mode)
    logical_source_id: str | None  # e.g. "zotero:<key>"
    zotero_key: str | None
    content_hash: str | None
    is_reference: bool

def resolve(
    paths, *,
    relpath="", abs_path="", zotero_key="", content_hash="", logical_source_id="",
) -> PdfIdentity: ...
```

`resolve()` is the *only* place that:
- expands a stub `.md` to its real file (absorbs `_resolve_reference_source`);
- calls `zotero_tools.resolve_pdf` for a key (the single Zotero resolver);
- computes/looks up `logical_source_id` (absorbs `_default_logical_source_id`);
- matches an existing `sources` row by id / relpath / external_path / hash.

`import_source` (Reference Mode + add-source) and the locator builder both call
`resolve()` instead of their private resolvers. The two ingest flows collapse to
"resolve identity → upsert row → generate L1." `_locator_from_span` derives its
open target from the same identity (external file authoritative when present).

### 1.2 Plugin — one model + one resolver

New `plugin/src/context/pdfSource.ts`:

```ts
export interface PdfSource {
  absPath?: string;      // real file on disk
  relpath?: string;      // in-vault path/stub
  zoteroKey?: string;
  fileHash?: string;
  displayName: string;
}
// single resolver; prefers backend resolution when available, thin local fallback
export async function resolvePdfSource(input, deps): Promise<PdfSource>;
export function pdfStatusKey(s: PdfSource): string; // one canonical cache key
```

All call sites (`getPdfRefSourcePath`, `resolvePdfRefSourcePath`,
`ensureIncuratorStatusForRef`, `onIncuratorStatusClick`, the locator opener,
`buildSyncedExternalPdfState`) consume `PdfSource` + `pdfStatusKey`. The badge
status map is keyed only by `pdfStatusKey`.

### 1.3 Slim `externalPdfView.ts`

Extract out of the view (no behavior change, pure move + tests):
- `registerExternalPdf*`, persisted-docs map, `persistDocs`/`loadPersistedDocs`
  → `externalPdfRegistry.ts`;
- `resolveZoteroAttachmentPath` → delete (delegate to backend `resolve_pdf`;
  keep only if backend unavailable, behind the plugin resolver).
The `ExternalPdfView` class keeps PDF.js render + zoom/scroll/page/snipping only.
Target: < ~1200 LOC for the view.

### 1.4 Delegate plugin Zotero resolution to backend

`resolveZoteroAttachmentPath` (plugin) becomes a fallback only; the primary path
is `IncuratorClient.resolveZoteroPdf()` → backend `zotero_tools.resolve_pdf`.
Removes D2 divergence.

## 2. Pros & Cons

**Pros**
- One mental model: "resolve once → canonical source." Kills D1/D2.
- Renderer becomes approachable (D3); identity changes no longer touch PDF.js.
- Badge bugs (D4, items 3/4) disappear because there is one key + one resolver.
- Mostly *move + delegate*; low semantic risk, high readability gain.

**Cons / limits**
- Touching `import_source` is schema-adjacent — must keep ingest tests green and
  avoid changing the `sources` contract (additive only).
- `externalPdfView.ts` extraction is large surface for merge conflicts with the
  in-flight diff-viewer work; must sequence after current branch settles.
- Backend-delegated Zotero resolution adds a round-trip on the hot path; cache
  the resolved path per key in the plugin to keep it fast.
