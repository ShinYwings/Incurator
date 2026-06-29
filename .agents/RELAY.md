# Active Relay State

**STATUS: v0.28.0 implemented; draft PR opened.**

## Goal (DONE)

Chat Crop Vision-Passthrough — Cmd+Shift+X crops now go DIRECTLY to a
vision-capable main chat model (antigravity/claude/codex) via a scoped CLI image
channel instead of a redundant backend `plugin pdf transcribe` round-trip that, in
the default config, hits the same provider. Non-vision models (text Ollama) keep
transcribe. The deferred materialize runs after the Thinking indicator renders, so
Send no longer freezes (the residual v0.27.9 bug).

## Branch / Version

- Branch: `feature/chat-crop-vision-passthrough` (from `master`).
- Version: **v0.28.0** (Minor — new behavior + §26.2a contract change).

## Validation (all green)

- P0 live-vision probe: antigravity / claude / codex each read a scoped `.cache`
  PNG in the chat-path flag shape. PASS.
- Plugin: 635 vitest tests pass; `tsc --noEmit` clean; esbuild production build OK.
- Backend: ruff clean; mypy clean (102 files); `test_spec_sync` 10/10 (0.28.0
  across 3 manifests + 4 spec titles).

## What shipped

- `plugin/src/agent/llmClient.ts`: interactive chat image channel
  (`chat_images/<run>` temp dir, path reference, per-turn scoped Read +
  `--add-dir`, per-call cleanup + startup sweep).
- `plugin/src/ui/chatSidebar.ts`: `materializeContextRefs` vision/non-vision
  branch + `mainChatModelSupportsVision()`; `handleSend` renders thinking BEFORE
  the deferred materialize await.
- Specs: SYSTEM_BEHAVIOR §26.2a revised, PLUGIN_SCHEMA §2.1.3 added, 4 spec titles
  → v0.28.0. Guides: PLUGIN_GUIDE(.md/_KR.md).
- Tests updated/added in `chatSidebarSource.test.ts` + `llmClient.test.ts`.

## Immediate Next Action

Draft PR opened: https://github.com/ShinYwings/Incurator/pull/69

Immediate next action: wait for review/CI. After merge, truncate this file to
IDLE.

### Update (2026-06-29, Codex)

Added the user-requested Quick Query popover fix on the same
`feature/chat-crop-vision-passthrough` branch: `Section 11.1.2, p281`-style
PDF pointers now treat the explicit page locator as a fetchable target. The
resolver consumes the nearby page hint for the unresolved section, fetches that
distant page through the open Incurator PDF viewer, and injects the fetched text
as `<resolved_cross_references>` instead of leaving the model with only the
current page window.

Files touched for this side-task:
- `plugin/src/context/crossReferenceResolver.ts`
- `plugin/src/context/pdfReferenceContext.ts`
- corresponding Vitest coverage
- `docs/guides/PLUGIN_GUIDE.md`
- `docs/guides/PLUGIN_GUIDE_KR.md`
- `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`
- `CHANGELOG.md`

Validation after the side-task:
- `npx vitest run -c ./vitest.config.ts` from `plugin/`: 638 passed
- `./node_modules/.bin/tsc --noEmit -p tsconfig.json` from `plugin/`: passed
- `node esbuild.config.mjs --production` from `plugin/`: passed
- `scripts/backend-check ruff`: passed
- `scripts/backend-check mypy`: passed
- `scripts/backend-check pytest`: 1121 passed, 6 skipped, 5 xfailed

Immediate next action remains: release commit (`chore(release): v0.28.0`) →
push → open PR.

### Update (2026-06-29, Codex)

Expanded the Quick Query popover fix beyond explicit page pointers. Bare object
labels such as `(3.5)` now trigger outline-bounded on-demand page fetching:
the resolver uses the leading object/chapter number to fetch the relevant
chapter/section range from the open Incurator PDF viewer, indexes display
equation labels like `(3.5)` only on math-like lines, and re-resolves before
building `<resolved_cross_references>`. This avoids mistaking the current page's
mere mention of `(3.5)` for the actual equation target.

Additional validation:
- `npx vitest run -c ./vitest.config.ts` from `plugin/`: 640 passed
- `./node_modules/.bin/tsc --noEmit -p tsconfig.json` from `plugin/`: passed
- `node esbuild.config.mjs --production` from `plugin/`: passed
- `scripts/backend-check pytest backend/tests/test_spec_sync.py`: 10 passed

