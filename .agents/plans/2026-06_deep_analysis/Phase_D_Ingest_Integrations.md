# Phase D: Ingest & Integrations — Senior Committee Deep Analysis

**Target Files**: `ingest_raw.py`, `plugin_api.py`, Zotero integration code

**Panel**: Bob (Data), Alice (Architect), Evan (Plugin), Frank (Backend), Hannah (QA)

---

## Debate Transcript

### 1. The iCloud Path Crisis: Ignoring Zotero Community Standards

**Evan (Plugin Specialist)**:
"The user's PDF is currently open at `/Users/shin/Library/Mobile Documents/com~apple~CloudDocs/Zotero/...`. This is an iCloud-synced path. Our plugin constructs absolute paths using `app.vault.adapter.getBasePath()` and sends them to the backend.

I researched how the **Obsidian Zotero Integration** plugin ecosystem handles this. The community consensus is clear:
- **Never use absolute paths as identifiers.** They break across devices.
- Use Zotero's **'Linked Attachment Base Directory'** for relative path resolution.
- Use **`zotero://select/items/...`** URIs as stable, device-independent identifiers.

Our system violates all three of these community standards."

**Frank (Backend Specialist)**:
"In `ingest_raw.py`, the backend receives the absolute path and calls `Path(absolute_path).exists()` without any cloud sync delay handling. On iCloud, files may be 'evicted' (not downloaded locally) and show as missing even though they exist. The system interprets this as 'file not found' and silently skips the source."

**Hannah (QA Engineer)**:
"This is exactly why our CI pipelines on GitHub Actions consistently fail on PDF-related tests. GitHub runners don't have iCloud. The absolute paths in our test fixtures point to non-existent local directories. By switching to `zotero://` URIs or content-hash-based identifiers, our test data becomes fully portable."

### 2. Blind L1 Acceptance: No Correction Tracking

**Bob (Data Engineer)**:
"The `sources` table in `db.py` tracks `content_hash` and `status` but has no mechanism to record that a human has corrected metadata from the source. The `correction_history` concept from `insight_lifecycle.py` applies only to insight candidates, not to L1 source metadata itself. If a Zotero source has wrong author names or a corrupt title, the system ingests it as-is and propagates the error through the entire DAG."

### 📝 Consensus & Action Items

1. **[Plugin & Backend]** Replace absolute path resolution with Zotero community-standard `zotero://` URIs or content-hash-based identifiers.
2. **[Backend]** Add iCloud-aware path resolution with retry logic for evicted files.
3. **[QA]** Replace all absolute path fixtures in the test suite with portable URI mocks.
4. **[Backend]** Add a `correction_history` column to the `sources` table to track L1 metadata overrides.
