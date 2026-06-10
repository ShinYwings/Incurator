# Native PDF Annotation System Plan

## Context
Replace the annotation system that previously relied on Zotero with an internal system. Utilize Obsidian's built-in PDF Viewer to save highlights and memos directly into `state.sqlite` and synchronize them offline.

## Multi-Agent Debate Topics (For Codex & Claude)
1. **`schema_guardian`**: 
   - When designing the `pdf_annotations` table schema, how can we make annotation blocks referenceable for integration with Obsidian Canvas?
2. **`source_pair_analyst`**: 
   - Can we design it so that highlighted text is directly promoted into `source_spans` of the RAG pipeline?
3. **`plugin_ux_designer`** (New role): 
   - How can we implement a smooth highlighting and popup memo UI in the plugin frontend (around `pdfCapture.ts`) that matches the UX of Zotero's highlighter? What are the IPC performance optimization strategies for communicating with the backend?

## Implementation Skeleton
- `backend/src/curator/db.py`: Create `pdf_annotations` table.
- `plugin/src/pdf/*`: Add highlight rendering, event listeners, and IPC transmission logic.
- `backend/src/curator/mcp_server.py` or IPC router: Receive annotation create/read/delete requests from the plugin and reflect them in the DB.
- `backend/src/curator/db_sync.py`: Include the `pdf_annotations` table in the Knowledge Sync Bridge Export/Import targets.

## Additional PDF-Domain Scope (triaged 2026-06-11)

### PDF / Zotero Asset Location Management
- **Current behavior**: When adding a PDF source via the purple pin, extracted
  PDF images are dumped into `05_Assets`. PDFs are usually pulled from a Zotero
  library folder, which has its own profile-specific asset location.
- **Requirements**:
  - Save extracted PDF images into the **profile-matched asset location** for
    that source. Cleanest candidate: store the asset location in the note's
    **frontmatter** so links resolve there. Link references so PDF images are
    created inside that asset folder.
  - When an external image is attached to an `.md` file, route it to that
    asset location too, with **`05_Assets` as the fallback**.
- **Reload relativepath bug**: The "reload" button on an `.md` file currently
  loads Zotero images from the Zotero **data folder cache** instead of from the
  assets folder (as "import item from Zotero" does). The image relativepath is
  computed wrong on reload — it must read from the asset location.
- **Add-source button state bug**: After "add source" succeeds, the button stays
  active. Once the add is confirmed, change the button label to **"Added"**.

### PDF Full-Text Search
- **Requirement**: Add an in-PDF text search feature.
- **Sub-feature**: spelling-exact / strict-spelling matching mode.

## Files Likely Involved (additional scope)
- `plugin/src/pdf/*` (purple pin add-source, asset path resolution, reload,
  in-PDF text search, add-source button state)
- PDF parser / asset writer in `backend/src/curator/` (image extraction target
  path, frontmatter asset-location field)

## Notes (additional scope)
- The asset-management + reload + add-source-button bugs are independent
  bug-class fixes and could be split out / prioritized ahead of the full
  annotation system if needed.