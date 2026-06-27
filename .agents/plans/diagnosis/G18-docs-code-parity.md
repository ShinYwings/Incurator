# Diagnosis: G18-docs-code-parity
Coverage: MCP tool surface (`backend/src/curator/mcp_server.py` ↔ `docs/guides/MCP_USER_GUIDE.md` / `_KR.md`), plugin settings surface (`plugin/src/types.ts` ↔ `docs/specs/plugin_schema/PLUGIN_SCHEMA.md` §2.1 / `docs/guides/PLUGIN_GUIDE.md`), CLI command surface (`backend/src/curator/cli.py` ↔ `docs/guides/USER_GUIDE.md`), spec version-line sync (`docs/specs/*` titles ↔ build manifests). Method: enumerated each code surface and diffed against the documenting file with `grep`/`comm`.

Category coverage: (f) docs/code drift: G18-1, G18-2, G18-3, G18-4. Severity skews S2/S3 — these are documentation-contract gaps, not runtime bugs.

## Findings

### [G18-1] (f) S2 — `PLUGIN_SCHEMA §2.1 PluginSettings` interface omits 6 live persisted fields
- Loc: `docs/specs/plugin_schema/PLUGIN_SCHEMA.md:214` (interface block), vs `plugin/src/types.ts:80` (`PluginSettings`)
- Evidence: the schema's authoritative `interface PluginSettings { … }` (lines 214–267) — which states "All fields required unless marked optional" — does not declare these fields that exist in `plugin/src/types.ts` and are persisted to `data.json`:
  - `agentEffort: string` (Ollama/Antigravity reasoning-effort slot; written in `settings.ts:213,222`)
  - `ollamaHost: string` (default `"http://localhost:11434"`; used by the Ollama host setting and model fetch)
  - `autoSyncEnabled?: boolean`, `autoSyncOnLoad?: boolean`, `autoSyncWatch?: boolean`, `autoSyncNotify?: boolean` (the whole cross-device Syncthing auto-sync group; toggles in `settings.ts:546–597`, behavior in `main.ts:setupAutoSync`)
  - Confirmed: `grep -c` for each name in `PLUGIN_SCHEMA.md` returns 0. The user-facing `PLUGIN_GUIDE.md` *does* describe auto-sync by UI label ("Auto-sync", "Watch for incoming"), so the gap is specifically in the schema contract (the field-name source of truth), which CLAUDE.md designates authoritative for plugin settings.
- Fix sketch: add the six fields to the §2.1 interface with the same comments as `types.ts`, and add `agentEffort`/`ollamaHost` rules to the "Rules" list; cross-check there is no other field divergence by diffing the two interfaces. Consider a small test that asserts every `PluginSettings` key appears in `PLUGIN_SCHEMA.md` to prevent recurrence.
- Blast radius: plugin settings contract, any agent reading the schema to reason about persisted state, future migration work.
- Suggested PR: `docs/plugin-schema-settings-parity`

### [G18-2] (f) S3 — Schema declares "All fields required unless marked optional" but several real fields are optional-by-`!== false`
- Loc: `docs/specs/plugin_schema/PLUGIN_SCHEMA.md:211`, `plugin/src/types.ts:116`–`119`, `plugin/main.ts:1797`,`1811`,`1833`,`1872`
- Evidence: the `autoSync*` settings are typed optional (`autoSyncEnabled?`) and read throughout with the `!== false` idiom so absent values default to enabled. The schema's blanket "All fields required unless marked optional" sentence doesn't capture this tri-state (undefined = enabled) convention, and (per G18-1) doesn't list the fields at all. Even once the fields are added, the schema should document the `!== false` default-on semantics, since it's load-bearing for older `data.json` files.
- Fix sketch: when adding the fields (G18-1), annotate them `?: boolean` with an explicit note: "absent ⇒ treated as enabled (`!== false`)".
- Blast radius: backward-compat reasoning for older saved settings.
- Suggested PR: folds into `docs/plugin-schema-settings-parity`

