# Diagnosis: G17-plugin-rest
Coverage: `plugin/src/auth/cliAuth.ts`, `plugin/src/auth/cliAuth.test.ts`, `plugin/src/zotero/assetLocalization.ts`, `plugin/src/zotero/templateRenderer.ts`, `plugin/src/types.ts`, `plugin/src/settings.ts`, `plugin/main.ts`; reference-only: `plugin/src/agent/incuratorClient.ts`, `plugin/src/ui/externalPdfView.ts`, `plugin/src/utils/deviceRegistry.ts`, `docs/specs/plugin_schema/PLUGIN_SCHEMA.md`.

Category coverage: (a) bugs: G17-1, G17-5, G17-6, G17-7; (b) redundancy: G17-9; (c) error-handling smells: G17-8; (d) legacy/dead code: G17-2, G17-3, G17-10; (e) architectural debt: G17-4, G17-11; (f) docs/code drift: G17-12; (g) perf: G17-8; (h) robustness/weaknesses: G17-1, G17-6, G17-9, G17-11; (i) UI/UX friction: G17-5.

## Findings

### [G17-1] (a,h) S2 — Auth-status poll `setInterval` is never cleared when the settings tab closes
- Loc: `plugin/src/settings.ts:318`, `plugin/src/settings.ts:339`, `plugin/src/settings.ts:343`
- Evidence: the inline "Login" button starts `authPollTimer = setInterval(…, 4000)` and only stops it via `stopAuthPoll()` on success, after 22 tries, or when another auth button is pressed. `AIAgentSettingTab` defines no `hide()` override and `authPollTimer` is a local inside `display()`. If the user clicks Login (badge shows "⏳ Waiting for login…") and then closes the Settings modal or navigates to another settings tab, the interval keeps firing every 4 s, calling `renderAuthStatusInline(authBadge, loginBtn)` against DOM nodes that were detached by `containerEl.empty()` / modal close. Each tick also spawns a CLI `command -v` probe via `resolveToken` → `assertCommandAvailable`.
- Fix sketch: store `authPollTimer` on the instance and clear it in a `hide()` override (PluginSettingTab supports `hide()`); also clear at the top of `display()` before re-render. Add a test that closing the tab mid-poll clears the timer.
- Blast radius: Settings UI, CLI probe spawning, detached-DOM writes, battery/CPU while settings closed.
- Suggested PR: `fix/settings-auth-poll-cleanup`

