# Changelog

All notable changes to Incurator are documented here.

---

## [0.5.4] — 2026-06-11

### Added

- **LaTeX-preserving copy from the AI chat (copy as Markdown).** Selecting part of
  an assistant reply and pressing `Cmd/Ctrl+C` now copies it as Markdown with
  formatting *and* the formulas' LaTeX **source** (`$...$` / `$$...$$`) restored,
  instead of the browser's flattened plain text / empty MathJax SVG.
- **LaTeX-preserving copy/cut from a note's Reading View.** Drag-selecting note
  text that contains a formula and pressing `Cmd/Ctrl+C` (or `Cmd/Ctrl+X`) copies
  the selection as Markdown with the LaTeX source restored. Works in pop-out
  windows. The selection visually skipping a non-selectable formula is expected —
  the formula is still captured.
  - Implemented via a Markdown post-processor that re-parses each rendered
    section's source and stamps it onto every formula as `data-tex` (only when the
    parsed and rendered formula counts match exactly, so a wrong source is never
    attached), plus a capture-phase clipboard handler gated to
    `.markdown-reading-view` + rendered math.
  - Non-math selections are left to Obsidian's native clipboard (byte-identical).
    Live Preview / Source mode already preserve `$...$` natively (CodeMirror copies
    the document source), so they are unchanged.

### Docs

- `PLUGIN_GUIDE` (EN + KR) §3.6/§3.7 and `PLUGIN_SCHEMA` §14 document the chat and
  Reading-View LaTeX copy behavior, the render-time stamping mechanism, and the
  exact-count correctness guard.

---

## [0.5.3] — 2026-06-11

### Removed

- **GitHub CLI (`gh`) dependency** — Incurator no longer requires or installs
  `gh`. `setup.sh` no longer installs it; the plugin's GitHub Sign-in/out
  settings toggle, the `github_authenticated`/`github_account` status fields, and
  `auth/githubAuth.ts` are removed; the backend `git_manager` no longer shells
  out to `gh auth status`. None of the core Git features needed it — `status`,
  `log`, file `history`, `commit`, and `push` all use the local `git` binary.

### Changed

- **Sidechat Git integration is local-only.** Asking "how did I write this
  before?" / history & status / push continue to work via local `git` with no
  GitHub account. HTTPS-push authentication, if you use it, is handled by your
  normal git credential helper, outside the plugin (commit/push can also stay
  with whatever tool you already use).

---

## [0.5.2] — 2026-06-11

### Fixed

- **Plugin no longer falls back to a stale `backend/.venv`** — `resolveWikiBinary`
  used to probe `<repo>/backend/.venv/bin/wiki` as a fallback after the canonical
  `<repo>/.venv/bin/wiki`. Because `backend/.venv` is never created by the
  supported workflow, when present it is stale, and running it silently executed
  an out-of-date backend (wrong version, missing fixes) without the user
  noticing. The resolver now probes ONLY the repo-root `.venv` and returns
  nothing if it is absent, so the user is prompted to re-run `./setup.sh` instead
  of unknowingly running an old build.

## [0.5.1] — 2026-06-11

### Fixed

- **Ask AI dropped formulas when selecting over math** — the quick-query popover
  captured the selection via `selection.toString()`, which is empty for a
  MathJax formula rendered as SVG, so dragging across a formula lost it. Capture
  now reads the formula's LaTeX source from the DOM annotation (present in both
  the SVG and the Live-Preview swapped-text state), preserving `$...$` / `$$...$$`
  — independent of render timing. Non-math selections are unchanged.

### Added

- **Keyboard selections trigger Ask AI** — selecting text with the keyboard
  (Shift+Arrow, Shift+Home/End, or Ctrl/Cmd+A) now surfaces the floating
  **✨ Ask AI** button, not just a mouse drag. Collapsing the selection back to a
  caret hides it.

> Note: copying only a partial editor selection with LaTeX intact (Cmd+C in an
> open note) remains deferred — see the ROADMAP Icebox.

---

## [0.5.0] — 2026-06-11

### Changed

- **Resilient, ambiguity-safe agent-edit matching** — `ai-agent-edit` SEARCH
  blocks no longer need to match the file byte-for-byte. A single shared matcher
  (`utils/editMatch.findSearchBlock`, used by every apply and preview path) tries
  `exact → line-trim → anchored`, tolerating leading/trailing whitespace and
  indentation-level drift, and always splices the file's real text. It refuses
  (returns null → "could not find") when ≥2 spans are plausible or an anchored
  span balloons past 3× the search size, so it never applies a guessed edit. This
  fixes the frequent "Could not find the exact SEARCH block" failures where no
  diff rendered at all.
- **Immediate diff (safe-gated)** — when an answer's edits target the note you're
  already viewing (or no note is focused), the in-editor Diff Viewer now opens
  automatically instead of waiting for a "Review Diff" click. A different focused
  note keeps the clickable pill so the diff never steals your editor; auto-open
  fires once per message and never on history re-render.