### Update (2026-06-29, Codex)

Optimized the popover reference resolver latency. Bare labels like `(3.5)` now
use ToC priority instead of scanning a broad range first: exact ToC section
matches fetch only that small section range, chapter fallback is capped smaller,
candidate pages are fetched in batches of 6, and resolution stops immediately
once the target is found. Added coverage proving an exact ToC entry for `3.5`
fetches only pages 112-114 rather than starting at chapter page 100.

Additional validation:
- `npx vitest run -c ./vitest.config.ts` from `plugin/`: 641 passed
- `./node_modules/.bin/tsc --noEmit -p tsconfig.json` from `plugin/`: passed
- `node esbuild.config.mjs --production` from `plugin/`: passed
- `scripts/backend-check pytest backend/tests/test_spec_sync.py`: 10 passed

### Update (2026-06-29, Codex)

Aligned sidechat and popover PDF page lookup around the backend cache/identity
path instead of letting popover depend only on PDF.js. Design decision: keep
`04_Resources` Reference Mode stubs as portable identity records only
(`logical_source_id`, Zotero key/link, content identity); do not write absolute
paths or extracted page text into synced stubs. Backend state/cache owns
per-device path hints and `.cache/pdf_pages/<content_hash>/<page>.txt`.

Implementation:
- `plugin/main.ts`: `fetchActivePdfPage()` now tries backend `plugin pdf context`
  first with `filePath`, `fileHash`, and `zoteroAttachmentKey`, `radius=0`,
  `maxPages=1`; it falls back to the open ExternalPdfView PDF.js fetch only when
  backend context has no exact page text.
- `backend/src/curator/plugin_api.py`: `pdf_context()` now reads/writes the
  content-hash page cache for page-window parsing, so sidechat and popover share
  repeated page fetches.
- Tests pin backend page-cache reuse and plugin backend-first fallback ordering.
- Docs/specs clarify that absolute paths are per-device call hints, not synced
  stub data.

Additional validation:
- `npx vitest run -c ./vitest.config.ts` from `plugin/`: 642 passed
- `./node_modules/.bin/tsc --noEmit -p tsconfig.json` from `plugin/`: passed
- `node esbuild.config.mjs --production` from `plugin/`: passed
- `scripts/backend-check ruff`: passed
- `scripts/backend-check mypy`: passed
- `scripts/backend-check pytest backend/tests/test_plugin_pdf_context_identity.py backend/tests/test_spec_sync.py`: 17 passed

### Update (2026-06-29, Codex)

Audited absolute-path handling across backend/system Reference Mode and the
Obsidian plugin. Found one real persistence gap: `saveSessionData()` sanitized
merged sessions, but if `.curator/sessions.json` was missing/unreadable it could
write current in-memory context refs directly. That path could persist
runtime-local PDF `backendStatus.sourcePath/currentPath/candidatePath` values
from macOS/Linux into synced chat history.

Fix:
- `plugin/main.ts`: every `sessions.json` write now passes through
  `sanitizeSessionDataForSync()` immediately before `adapter.write()`.
- `plugin/src/mainSecurity.test.ts`: source-level regression coverage pins that
  sanitizer-before-write contract.
- Plugin guide EN/KR and plugin schema now state that first-write and
  legacy-migration session saves are sanitized too.

Audit classification:
- `04_Resources` Reference Mode stubs remain portable; generated frontmatter
  contains `logical_source_id`/Zotero key, not absolute `target_path`.
- Backend `sources.external_path`, `.cache/pdf_pages`, `.cache/config/last_root`,
  and `.curator/runtime/*.json` are device-local state/cache.
- Plugin `localStorage` external PDF paths and `data.json` backend path settings
  are per-device hints; synced `sessions.json` now strips absolute context paths
  and runtime backend status before all writes.

Additional validation:
- `npx vitest run -c ./vitest.config.ts src/mainSecurity.test.ts src/utils/sessionData.test.ts` from `plugin/`: 19 passed
- `./node_modules/.bin/tsc --noEmit -p tsconfig.json` from `plugin/`: passed

### Update (2026-06-29, Codex)

Audited and fixed runtime temp/cache file placement. New rule now documented:
Incurator-created temp/cache byproducts must live under either
`<incurator-repo>/.cache/` or `<vault>/.curator/`; no OS temp fallback for our
runtime artifacts.

