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