- **Diff Viewer hunk counter is always visible** (e.g. `1/1`), with ↑/↓ · Tab
  navigation and Y/N/Enter/Esc shortcuts for multi-hunk diffs (unchanged).
- **Scoped edits** — the edit prompt now requires minimal, section-scoped REPLACE
  bodies (never pasting a whole chat answer), plus a non-blocking "large
  replacement" warning as a model-independent safety net.

### Fixed

- **Leaked edit markers** — orphan `<<<<` / `====` / `>>>>` markers from a
  malformed/partial edit block are stripped from the rendered message (fence-aware,
  evidence-gated). Stored message content is untouched, so "Copy as Markdown"
  stays faithful. The block parser also tolerates marker spacing/length variants
  and a missing closer.

### Removed

- **On-disk diff artifact** — the `00_System/Agent Diffs/` note feature and its
  **Write edits as diff artifact** setting were removed; the in-editor Diff Viewer
  is now the single source of truth. Existing artifact files in your vault are
  left untouched.

---

## [0.4.4] — 2026-06-11

### Fixed

- **Plugin resolved a stale `wiki` binary** — `resolveWikiBinary` probed
  `<repo>/backend/.venv/bin/wiki` *before* the canonical repo-root
  `<repo>/.venv/bin/wiki`. Because `setup.sh` installs the live backend into the
  root `.venv` (`VIRTUAL_ENV="$ROOT_DIR/.venv"` + `uv pip install -e ./backend`),
  the leftover `backend/.venv` copy was frequently stale, so the plugin reported
  an old backend version (e.g. `0.4.2`/`0.3.2`) and silently broke the self-update
  toast. The probe now prefers the root `.venv` and keeps `backend/.venv` only as
  a fallback for un-migrated checkouts. Completes the install-path hotfix started
  in the previous commit.
- **Backend dashboard misreported the active model** — the LLM selector fell back
  to the first catalogue entry (Antigravity Gemini) whenever the configured model
  was not in the bundled catalogue (e.g. a custom local Ollama model like
  `qwen2.5:3b`), so the dashboard always showed Antigravity Gemini even though the
  backend config (`wiki status`) was correct. The unmatched model is now surfaced
  as its own "(current)" option and selected, keeping the display faithful to the
  persisted config.
- **Docs path scrub** — removed an absolute `file:///Users/...` link from
  `SYSTEM_BEHAVIOR.md` (now relative) and genericized real vault-name examples
  (`second_brain`, `/Users/<you>/...`) to `/path/to/<vault>/...` in the dev/sync
  guides. Updated `DEV_SCRIPTS_GUIDE` to match `plugin/deploy.sh`'s new local-build
  fallback when `OBSIDIAN_PLUGIN_DIR` is unset.

---

## [0.4.3] — 2026-06-07

### Fixed

- **Chat sidebar LaTeX selection** — Shift+click could not extend a text selection
  across rendered MathJax formulas because SVG elements block mouse events by
  browser default. Added `pointer-events: none` and `user-select: text` on
  `.ai-agent-chat-msg-content mjx-container` and its SVG child so that the mouse
  event passes through to the surrounding text layer, letting selection span
  formulas. The existing `copy` event interceptor then extracts LaTeX source from
  `annotation[encoding="application/x-tex"]` as before.

---

## [0.4.2] — 2026-06-07

### Added

- **LaTeX copy preservation** — selecting rendered math in the agent chat sidebar
  or quick query popover and pressing Ctrl+C now copies `$...$` / `$$...$$` LaTeX
  source instead of empty SVG content. Implemented via a `copy` event interceptor
  that extracts the source from MathJax v3 `annotation[encoding="application/x-tex"]`.
- **PDF → LaTeX conversion** — right-click "Convert to LaTeX (Copy)" (or
  Cmd+Shift+C) in the PDF viewer sends selected text to the LLM, which returns
  clean Markdown with proper LaTeX delimiters. Result is copied to clipboard.
  Shortcut registered on `ownerDocument` via `registerDomEvent` for correct
  event bubbling and automatic cleanup.

### Fixed

- **CI TypeScript check** — `buildManifest.json` is gitignored so it was absent
  in CI after checkout. Plugin-tests job now generates a minimal stub before
  `tsc --noEmit` and `vitest run`.
- **CI pytest** — `test_plugin_version_returns_build_fields` was asserting stale
  `*_fingerprint` fields removed in v0.4.1. Updated to match current schema.
- **setup.sh plugin deploy** — after building, setup.sh now reads `last_root`
  from `.cache/config/last_root` and copies `main.js`, `manifest.json`,
  `styles.css` directly to the vault's plugin directory. Removes the need for
  `OBSIDIAN_PLUGIN_DIR` or a `.env` file.

---

## [0.4.1] — 2026-06-07

### Added

- **Vault schema migration** (`wiki migrate`) — explicit upgrade path for vaults
  after a backend update changes config or Collections structure. Tracks
  `VAULT_SCHEMA_VERSION`; `wiki status` warns when a vault is behind. `wiki migrate`
  applies pending steps, scans `Collections/*.md` for files missing required
  frontmatter fields, and `--requeue` re-queues their sources for regeneration.
  `--dry-run` previews without writing. `wiki init` stamps new vaults with the
  current schema version.
