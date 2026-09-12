# Plugin Proposal: Finish the Backend-Driven GC Surface Without Truncating Chats
Date: 2026-09-11 | Agent Persona: Plugin and Session Retention Reviewer

## 1. Core Logic & Implementation

### Shipped behavior, established from current code

- The requested **Dashboard GC tab has never shipped**. `plugin/src/ui/incuratorDashboardModal.ts:37–47` enumerates Overview, Jobs, Sources, Access, Traces, Synthesis, Insights and Persona; routing at lines 173–182 has the same set. A repository-wide plugin search finds no GC command invocation. This is a concrete missing user-facing capability, not a new policy that needs invention.
- The backend already provides `gc plan --json` and `gc run --json` (`backend/src/curator/commands/gc.py:39–64,129–188`). Preview returns prunable session/run counts, reclaimable paths/bytes and retained reasons. Session choices are `0/30/90/180/365` (`backend/src/curator/gc.py:251–254`), with zero meaning keep forever. The prompt-run cap is opt-in and zero by default (lines 257–270). No UI implementation should duplicate either selection algorithm.
- Sessions live in synced `.curator/sessions.json`, separately from settings (`plugin/src/types.ts:57–68`; `main.ts:1638–1652`). Merge unions deletion ids and uses whole-session last-write-wins (`plugin/src/utils/sessionData.ts:15–52`). Tombstones must remain: an offline peer can otherwise restore a deleted session. Absence from a local array is not deletion; the ineffective 30-session slice was removed (`ChatSidebarView.ts:4705–4726`, `sessionCapIsNotRetention.test.ts`).
- Full active-session provider replay is an explicit v0.82.3 correction (`CHANGELOG.md:25–31`; `ChatSidebarView.ts:1510` iterates all messages). Do not reintroduce a history window, summary replacement, or image removal under the name retention.
- Auto-reference text/outline/window payloads are stripped only from persisted copies, while thumbnail base64 remains (`sessionData.ts:63–99`). The transcript visibly consumes the base64 (`ChatSidebarView.ts:2948–2951,4511–4514`). Existing `autoRefPayloads.test.ts` covers that distinction. Manual attached image/text payloads are also meaningful prompt history (`ChatSidebarView.ts:1524–1528`).
- `data.json` is predominantly configuration and cumulative provider counters, not another transcript ledger (`types.ts:86–135`). Scroll positions already have a 100-entry recency cap (`utils/scrollPositions.ts:39–62`). Zotero profiles and recent-item state are persisted separately after successful migration (`main.ts:1469–1478`); sessions have legacy migration (`main.ts:1693–1703`). Therefore “expire data.json every N days” is not justified: it would reset settings and state rather than collect garbage. An old canonical session plus duplicate legacy settings fields merits a separate evidence-backed migration audit, not blind key removal here.

### Smallest justified product increment

Implement the already-requested GC Dashboard surface in a minor release, preserving session schema and existing default policies. The panel should load the backend's effective retention policy and live preview, offer the existing session windows plus the existing unreferenced-run cap, write via `wiki config set --local`, and explicitly separate saving policy from running GC. No auto-GC timer is implied by the existing commands or this proposal. Show retained categories and reasons as first-class results; an unreadable session count must appear as unavailable, not “-1 sessions” or zero.

A live effective-policy source is necessary. The existing preview JSON omits effective windows/caps, while `readVaultConfig()` reads project YAML only (`incuratorDashboardModal.ts:189–194`) and `config set` defaults to global (`commands/config.py:85–109`). Reading project YAML alone would misrepresent inherited global policies. Prefer an additive `policy` object in `gc plan --json`, containing backend-normalized values and choices; then persist chosen values through explicit `--local` so this vault's Dashboard cannot silently change another vault's global settings. This is a public CLI response extension and should be the single planned contract change of the UI release. Existing keys remain compatible.

Use the established `runWikiCommand()` → `plugin.runBackendCommand()` boundary (`incuratorDashboardModal.ts:312–324`). Do not edit settings YAML or sessions JSON directly from the new panel. A failed config write keeps the previously applied policy visible. Refresh preview after successful config changes and GC. Clearly label reclaimed cache bytes separately from session/run counts: current `bytes_reclaimable` counts cache only, and SQLite row deletion does not promise filesystem shrinkage.

### Destructive execution is an unresolved engineering prerequisite, not a product policy question

A naïve Run GC button is unsafe with current writers:

1. Backend `prune_sessions()` reads/splits the file at `gc.py:381`, later overwrites via `atomic_write_text` at line 399.
2. `durable_io.atomic_write_text()` replaces at line 115 without read-modify-write coordination; its purpose is intact bytes, not preserving concurrent changes.
3. Plugin saves use an in-process queue plus `adapter.process()` at `sessionStore.ts:66–102`. There is no shared backend/plugin lock. Backend replacement can overwrite a plugin message/session committed since backend read; a plugin process callback can conversely publish a snapshot predating newly written GC tombstones.
4. Backend can prune the selected inactive-by-age session and choose another id (`gc.py:395–397`), but sidebar `this.messages` is a separate clone (`ChatSidebarView.ts:4701–4702,4746–4747`). Blindly reloading `sessionData` without refreshing the sidebar lets the next persist copy old visible messages into the newly selected session (`persistCurrentSession`, lines 4774–4791).

Before shipping writable GC from Dashboard, adversarially reproduce these schedules in disposable fixtures and settle one coherent serialization/reconciliation design. A JavaScript flag or disabling the button while generating covers only one plugin instance; a backend-only lock does not constrain Obsidian's writer; “reread just before rename” still leaves a race. Do not claim any of these alone fixes the disease. Moving session mutation behind one backend command would be a larger plugin persistence contract change and must be a separate release with a compatibility/rehearsal plan. An explicit local maintenance barrier could be sufficient only with a demonstrated account of every writer and exact reload behavior; it must not erase the user's unsaved draft or implicitly abort generation.

If the team cannot establish complete local-writer coordination in this release, ship preview + policy controls as an explicitly partial milestone, leave the destructive Dashboard action open in the roadmap, and explain the engineering dependency. This does not require a user product decision: it is implementation sequencing of an already requested capability. Do not claim B1/B2 complete. The root cause should then receive its own immediate planned release, not a permanent “close Obsidian” workaround.

### Remaining user decisions and non-decisions

- **No clarification needed** to expose the requested existing session choices and prompt-run cap, or retain all thumbnails and full replay. The user already chose that shape, delegated prompt-run policy, and corrected replay.
- **Actual product decision** before deliberately dropping/downsampling visible image history or replacing it with a summary. Keeping the current behavior while other work proceeds is not a capability reduction.
- **Actual product decision** before imposing new query-trace, compiler-generation or job-history deletion windows; domain review must establish live reference floors first.
- **Not a preference setting:** session/DB tombstone expiry. There is no peer-acknowledgement/recovery proof; offer no expiry control.
- **Actual production execution:** GC deletion still requires the user's explicit action/authorization. Implementation tests must use temporary stores. Merely opening Dashboard or saving a window must not run deletion.

### Tests, docs and acceptance conditions

- Backend pytest: effective policy JSON matches the exact policy used by plan/run with global inheritance, local override, missing/malformed settings; preserve current keys and corrupt-session signaling. CLI smoke on testbed only, with isolated cache/config paths.
- Plugin Vitest: tab routes, backend CLI argument arrays, allowed choices, inherited policy rendering, config failure, corrupt/unavailable preview, no automatic deletion on open/save, cancel performs no run, in-flight duplicate prevention, exact post-run refresh, cache-byte wording. Use behavioral UI/controller tests, not substring-only implementation mirrors.
- Destructive integration gates before adding Run: concurrent plugin save/GC loss schedule, tombstone publication, selected-session replacement, no stale-view copy into another id, streaming/draft preservation, save failure, peer tombstones, unreadable canonical file untouched.
- Preserve current session store, payload and full-replay regressions. Run backend pytest/ruff/mypy, plugin Vitest and plugin-directory `npx tsc --noEmit` per repo rules.
- English-first docs: `docs/guides/PLUGIN_GUIDE.md` Dashboard/session sections, `docs/guides/USER_GUIDE.md` GC CLI section, matching `_KR.md` guides; `docs/specs/plugin_schema/PLUGIN_SCHEMA.md` Dashboard contract and system/CLI specification section describing JSON policy. Minor version bump requires all four spec-title version lines synchronized.
- Explicit documentation inventory for data.json contents/bounds and retained image/tombstone semantics closes the policy-description gap without deleting any of them.

## 2. Pros & Cons

The proposal implements a plainly requested missing surface and uses existing retention policy, keeping scope auditable. It preserves the corrected full replay and visible images, does not invent another retention configuration, and distinguishes real product choices from technical follow-up work. It also rejects a destructive UI whose backend writer would turn routine cleanup into session loss.

The current backend JSON is insufficient to render inherited policy faithfully, so even the minimal useful panel needs an additive CLI contract. Full destructive integration may require a separate session-writer release; pretending this is a tiny button would hide its actual blast radius. A preview/control-only increment is therefore partial by definition and must remain visibly queued, with root-cause execution safety next. Image deduplication and tombstone compaction may save disk later, but both change synced storage semantics and are unsuitable additions to this increment without independent migration/recovery design.