Fixes:
- `plugin/main.ts`: PDF crop backend transcription temp images now live under
  `<vault>/.curator/runtime/pdf_crops/` and are removed in `finally`, instead of
  `os.tmpdir()`.
- `plugin/src/agent/llmClient.ts`: plugin CLI cache uses
  `<repo>/.cache/cli/` when `incuratorRepoPath` is known, otherwise
  `<vault>/.curator/runtime/cli/`; no `tmpdir()` fallback. CLI child env
  `TMPDIR`/`TEMP`/`TMP` now points to the same cache root's `tmp/`.
- `backend/src/curator/llm.py`: Antigravity logs and Codex output files now use
  repo `.cache/llm/...`; backend provider CLI subprocess temp env points to
  `.cache/llm/tmp`.
- `backend/src/curator/zotero.py` and `zotero_integration.py`: Zotero SQLite
  lock-bypass copies now use repo `.cache/zotero_sqlite/` instead of OS temp.
- `backend/src/curator/ingest_llm.py`: removed an unused OS-temp insight staging
  directory entirely.
- Added source-level hygiene tests and updated docs/specs/CHANGELOG.

Audit note:
- Remaining `/tmp` references are sandbox isolation policy/tests or test fixture
  paths, not Incurator-created runtime temp/cache files. External-tool required
  config files such as Codex/Gemini MCP config remain in those tools' own config
  locations by necessity and are documented as not temp/cache byproducts.

Validation:
- `npx vitest run -c ./vitest.config.ts` from `plugin/`: 644 passed
- `./node_modules/.bin/tsc --noEmit -p tsconfig.json` from `plugin/`: passed
- `node esbuild.config.mjs --production` from `plugin/`: passed
- `scripts/backend-check ruff`: passed
- `scripts/backend-check mypy`: passed
- `scripts/backend-check pytest`: 1123 passed, 6 skipped, 5 xfailed

Follow-up in the same audit:
- Backend validation tool caches also moved under repo `.cache/`:
  `backend/pyproject.toml` now uses `.cache/pytest`, `.cache/ruff`,
  `.cache/mypy`, and `scripts/backend-check ruff` now passes the backend config
  explicitly so Ruff does not recreate root `.ruff_cache`.
- Removed generated root `.pytest_cache`, `.ruff_cache`, `.mypy_cache`.
- Updated `.gitignore`, workspace gitignore template, contribution/sync-ignore
  docs, and AGENTS/CLAUDE to reflect repository `.cache/` as the cache root.
- Re-ran final validation after this follow-up:
  - `npx vitest run -c ./vitest.config.ts && ./node_modules/.bin/tsc --noEmit -p tsconfig.json && node esbuild.config.mjs --production`: passed
  - `scripts/backend-check ruff`: passed
  - `scripts/backend-check mypy`: passed
  - `scripts/backend-check pytest`: 1123 passed, 6 skipped, 5 xfailed
  - Root cache check: only `.cache/` exists; no `.pytest_cache`, `.ruff_cache`,
    or `.mypy_cache`.

### Update (2026-06-29, Codex)

Addressed PR review feedback for PDF context fallback robustness:
- Backend PDF page cache helpers now tolerate missing or non-string content
  hashes, skip cache writes without a valid hash, and parse the requested pages
  directly instead of crashing on `.strip()`.
- Plugin `fetchActivePdfPage()` now catches backend PDF context/network failures
  and falls back to the open PDF.js viewer as intended.
- Folded the remaining local review hardening into the same follow-up commit:
  claude image-turn `--add-dir` is confined to the scoped image dir when `Read`
  is re-enabled; pre-spawn CLI setup failures clean image temp dirs; Zotero
  SQLite temp-copy failures remove placeholder files.
- Changelog updated under v0.28.0.

Validation:
- `scripts/backend-check pytest backend/tests/test_zotero_tools.py backend/tests/test_plugin_pdf_context_identity.py backend/tests/test_spec_sync.py`: 31 passed
- `npx vitest run -c ./vitest.config.ts src/agent/llmClient.test.ts src/mainSecurity.test.ts`: 63 passed
- `scripts/backend-check ruff`: passed
- `scripts/backend-check mypy`: passed
- `./node_modules/.bin/tsc --noEmit -p tsconfig.json`: passed