- **Plugin repo-path auto-discovery** — the backend now reports its own repo root
  via `wiki plugin version` (`repo_path`), so the Obsidian plugin no longer needs
  a manually configured "Repository path". The setting becomes an optional
  override. Non-editable (site-packages) installs report `repo_path: null` and the
  plugin hides the update banner instead of showing a dead button. The 1-click
  update copies built plugin files into the currently open vault only.

### Fixed

- **Machine-local config isolation** (`config.py`) — `llm`, `search`, and
  `external` blocks are no longer stored in the synced vault `.curator/config.yml`.
  `load_config()` automatically migrates any existing machine-local blocks into
  `.cache/config/config.yml` (global cache) and rewrites the vault config without
  them. `zotero_init()` saves Zotero roots to the global cache instead of the
  vault config, so ZotMoov/data-directory paths never leak into synced state.
- **Portable Zotero source identity** (`runtime_state.py`) — `build_sources_snapshot()`
  now returns `zotero://open-pdf/library/items/<attachmentKey>` as `source_path`
  for Zotero-backed references (where `logical_source_id` starts with `zotero:`).
  The absolute local PDF path is preserved as `external_path` (device-local hint)
  and is no longer surfaced as the portable display identifier.
- **Plugin dashboard always refreshes local snapshots** (`incuratorDashboardModal.ts`) —
  Added `readFreshRuntimeJson()` which always triggers a local backend refresh
  before reading. Sources tab now uses it so the dashboard never renders a peer
  device's stale snapshot. `wiki config set llm.fallback` no longer passes
  `--local` (vault scope); LLM fallback is now written to the machine-local
  global config, consistent with how all `llm` config is handled.

---

## [0.4.0] — 2026-06-06

### Added

- **Cross-device Knowledge Sync Bridge** (`wiki db export / wiki db import`)
  - Export the knowledge DB to a portable JSONL file (`wiki db export`)
  - Import a JSONL file into another device's DB with Last-Write-Wins merge (`wiki db import`)
  - `--dry-run` option to preview changes before writing
  - `--compress` option for gzip output (`.jsonl.gz`)
  - `--since <datetime>` for incremental (delta) exports
  - Post-import automatic `wiki reindex` (skippable with `--skip-reindex`)
  - Device-local tables (embeddings, job state, FTS5 indices) are automatically excluded from exports
- **Tombstone table** (`deleted_records`) — deleted records propagate to other devices on next import
- `db_sync.record_tombstone()` helper for future delete operations to call
- **Syncthing auto-sync (Zotero-grade, one-writer-per-file)** (`wiki db autosync`)
  - Each device writes only its own `.curator/sync/dev-<id>.jsonl` snapshot and imports
    every peer's — no Syncthing write-write conflicts by construction
  - Row-level Last-Write-Wins + tombstones: concurrent offline edits on two devices both
    survive (no whole-file overwrite)
  - Structural loop prevention with **no content-hash guard**: own file never imported,
    re-export only when the local DB actually changed
  - Syncthing `*.sync-conflict-*` files imported as LWW peers, then archived under
    `.curator/runtime/sync_conflicts/`
  - Reference-Mode `sources.external_path` preserved per device on merge
    (`_DEVICE_LOCAL_COLUMNS`)
  - Device-local `.curator/sync_state.json` (excluded via `.stignore`) tracks device id +
    per-peer high-water marks
  - Obsidian plugin: on-load sync, `.curator/sync` file watcher (desktop) + 60s poll
    fallback, manual "Sync Knowledge DB" ribbon, status-bar indicator, four default-on
    settings toggles
  - Optional `auto_sync.enabled` so CLI `wiki update` exports this device's snapshot

### Changed

- `SCHEMA_VERSION` bumped from 6 → 7 (non-destructive; adds `deleted_records` table only)
- Existing vaults self-heal on next `wiki` invocation

### Fixed

- `wiki db import` reported `0 changes` after any prior export — caused by a
  `sync_meta.json` content-hash loop guard, now removed in favor of structural
  loop prevention (dry-run and real import report/apply the identical delta)

### Documentation

- `docs/guides/USER_GUIDE.md` + `USER_GUIDE_KR.md`: "Cross-Device Knowledge Sync" +
  `wiki db autosync` section
- `docs/guides/PLUGIN_GUIDE.md` + `_KR.md`: plugin auto-sync settings/triggers
- `docs/guides/SYNC_IGNORE_GUIDE.md` + `_KR.md`: `sync_state.json` exclusion;
  keep `.curator/sync/` synced
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`: §13.1 one-writer-per-file auto-sync;
  §13.3 device-local sync state
- `docs/specs/curator_schema/SCHEMA.md`: §11.17 `deleted_records` contract +
  `_DEVICE_LOCAL_COLUMNS`

---

## [0.3.3] — 2026-06-06

Initial release on `master` branch. Baseline for the v0.4.x series.