### [G17-2] (d) S3 — Dead `startProviderLogin` / `providerLabel` in settings.ts
- Loc: `plugin/src/settings.ts:1050`, `plugin/src/settings.ts:1062`
- Evidence: `AIAgentSettingTab.startProviderLogin()` and its only caller-helper `providerLabel()` are private and never invoked anywhere in `settings.ts` (the Login button calls `this.plugin.authResolver.startLogin(...)` directly at line 329; the command palette uses `main.ts`'s own `startProviderLogin`). Confirmed by grep: the only references are the definitions and `startProviderLogin` calling `providerLabel`. Pure dead code.
- Fix sketch: delete both methods.
- Blast radius: none (unreferenced).
- Suggested PR: `chore/remove-dead-settings-login-helpers`

### [G17-3] (d) S3 — Dead `normalizeExpiry` in cliAuth.ts
- Loc: `plugin/src/auth/cliAuth.ts:404`
- Evidence: `CLIAuthResolver.normalizeExpiry()` (handles number/string/seconds-vs-ms/date-string expiry coercion) is never called; expiry is computed by `decodeJwtExpiry` (which uses `claims.exp * 1000` directly) and `getCacheExpiry`. Confirmed by grep — only the definition exists.
- Fix sketch: delete `normalizeExpiry`, or wire it into `decodeJwtExpiry`/`getOpenAICredential` if the string/seconds normalization was actually intended.
- Blast radius: none (unreferenced).
- Suggested PR: `chore/remove-dead-normalize-expiry`

### [G17-4] (e,d) S3 — `migrateUnavailableModelDefaults` hardcodes an unbounded model denylist
- Loc: `plugin/main.ts:1326`
- Evidence: migration keeps a literal `Set` of ~13 stale model IDs (`gpt-5`, `claude-opus-4-7`, …) that must be hand-edited every time a bundled default rotates. The same function already has the correct general check (`!getModelOption(catalogue, provider, model)` ⇒ unknown model ⇒ reset to backend default), which subsumes the denylist for any model not in the live catalogue. The literal set is redundant with that check and grows every release.
- Fix sketch: drop the literal set; reset `settings.model` whenever it is non-empty and `getModelOption(...)` returns undefined for the active catalogue. Keep one test per provider.
- Blast radius: model-default migration on plugin load.
- Suggested PR: `refactor/model-default-migration-by-catalogue`

### [G17-5] (a,i) S2 — "Check DeepSeek API Key" command never checks the key; it always shows the help notice
- Loc: `plugin/main.ts:547`, `plugin/main.ts:1753`, `plugin/src/auth/cliAuth.ts:143`
- Evidence: the `login-deepseek` command ("Check DeepSeek API Key") calls `this.startProviderLogin("deepseek")` → `authResolver.startLogin("deepseek")`, which unconditionally `throw new Error(AUTH_HELP.deepseek)`. So `startProviderLogin`'s catch shows "Set DEEPSEEK_API_KEY in the Obsidian environment…" as a `Notice` even when a valid key is configured in settings or env. The command's name promises a check it does not perform.
- Fix sketch: special-case deepseek in the command (or in `startProviderLogin`) to call `resolveToken("deepseek")` and report ✓/✗ instead of always throwing the help text.
- Blast radius: command palette UX for DeepSeek users.
- Suggested PR: `fix/deepseek-check-command`

### [G17-6] (a,h) S2 — Zotero "Reload Source" always uses `profiles[0]`, corrupting notes imported with another profile
- Loc: `plugin/main.ts:321`, `plugin/main.ts:322`
- Evidence: the `incurator-zotero-refresh` command picks `const p = profiles[0]; // use first profile as default` regardless of which import profile created the note. A user with multiple profiles (e.g. "Papers" → `03_Notes/Papers` and "Books" → `03_Notes/Books`, different templates and asset folders) who refreshes a Book note will re-render it with the Papers template and write assets to the Papers folder, silently rewriting the note's structure and emitting wrong asset links.
- Fix sketch: persist the originating profile name in the note frontmatter at import time (e.g. `zotero_profile`), then resolve the matching profile on refresh; fall back to `profiles[0]` only when none is recorded. Add a multi-profile refresh test.
- Blast radius: multi-profile Zotero users, note structure, asset link correctness.
- Suggested PR: `fix/zotero-refresh-profile-binding`

### [G17-7] (a,h) S3 — Zotero refresh uses citekey as an item key when `zotero_app_url` is absent
- Loc: `plugin/main.ts:315`
- Evidence: `if (!itemKey && citekey) itemKey = citekey; // fallback to citekey if URL missing (backend will need to handle this)`. A Zotero citekey (e.g. `smith2020vision`) is not a Zotero item key (e.g. `FTW7QHWY`); passing it to `getZoteroItemMetadata` relies on an unstated backend contract that may silently fail or fetch the wrong item.
- Fix sketch: if no item key can be parsed from `zotero_app_url`, look the item up by citekey through an explicit backend "resolve citekey → item key" call rather than passing the citekey into an item-key parameter; surface a clear error when neither resolves.
- Blast radius: refresh of notes lacking `zotero_app_url`.
- Suggested PR: `fix/zotero-refresh-citekey-resolution`

### [G17-8] (c,g,h) S3 — Mixed sync/async fs and repeated inline `require` in device-registry writers
- Loc: `plugin/main.ts:1106`, `plugin/main.ts:1107`, `plugin/main.ts:1108`, `plugin/main.ts:1314`, `plugin/main.ts:1315`, `plugin/main.ts:1317`
- Evidence: `cacheBackendCommand()` and `syncDeviceRegistryFromSyncthing()` both `require("path")` and `require("fs")` inline mid-function and call synchronous `fsSync.existsSync` / `fsSync.mkdirSync` interleaved with `await fs.writeFile` (the async promises API imported at the top). The synchronous calls run on the Obsidian UI thread, the inline requires repeat on every call, and the two functions duplicate the same "ensure parent dir, then write registry JSON" sequence.
- Fix sketch: import `dirname` from `path` and `mkdir` from `fs/promises` at module top; extract a single `writeDeviceRegistry(configPath, registry)` helper used by both writers; drop inline requires and `existsSync`/`mkdirSync` in favor of `await fs.mkdir(dir, { recursive: true })`.
- Blast radius: device registry persistence (`devices.json`), backend-command caching, Syncthing registry merge.
- Suggested PR: `refactor/device-registry-fs-helper`

### [G17-9] (b,h) S2 — Global `window.open` / `shell.openExternal` monkeypatch is fragile across plugins
- Loc: `plugin/main.ts:673`, `plugin/main.ts:769`, `plugin/main.ts:773`, `plugin/main.ts:784`, `plugin/main.ts:800`
- Evidence: `onload` overwrites `window.open` and patches `electron`/`@electron/remote` `shell.openExternal`, restoring the captured originals via `this.register(...)`. If another plugin patches `window.open` after this plugin loads, this plugin's unload restores *its* captured original and silently discards the other plugin's patch (last-writer-wins teardown). The interceptor also runs for every `window.open` / `openExternal` call process-wide, not just zotero links (it does early-out on non-zotero URLs, but the indirection is global).
- Fix sketch: prefer the capture-phase DOM `click`/`auxclick` interceptor (already present at line 764) as the primary path; if the global patches are still needed, guard teardown to only restore when the current value is still this plugin's patched function (identity check) so a later plugin's patch is preserved.
- Blast radius: any other plugin that patches `window.open`/`shell.openExternal`, external-link handling after unload.
- Suggested PR: `fix/zotero-open-patch-identity-guard`

### [G17-10] (d) S3 — `getZoteroAnnotations` passthrough on the plugin is redundant with the client method
- Loc: `plugin/main.ts:934`, `plugin/src/agent/incuratorClient.ts:762`
- Evidence: `ObsidianAIAgent.getZoteroAnnotations()` is a one-line passthrough to `this.incuratorClient.getZoteroAnnotations()`. Its only caller (`externalPdfView.ts:864`) already holds `this.plugin` and could call the client directly, like other call sites do. Same one-line-passthrough shape exists for `searchZoteroItems`/`getZoteroItemMetadata` — a thin wrapper layer that adds indirection without behavior. (Low priority; only flag if a wrapper cleanup PR is already touching these.)
- Fix sketch: have `externalPdfView` use `this.plugin.incuratorClient.getZoteroAnnotations(...)` and drop the plugin passthrough, or keep the wrappers but document them as the intended façade — pick one and be consistent.
- Blast radius: external PDF annotation loading.
- Suggested PR: `chore/zotero-passthrough-consistency`

### [G17-11] (e,h) S2 — `data.json` is rewritten via `saveData` from many uncoordinated call sites
- Loc: `plugin/main.ts:139`, `plugin/main.ts:1148`, `plugin/main.ts:1210`, `plugin/main.ts:1216`, `plugin/main.ts:1264`, `plugin/main.ts:1027`, `plugin/main.ts:834`
- Evidence: `saveData(this._persistableSettings())` is called from `loadSettings` (migration), `updateSettings`, `saveSettings`, `loadSessionData` (legacy migration), the scroll-position debounce, the LLM usage callback (passed into `LLMClient`), and `onunload`. Several can interleave (a scroll-save debounce firing while `saveSettings` runs from a settings toggle), and each serializes the entire settings object. There is no single writer or dirty-flag coordination, so a late write can clobber an earlier concurrent one.
- Fix sketch: funnel all persistence through one debounced `persistSettings()` writer with a dirty flag; have callbacks mark dirty rather than each calling `saveData`. At minimum, document the single-writer assumption and ensure the scroll-position debounce and `saveSettings` cannot race.
- Blast radius: settings durability, usage accounting, scroll positions, session migration.
- Suggested PR: `refactor/plugin-settings-single-writer`

### [G17-12] (f) S3 — `imageFolder` is `@deprecated` in types but still the live migration source
- Loc: `plugin/src/types.ts:14`, `plugin/src/zotero/assetLocalization.ts:38`, `plugin/src/zotero/assetLocalization.ts:46`
- Evidence: `ZoteroImportProfile.imageFolder` is marked `@deprecated use assetFolder + assetSubfolder`, yet `resolveProfileAssetSpec` still reads it as the migration fallback and there is no one-time migration that rewrites old profiles to `assetFolder`/`assetSubfolder` and clears `imageFolder`. The deprecated field therefore lives indefinitely, and any new code that trusts the `@deprecated` tag and ignores it will diverge from the wizard/reload path that still honors it.
- Fix sketch: add a one-time profile migration in `loadSettings` that converts `imageFolder` → `assetFolder`/`assetSubfolder` and deletes `imageFolder`; then the runtime fallback can be removed and the field truly retired.
- Blast radius: legacy Zotero profiles, asset-folder resolution.
- Suggested PR: `chore/migrate-legacy-imageFolder`

## Positives (keep / do-not-break)
- `assetLocalization.ts` is a genuinely good de-duplication: the wizard and the reload command share one `localizeAnnotationImages`, with a clear comment on the bug it fixed (absolute Zotero cache paths) and content-hash-guarded overwrite to avoid sync churn.
- `_persistableSettings()` correctly strips `deepseekApiKey` before every `saveData`, restoring it from `DEEPSEEK_API_KEY` at load — matches PLUGIN_SCHEMA §2.4 (secret never persisted).
- `CLIAuthResolver` verifies the CLI binary exists (`assertCommandAvailable`) before claiming authentication, and is honest about CLI-managed sessions it cannot fully read (agy keychain, Claude).
- The quick-query / note-LaTeX-copy DOM handlers are registered per-document AND per popout window via `window-open`, with `registerDomEvent` so Obsidian unbinds them on unload.
- Reading-view math source stamping is exact-count guarded so a mis-parse can never stamp the wrong LaTeX onto a `.math` node.
- `sliceLinesByIndex` is used per math block instead of splitting the whole document on every render — a deliberate perf choice.

## Open questions for the human
- Should each Zotero note record its originating import profile (frontmatter) so refresh re-renders with the correct template/assets? (Needed to fix G17-6 properly.)
- Is the global `window.open`/`shell.openExternal` patch still required now that the capture-phase DOM interceptor exists, or can the global patch be dropped to avoid cross-plugin teardown hazards?
- Should plugin `data.json` writes be funneled through a single debounced writer, or is the current many-call-site `saveData` acceptable given observed low contention?
- Do we want a one-time migration that retires the deprecated `imageFolder` field, or keep the runtime fallback indefinitely?
