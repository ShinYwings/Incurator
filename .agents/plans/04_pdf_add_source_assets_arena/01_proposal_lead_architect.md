# Proposal: --asset-dir threading + "Added" badge state

Date: 2026-06-11 | Agent Persona: lead_architect

## 1. Core Logic & Implementation

### 1.1 Asset routing (plugin resolves → backend uses)

**Plugin (incuratorClient.ingestPdf / chatSidebar add-source path):**
Resolve a vault-relative asset folder for the PDF being added and pass it as a new
`--asset-dir` arg to `source import`:
- **Zotero source** (`ref.zoteroAttachmentKey`, or a Zotero profile exists): reuse
  the v0.5.5 `resolveProfileAssetSpec` from `src/zotero/assetLocalization.ts` on the
  first/default profile → `assetFolder` (the per-item `assetSubfolder` template is
  skipped here since add-source has no rendered item metadata; the backend appends
  the source slug subfolder).
- **Non-Zotero**: a new optional plugin setting `incuratorPdfAssetFolder`
  (default `""`). When empty → omit `--asset-dir` (backend falls back to
  `05_Assets`).
- Always omit `--asset-dir` if the resolved folder is empty, so behavior is
  unchanged when nothing is configured.

```ts
// IncuratorIngestRequest gains: assetDir?: string
const args = ["plugin", "source", "import", ...,
  ...(request.assetDir ? ["--asset-dir", request.assetDir] : []),
];
```

**Backend (`source_tools.py` source import → ingest → `_save_pdf_images`):**
Add `--asset-dir` to the `source import` CLI, thread it through the ingest call to
`_save_pdf_images(parsed, relpath, paths, asset_dir=...)`:

```python
def _save_pdf_images(parsed, relpath, paths, asset_dir: str | None = None) -> list[dict]:
    ...
    slug = _slug(relpath)
    root = _safe_vault_subdir(paths, asset_dir) if asset_dir else (paths.root / consts.DIR_ASSETS)
    assets_dir = root / slug
    ...
    saved.append({"obsidian_path": f"{_vault_rel(root)}/{slug}/{filename}", "page": page})
```
- `_safe_vault_subdir` resolves `asset_dir` under `paths.root`, rejecting `..`/abs
  escapes (falls back to `05_Assets` on a bad value). The `obsidian_path` embedded
  in L1 is computed from the actual root, so embeds resolve regardless of folder.

### 1.2 "Added" badge state (plugin chatSidebar.ts)

Add the tracked/built states to the label map and gate the click:

```ts
// incuratorStatusLabel(state)
case "l1_ready": case "l2_ready": case "l3_ready": case "l4_ready":
case "ready":    return "Added";
```
- In `onIncuratorStatusClick`, early-return (no-op, optional Notice "Already added;
  open Dashboard › Sources to rebuild") when state ∈ the Added set.
- Visually mark the badge non-interactive (a `is-added` class → `cursor: default`,
  no hover affordance).
- `stale / moved / missing / hash_drift / moved_and_hash_drift / error` keep their
  existing actionable labels + handlers (rebind / re-add), so a changed/moved source
  becomes clickable again automatically.

### 1.3 Verification + docs

- Testbed: `wiki plugin source import --file-path <pdf> --asset-dir <dir>` then
  `source register --build`; assert L1 page exists, images under `<dir>/<slug>/`,
  L2/L3 jobs queued. Repeat without `--asset-dir` → images under `05_Assets/<slug>/`.
- Docs: PLUGIN_GUIDE (EN+KR) add-source section — what it ingests (L1 now, L2/L3
  queued), where assets go, the "Added" state; PLUGIN_SCHEMA the `--asset-dir` arg +
  status→label mapping. Note the PDF math/VLM limitation points to RAG plan B.

## 2. Pros & Cons

**Pros**: small, additive, zero-regression (no `--asset-dir` → identical today);
reuses the v0.5.5 `assetLocalization` profile resolver; backend stays the single
image writer; "Added" state is pure label+guard, no new status from backend.

**Cons**: add-source can't resolve the per-item `assetSubfolder` template (no item
metadata at add time) — uses the profile's asset *folder* only; acceptable. A
backend that doesn't yet know `--asset-dir` must ignore it gracefully (handled by
argparse default None).