### [G18-3] (f) S3 — `wiki migrate` is a registered top-level CLI command absent from USER_GUIDE
- Loc: `backend/src/curator/cli.py` (`@app.command("migrate")`), vs `docs/guides/USER_GUIDE.md`
- Evidence: `grep` for `wiki migrate` in `USER_GUIDE.md` returns 0. `migrate` is a real, non-hidden top-level command (unlike `testbed`/`jobs`/`plugin`, which are explicitly `hidden=True`). Either it is a user-facing maintenance command that should be documented (with a "you normally won't run this" caveat), or it should be marked `hidden=True` like the other internal command groups so the public CLI surface and the guide agree.
- Fix sketch: decide whether `migrate` is user-facing; if yes, add a short USER_GUIDE entry; if no, set `hidden=True`. Apply the same once-over to any other non-hidden command missing from the guide.
- Blast radius: documented CLI surface vs `--help` output.
- Suggested PR: `docs-or-cli/migrate-visibility`

### [G18-4] (f) S3 — No automated guard ties MCP tool / plugin-settings surfaces to their docs
- Loc: `backend/tests/test_spec_sync.py` (version-line guard only), `backend/src/curator/mcp_server.py`, `plugin/src/types.ts`
- Evidence: `test_spec_sync.py` enforces the spec *version-line* sync (and it currently passes — all four spec titles declare `v0.27`, matching the active 0.27.x line, so the `.0`-vs-`.2` patch suffix is expected and is **not** a drift). But there is no test asserting that (a) every `@mcp.tool()` name appears in `MCP_USER_GUIDE.md`, or (b) every `PluginSettings` key appears in `PLUGIN_SCHEMA.md`. The MCP surface happens to be fully in sync today (all 50 registered tools are documented; EN/KR both list 45 `curator_*` names), but nothing prevents the next added tool/field from silently drifting — which is exactly how G18-1 accumulated.
- Fix sketch: add a lightweight parity test: parse `@mcp.tool()`/`mcp.tool()(fn)` names from `mcp_server.py` and assert each is mentioned in `MCP_USER_GUIDE.md`; parse `PluginSettings` keys and assert each is mentioned in `PLUGIN_SCHEMA.md`. Keep it grep-level (mention-exists), not shape-level, to avoid brittleness.
- Blast radius: long-term docs/code parity maintenance.
- Suggested PR: `test/docs-surface-parity-guards`

## Positives (keep / do-not-break)
- **MCP tool docs are fully in parity**: all 50 registered MCP tools (48 `@mcp.tool()` + 2 `mcp.tool()(fn)` persona registrations) are documented in `MCP_USER_GUIDE.md`, including the 6 non-`curator_`-prefixed helpers (`check_ingest_status`, `check_source_status`, `fetch_document_section`, `get_available_models`, `promote_answer`, `search_curator`). EN and KR guides agree at 45 `curator_*` names each.
- The removed singular alias `curator_search_source` is correctly documented as removed (v0.2.1) rather than silently dropped — good deprecation hygiene, mirrored in the KR guide at the same line.
- Spec version-line sync holds: `SCHEMA.md`, `SYSTEM_BEHAVIOR.md`, `PLUGIN_SCHEMA.md`, `SEARCH_ENGINE_SCHEMA.md` all title `v0.27.x`, matching the build manifests' active minor line; `test_spec_sync.py` enforces this.
- Hidden CLI groups (`testbed`, `jobs`, `plugin`) are correctly `hidden=True`, so their absence from the user guide is intentional, not drift.
- `incuratorPdfAssetFolder` and the v0.22.0 vision-model relocation (no `latexModel` plugin setting) are documented in detail in the schema Rules, matching the code's actual behavior.

## Open questions for the human
- Is `wiki migrate` meant to be a user-facing command (document it) or internal (mark `hidden=True`)?
- Do we want the parity guard tests (G18-4) added now, or deferred until after the Phase B fix PRs land?
- Should PLUGIN_SCHEMA's `PluginSettings` block be generated from `types.ts` (single source of truth) rather than hand-maintained, to permanently end this class of drift?
