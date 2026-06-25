# Changelog

All notable changes to Incurator are documented here.

---

## [0.25.3] - 2026-06-26
### Fixed
- **`resolveCredential` exhaustiveness** (`cliAuth.ts`): Added a `default` case
  to the provider switch that throws an explicit error with a `never`-typed guard.
  Without it, an unrecognised provider silently returned `undefined` as the
  credential, causing opaque call-site crashes.
- **`updateSettings` drops its argument** (`main.ts`): `Object.assign` now merges
  `updates` into `this.settings` before the data is saved. Previously every caller
  was saving the unchanged current settings, so settings-panel mutations were
  discarded on navigation.
- **`claude-sonnet-4-6` wrongly in unavailable-model blocklist** (`main.ts`):
  Removed from `unavailableDefaults`; it is a live, valid model ID. Its presence
  caused the plugin to force-reset users whose active model was
  `claude-sonnet-4-6` to the provider's default (Gemini) on every load.

## [0.25.2] - 2026-06-26
### Fixed
- **Stale config path references removed from docs.** All references to the
  retired `~/.config/curator/config.yml` global path and the renamed
  `.curator/config.yml` vault file have been corrected to reflect the actual
  paths used since v0.25.0: vault-scoped settings are in `.curator/settings.yml`
  and machine-local settings are in `.cache/config/config.yml` at the repo root.
- **False auto-processing callout removed from USER_GUIDE.** The `[!IMPORTANT]`
  callout that incorrectly claimed `wiki query` / `search_curator` auto-ingest
  pending sources has been replaced with an accurate note describing the manual
  pipeline (`wiki add` → `wiki build` → `wiki sync` → `wiki query`).
- **CLAUDE.md spec paths made explicit.** The `SEARCH_ENGINE_SCHEMA.md` glob in
  the version-bump instructions now lists its actual subdirectory
  (`docs/specs/search_engine/`) instead of relying on an ambiguous wildcard that
  agents misread as `docs/specs/system_behavior/`.

## [0.25.1] - 2026-06-25
### Fixed
- **Safer source/job recovery.** `wiki source rm` now keeps source files unless
  `--delete-file` is explicit, `wiki source retry` sees layer-scoped failures,
  and `wiki jobs rerun` is idempotent for already queued jobs.
- **Portable PDF/VLM ingest and L2 generation.** VLM markdown strips transient
  `.cache/vision_render` temp links before persistence; generated L2 Atom/KNU
  fields now pass an English-output guard with retry/failure behavior; generated
  CTX projections no longer expose parser-made same-document heading wikilinks.
- **Plugin source/PDF/quick-query stability.** Registered source chips stay
  inert while queued/running, generated vault block links are clickable, quick
  query preserves LaTeX copy data and now supports multiple independent popovers,
  bare PDF equation references like `(19.11)` resolve through local PDF context,
  and Convert-to-LaTeX uses an output-only dedicated transcription path.
- **L4 and PDF viewer clarity.** Completed builds now mark L4 `done`, `skipped`,
  or `error` instead of leaving eligible sources indefinitely `pending`; the
  dashboard renders `Skipped`, and PDF scroll work is coalesced per animation
  frame to reduce long-document jank.

---

## [0.25.0] - 2026-06-23
### Changed
- **Backend ↔ plugin config isolation + rename.** The vault-scoped config file is
  renamed `.curator/config.yml` → `.curator/settings.yml` so it no longer collides
  by name with the per-device backend config `<repo>/.cache/config/config.yml`.
  Rule: per-device backend settings (`llm`, `search`, `external`) and
  `devices.json` live only in the repo's `.cache/config/` (never synced); only
  device-portable, syncable settings live in the vault's `.curator/settings.yml`.
  No backward-compat: existing vaults must re-init or rename their config file.
### Added
- **`wiki status --json`.** Prints the live consolidated `{status, sources, jobs}`
  payload to stdout. The Obsidian dashboard now reads this live output directly
  (one CLI call per render, cached across panels) instead of the on-disk
  `.curator/runtime/*.json` snapshot — so it can never show stale data when a
  backend change forgets to regenerate the snapshot. The snapshot file remains a
  best-effort cache for the lightweight chat status bar only.
### Fixed
- **Dashboard ↔ `wiki status` desync ("Apply reverts after visiting Jobs").**
  `wiki config set --global` wrote `settings.yml` while the loader read
  `config.yml`, so global LLM changes (fallback / PDF-vision / LaTeX-region
  models, set via `config set`) silently reverted while the primary (set via
  `config provider`) stuck. Both `config get/set --global` now use the backend
  global `config.yml`.
- **Dashboard LLM Apply did nothing on fresh vaults.** Apply was gated on a
  successful `.curator/settings.yml` read, but LLM is a machine-local key that
  never lives there — the gate is removed (model-selected is the only precondition).
- **Dashboard changes appeared to revert.** The LLM Apply and Persona Save
  handlers did not refresh the backend snapshot after writing, so re-rendering
  showed the stale pre-save values; both now regenerate + re-read like every other
  mutation handler.
- **Dashboard model-load timer leak.** Closing the dashboard before the model
  catalogue loaded left a 400 ms `setInterval` polling a detached DOM; it is now
  tracked and cleared in `onClose()`.
### Changed
- **Edit-review loop demoted from hard gate to a hint.** A valid `ai-agent-edit`
  proposal now always opens a reviewable diff, even when the model skips the
  `[[PHASE:…]]` review markers. The old gate suppressed the diff entirely on
  token-limited / low-instruction-following models, producing "I made an edit"
  with no diff. Non-conforming answers now show the edit pills plus a soft,
  non-blocking note with an optional **Re-run with review** button; the blocked
  banner and the "Override & review anyway" escape hatch are removed.
### Added
- **Output-token truncation recovery.** Cut-off answers (Gemini `MAX_TOKENS`,
  OpenAI/Ollama `length`, Claude `max_tokens`) are detected via a normalized
  `StreamChunk.finishReason`/`truncated` mapped in every provider adapter, and
  auto-continued up to 3 times. Continuations resume mid-edit-block, are stitched
  with overlap de-dup (no duplicated text, no mangled `ai-agent-edit` fence), and
  the message stays streaming until truncation fully resolves — so edit pills /
  auto-open never fire on an in-flight partial. A manual **↪ Continue** button
  appears if it's still cut off after the cap.
### Fixed
- **Diff Viewer keyboard hijack.** Accept/Reject/navigate shortcuts now fire only
  when the diff editor or its toolbar is focused — pressing Enter in the chat box
  no longer silently applies an open diff. Opening a diff focuses it so the keys
  work immediately.
- **Multi-edit "could not be matched" / "already opening" errors.** Proposals are
  matched against the original file (order-independent), so accepting one edit can
  no longer break another's SEARCH; skipped edits are reported as not-found vs
  overlapping. A same-file re-entrant Review request now coalesces silently
  instead of raising "a diff review is already opening".
- **No more silent open failures.** `DiffViewer.show` returns a typed result and
  callers surface the exact reason (nothing changed / editor not ready).

---

## [0.23.0] - 2026-06-22
### Security
- **CLI provider tool-scope sandbox.** The Quick Query popover and chat sidebar use
  CLI agents (Antigravity `agy`, Claude, Codex) that have their own built-in tools —
  which the v0.19.0 MCP isolation did not govern, so the agent could run scripts,
  create files, and search the whole filesystem (e.g. a hallucinated
  `find_mvg_text.py`). Now `toolPolicy` reaches the CLI command builder:
  - **Popover runs the CLI tool-free** (claude `--tools ""`; codex `--sandbox
    read-only`); the **sidechat scopes tools to the allowed roots** (vault +
    configured Zotero folder + Zotero library) — claude `--disallowedTools`
    (keeping only the DB-scoped Incurator MCP tools), codex `workspace-write` +
    `--add-dir`. The dangerous `agy --dangerously-skip-permissions` /
    trust-workspace bypass is removed.
  - Antigravity's own `--sandbox` is ineffective (it still created files in testing),
    so every CLI subprocess is wrapped in an **OS sandbox** generated from the allowed
    roots — macOS `sandbox-exec` (Seatbelt, deny writes outside the roots; validated
    to contain nested child processes) and Linux `bubblewrap` (`bwrap`). On Linux,
    install `bubblewrap` (`sudo apt install bubblewrap`); without it the agentic CLI
    is blocked with a reminder. Windows CLI sandboxing is not yet supported. Setup is
    automatic — no manual profile configuration. Reads remain allowed (the contained
    harm is file creation / script execution); external user-configured `mcpServers`
    remain the user's own trust boundary.

---

## [0.22.0] - 2026-06-21
### Added
- **Dedicated PDF-extraction vision models (`vision_model` / `latex_extract_model`).**
  PDF text-layer extraction (pymupdf4llm) cannot reliably reconstruct LaTeX for math.
  You can now elect a **vision model**, configured in the **Dashboard → LLM Provider**
  card and decoupled from the main chat model, to read rendered pages. When
  `llm.vision_model` is set, every `add source` PDF page is rendered (PyMuPDF
  `get_pixmap`, bounded DPI + longest-edge cap) and transcribed to Markdown + LaTeX,
  becoming L1 with `parser_used="vlm"`. The pymupdf4llm text is retained per page as
  `parser_text`; a transient per-page VLM failure falls back to it (never aborts).
  A `vision_max_pages_per_run` rail bounds a single run. Cloud vision runs on your
  existing **CLI subscription** (Ollama in-memory, or the `claude`/`agy`/`codex` CLIs
  reading a temp PNG under `.cache/vision_render/` that is always cleaned up) — **no
  provider API keys**. Per-page transcriptions are cached by
  `(rendered-image hash, model)` so a Dashboard model switch invalidates stale L1.
  A second light slot, `llm.latex_extract_model` (empty → falls back to
  `vision_model`), powers interactive region OCR for right-click **Convert to
  LaTeX** and **Cmd+Shift+X** crop transcription. (SYSTEM_BEHAVIOR §26.2a.)

### Fixed
- **Interactive PDF snippets now use the selected PDF extraction model.**
  Right-click **Convert to LaTeX** and **Cmd+Shift+X** route through the backend
  `plugin pdf transcribe` resolver instead of the plugin main chat model. When a
  crop is successfully transcribed, the chat context carries the transcription
  text without forwarding the crop image to the main chat model's vision path.
- **Chat context decay on `Cmd+Shift+L` localized questions.** In long, edit-heavy
  sessions, a freshly referenced line range asked about as a *question* could be
  ignored while the agent proposed a whole-file edit. The root cause was a payload
  self-contradiction: a `Cmd+Shift+L` line range is both a primary-focus selection
  (recency anchor: "answer only, do not modify the document") and an editable range
  (`<editable_selection>` + the `<edit_review_loop>` contract: "you may edit these
  lines"). The plugin now suppresses both edit affordances when the latest turn is a
  localized question (a primary-focus selection present and the turn is not an edit
  request), so the recency anchor is unopposed. The decision is unconditional with
  respect to prior turns — a fresh question after an earlier whole-document edit is
  still honored. Genuine edit requests keep the full edit/diff flow.

### Changed
- **Zotero import profiles are ordered most-recently-used first.** The import
  wizard now auto-loads the most-recently-used profile (not merely the first saved)
  and orders the Import Profile dropdown recent-first via a new optional
  `lastUsedAt` timestamp, stamped when a profile is used for an import or created.
  Profiles never used keep their insertion order; the persisted profile order is
  not mutated by rendering.

---

## [0.20.0] - 2026-06-20
### Fixed
- **`context_expand` token-budget inflation.** Expansion now budgets against the
  *cumulative* pack — the tokens already consumed by the pack's selected items seed
  the budget, so a newly expanded item is admitted only if it fits within
  `limit_tokens` alongside everything already selected. Previously each expansion
  was granted a fresh full budget, so a near-full pack plus an expansion could
  overflow the model context window. Items that no longer fit return as
  `expansion_refused` (increase `limit_tokens` or refetch).
- **Retrieval provenance erased on answer-synthesis failure.** A failed
  `query_local_answer`/`query_global_reduce` validation no longer clears the
  result/trace `source_span_ids` (and sibling provenance arrays); the retrieved
  evidence is preserved exactly as the `explore` route already preserves it, so a
  synthesis failure is no longer misclassified as a recall=0 retrieval failure. The
  answer-cited spans on the `synthesis_status=failed` action remain empty.
- **Token estimate charged literal `"None"`.** A payload whose `detail` is JSON
  `null` is now costed as an empty string (1 token) instead of the 4-char `"None"`.
- Dropped a redundant `curate.yml` re-parse in `QueryOrchestrator.run` — the policy
  hash is now reused from the snapshot `context_fetch` already resolved.

### Changed
- **Explore route unified through `ContextService` (SYSTEM_BEHAVIOR §31.8).** The
  `explore` route no longer runs a divergent associative retrieval pipeline. It now
  grounds on the same `context_fetch` pack path as every other route — producing a
  `PACK-*`/`SNAP-*` snapshot, obeying the shared token budget, and recording ordered
  `CTXA-*` actions under a single `QTR-*` root. The explore-specific behavior
  (follow-up questions + provisional insight candidates) became a synthesis-phase
  consumer of that normalized pack rather than a second retrieval path.
  `explore` is admitted to `_ADMITTED_ROUTES` (not a safe baseline — it can still be
  rolled back to `local` via `INCURATOR_DISABLED_ROUTES`). `curator_fetch_context`
  now returns explore-route grounding for discovery-signal questions instead of
  silently degrading them to `local`.
- Removed the orphaned legacy explore branch in `QueryOrchestrator.run` and its
  dead helpers (`_evidence_json`, `_build_retrieval_trace`, `_question_hash`).

### Notes
- This release closes the RAG-hardening milestone's one genuinely-unimplemented
  systemic gap (explore unification). A grounding audit of the remaining
  `batch_1_to_3_audit` findings confirmed they were already shipped by the Plan A–G
  stabilization (orphaned-support truth state, CJK-safe token estimation, rank-order
  preservation, expansion state machine + budget-exhausted signal, graph
  giant-component `bridge_risk` quarantine + entity-alias resolution, degraded-mode
  eval fixtures) and are pinned by regression tests.
- Verified end-to-end on two testbed scenarios (`complex_math_backprop`,
  `testbed_template`) against a live LLM backend: `add` → `build` → `sync` →
  query (`local`/`global`/`explore`) → Mode B backprop.

## [0.19.0] - 2026-06-20
### Added
- **Shared prompt registry** (`plugin/src/context/promptRegistry.ts`). The chat
  sidebar and the Quick Query popover now assemble their security-critical prompt
  rules from one set of composable blocks (`boundaryConstraints`,
  `buildRecencyAnchor`, `SurfaceProfile`/`SIDECHAT_PROFILE`/`POPOVER_PROFILE`), so
  filesystem/tool boundaries can no longer drift between the two surfaces. The
  popover's "no filesystem access" rule is now sourced from the registry instead
  of a hardcoded duplicate.
- **Recency anchor against long-session context decay.** A `<critical_invariants>`
  block is appended LAST in each request (the strongest-attention position),
  re-asserting "answer only about the current `<primary_focus_selection>`; do not
  edit the whole document unless explicitly asked" — deferring to the existing
  pointer / `<resolved_cross_references>` rule. Fixes the case where a localized
  `Cmd+Shift+L` selection added late in a long chat was ignored and the agent
  reverted to whole-file modification.
### Fixed
- **Quick Query popover is now hard-isolated from MCP tools.** `LLMClient.streamChat`
  gained an optional `{ toolPolicy: "auto" | "none" }`; the popover passes
  `"none"` so `mcpManager.getAllTools()` is never invoked on its path. The popover
  can no longer run scripts (e.g. a hallucinated `find_mvg_text.py`), create
  files, or traverse the filesystem — it answers only from the selected passage
  and current page. The single `shouldInjectMcpTools` helper funnels the
  toolPolicy-none, CLI-provider, and no-MCP-manager cases into one no-tools path
  so they cannot diverge. The chat sidebar's tool behavior is unchanged
  (default `"auto"`).

## [0.18.0] - 2026-06-20
### Added
- Synthesized chat/query answers now cite the **original source documents**
  outside `.curator/` (e.g. `[[04_Resources/Paper]]`), not only the hidden DAG
  node. Each retrieved hit's spans are resolved to their real, visible source
  files via the new forward provenance trace `db.sources_for_spans` (span →
  `source_spans.source_id` → `sources.relpath`), and the synthesis prompt
  instructs the model to cite them. Only the `.md` suffix is stripped, so `.pdf`
  and other source links still resolve.
- `02_Wiki/` promotions (`promote_answer` / `wiki query` "save to wiki" / the MCP
  `promote_answer` tool / CLI `plugin promote`) accept the answer's
  `source_span_ids` and append a deterministic `## Sources` section linking every
  distinct source document behind the answer. Because the promoted note is a
  visible vault file, those sources appear in Obsidian's native Graph view and
  Backlinks pane — the hidden DAG cannot contribute such edges (the c3 hybrid).
  Multi-source syntheses list all contributing papers, not just the first.
- A **💾 Save to 02_Wiki** button in the chat **Sources & Trace** panel promotes the
  current answer to a durable `02_Wiki/` page, passing the trace's
  `source_span_ids` so the page's `## Sources` section (and thus native Graph /
  Backlinks) is populated. Promotion stays an explicit, human-approved action.
### Fixed
- Verified a gap left by RAG stabilization: the search materializer aggregates
  source provenance up to abstraction records (entities, relations, community
  reports, synthesis nodes) via `source_span_ids`, but this was never asserted and
  `_first_source_id` kept only a single source. `db.sources_for_spans` now returns
  every distinct origin in span order, pinned by `test_abstraction_source_trace`
  (including a multi-source synthesis node tracing back to both papers).
- `db.sources_for_spans` now resolves all distinct source relpaths with one
  batched `IN` query instead of one query per source.
- Promoting a historical chat answer now uses that answer's own trace and the
  immediately preceding user question. Older trace panels keep source navigation
  and Save to 02_Wiki available, but hide mutating context-pack actions so they
  cannot affect the active query state.

## [0.17.0] - 2026-06-20
### Fixed
- Curator DAG wikilinks are now clickable. The L1–L4 knowledge DAG lives under
  the hidden `.curator/Collections/` folder, which Obsidian's metadataCache never
  indexes — so curator-layer links such as `[[02_Atoms/ATM-9f8e7d6c]]` previously
  rendered as dead, unresolved links (no click, hover, graph, or backlinks) in the
  chat sidebar, the quick-query popover, and opened DAG pages. The plugin now
  registers a single markdown post-processor that rewrites these rendered links
  into clickable links which open the hidden page via `openLinkText`. The rewrite
  accepts an optional `.curator/Collections/` prefix, an optional `.md` suffix, and
  a `#heading`/`#^block` subpath; marks a missing target with an `is-missing`
  style instead of opening a nonexistent page; and leaves non-curator internal
  links, external links, real-vault embeds, and `[[PHASE:…]]` markers untouched.
### Notes
- Because the DAG stays hidden, curator nodes still do not appear in Obsidian's
  native Graph view or core Backlinks pane; use the chat Sources & Trace panel for
  backlink-style provenance. The backend `[[LAYER/ID]]` link format is unchanged.

## [0.16.1] - 2026-06-20
### Fixed
- Narrowed wikilink target normalization so it strips only the retired curator
  URI schemes (`legacy://` and the pre-v0.3.2 search-binary scheme) instead of
  any `scheme://` prefix. Standard external links (`http://`, `https://`,
  `obsidian://`, `zotero://`) in source paths are now preserved instead of
  having their scheme and authority mangled.

## [0.16.0] - 2026-06-20
### Changed
- Removed legacy external-search-binary runtime/build/status surfaces. The
  backend and MCP status payloads now expose the DB-native `search_*` contract
  only.
- Updated plugin dashboard/status handling to read `search_ready`,
  `search_version`, and related DB-native search fields without legacy fallback
  keys.
- Removed the obsolete benchmark harness and archived parity writeups that still
  invoked the retired external search path.

### Fixed
- Added a guard test that prevents active source, tests, plugin, scripts, specs,
  guides, and agent rules from reintroducing retired search-binary references.

## [0.15.0] - 2026-06-19
### Changed
- **Quick Query popover is now persistent.** Outside clicks and background
  scrolling no longer close or drag the popover away from the user's chosen
  context; close it explicitly with **×** or `Esc`.
- **Quick Query popover can be moved and minimized.** Drag the header to place it
  anywhere in the current window, and collapse it to a header-only state without
  losing the answer, input, or follow-up state.
- **Quick Query title follows the latest question.** The header updates on each
  submit so minimized popovers remain identifiable.

### Fixed
- Fixed old quick-query teardown order so popout-window scroll/resize listeners
  are removed before switching the active document.
- Fixed text-node outside-click handling in the quick-query document listener.

## [0.14.1] - 2026-06-19
### Fixed
- **Diff Viewer — Accept All cursor.** Accepting all changes now leaves the
  cursor at the first changed line instead of teleporting to the bottom of the
  document.
- **Diff Viewer — toolbar anchoring.** When a diff opens off-screen, the editor
  scrolls the first change into view before measuring, so the Accept/Reject
  toolbar anchors next to the change instead of jumping to the top of the screen.
- **Diff Viewer — multi-file review race.** Opening a diff is serialized behind a
  single in-flight guard, so clicking a second proposal pill can no longer
  re-point the singleton Diff Viewer to the wrong file mid-open.
- **Edit-proposal pills show honest, live status.** Each review pill is derived
  from the current file via the shared matcher: **✓ Applied** when the edit
  already appears, or when an empty-replacement deletion has already removed the
  SEARCH text; **⚠ Not found** when neither side matches. Applied/not-found pills
  no longer re-run doomed matches on click, so no "could not find" appears after
  a status pill already reported the state. Self-healing across re-render and
  session reload (no schema change).
- **Path resolution fallback.** `resolveVaultFile` adds a case-insensitive,
  whitespace-trimmed full-path scan, fixing spurious "file not found" on existing
  notes whose path differs only by case without retargeting same-named notes in
  other folders.
- **Agent no longer claims edits are applied.** The edit-loop post-edit phase now
  states edits are *proposed and pending your Accept in the Diff Viewer*; nothing
  is written to disk until you accept.

### Notes
- Triaged against the v0.11.0 Diff Viewer overhaul: navigation scroll and
  premature-disk-write were confirmed already fixed and are now pinned by
  regression tests. Unified-view polish and cross-model output determinism remain
  deferred to the Agent UI/UX & Context Architecture milestone.

## [0.14.0] - 2026-06-19
### Added
- **Enforced & observable sidechat edit-loop state machine.** Edit proposals
  now must walk a visible four-phase loop — **Analysed → Reviewed → Updated →
  Reviewed** — before any change can be accepted. A new composable
  `getEditLoopContract()` system-prompt block (anchored last, at strongest LLM
  attention) instructs the agent to emit canonical `[[PHASE:...]]` markers, and
  is appended for any edit-likely turn: a Markdown edit request, an editable
  selection, an open Markdown edit target, or a multi-turn continuation of an
  edit loop a previous answer already opened.
- **Runtime hard gate (`context/editLoopContract.ts`).** A pure validator parses
  the response; an edit-bearing answer that skips or mis-orders the loop no
  longer auto-opens the Diff Viewer. Instead the chat shows a **"Agent skipped
  the review loop"** banner with **Re-run with loop** (re-prompt) and **Override
  & review anyway** (open the diff regardless) actions. Pure Q&A with no edits is
  never gated.
- **Observable phase UI.** Conforming answers render each phase as a labeled,
  collapsible section (`.ai-agent-edit-phase[data-phase]`), with the inline diff
  review pill anchored inside the **Updated** phase. Phase markers never leak as
  raw text in any render path.

## [0.13.0] - 2026-06-19
### Added
- **Unified Agent ContextService feedback (Plan F P7).** New append-only
  `context_feedback` operation records `FBK-*` events against the exact served
  pack/snapshot with the nine locked feedback types (relevant, irrelevant,
  incorrect, stale, insufficient, duplicate, new_insight, correction,
  promotion_request). Feedback is hard-quarantined: it never edits source files,
  generated records, ranking, or truth state. A `new_insight` event enqueues a
  provisional `pending` insight candidate for human review. Exposed through
  `plugin_api.feedback_context` and the hidden `wiki plugin context feedback`
  command.
- **Sources & Trace feedback UI (Plan F P7).** Each evidence item shows
  relevant/irrelevant controls and a "Report..." menu
  (incorrect/stale/insufficient/duplicate) that records feedback through the
  backend without mutating the pack.
- **ContextService route admission and rollback (Plan F P8).** The service serves
  only Plan-A pack-integrated routes (`local`, `source-section`, `global`).
  `explore` and unknown routes degrade to `local` before retrieval runs; the
  experimental `global` route is independently disableable via
  `INCURATOR_DISABLED_ROUTES` for rollback. The decision is recorded as
  `route_admission` on the response and root trace.

### Changed
- **Sources & Trace locator resolution extracted (Plan F P6).** The pure
  open-target decision moved to `incuratorQueryTraceLocator.ts` with behavioral
  unit tests; the vault PDF locator label no longer repeats the `#page=N` anchor.

## [0.12.0] - 2026-06-19
### Added
- **Unified PDF asset identity resolution (Plan G).** Backend Reference Mode,
  Zotero-backed PDFs, add-source registration, and PDF viewer context now route
  through shared AssetIdentity/AssetSource contracts instead of ad hoc path
  conversion.
- **Device-safe PDF session sync.** Synced chat sessions no longer persist
  macOS/Linux absolute PDF paths or volatile backend path status as durable
  identity; portable identifiers are kept so each device re-resolves local paths.

### Changed
- **External PDF viewer slimmed.** Persistence/registry behavior and capture/RAG
  composition were extracted from `externalPdfView.ts`, with the PDF module LOC
  total reduced below the Plan G baseline.
- **Zotero PDF handling hardened.** Status keys, durable attachment identity,
  cache epoch invalidation, and stale localStorage path replacement now use the
  same resolver model.

### Fixed
- **Reference PDFs open the real file, not the stub.** Locator consumers now
  honor `external_uri` for Reference Mode PDFs while keeping vault stubs as
  portable metadata. Non-PDF local external references now use the desktop system
  opener instead of relying on Chromium `window.open`.
- **Add-source badge state regressions.** Zotero identity no longer depends on
  currently open PDF tabs, and added/building states are covered by contract
  tests.
- **PR review hardening.** Fresh Zotero/current-device path resolution now
  overrides stale DB/layout path hints, Reference Mode stubs no longer mark
  unresolved assets as resolved, Sources & Trace verification updates the
  displayed item, and synthesis output cannot overwrite `source_span_ids` with
  `None`.

---

## [0.11.0] - 2026-06-16
### Fixed
- **Complete overhaul of Diff Viewer UI (resolving 34 known bugs)**:
  - Implemented Inverted Decoration Model (projects diffs virtually without pre-mutating the buffer).
  - Prevented OOM crashes by setting hard limits on the LCS diffing algorithm.
  - Stabilized UI layout (floating toolbar now maintains correct viewport coordinates during scroll).
  - Enforced strict state synchronization (buffer is only modified upon explicit 'Accept').
  - Prevented DOM and event memory leaks via strict singleton enforcement and layout-change listener cleanup.
  - Added robust support for multi-file edit proposals and target-isolated routing.

## [0.10.0] — 2026-06-15

RAG Retrieval Provenance release (Plan A, Program 3). Builds the trusted
retrieval and evidence-selection substrate consumed by the forthcoming Plan F
ContextService. Every retrieval call now carries one authoritative RTR-*
execution ID, bounded and query-relevant evidence, explicit omission counts,
CurationPolicy enforcement, and resolvable structured source locators.
Specs: SCHEMA.md §22, SYSTEM_BEHAVIOR.md §28–§30, SEARCH_ENGINE_SCHEMA.md §12.

### Added

- **Authoritative RTR-\* retrieval execution ID (§30.1).** Each `build_evidence`
  call generates a unique `RTR-<8hex>` ID stamped on the `EvidencePack`, stored
  inside `query_traces.retrieval_trace_json` with `contract_version: "1"` for
  Plan F consumption (§22.4).
- **CurationPolicy forwarded through evidence assembly (§28.1 / F3).** The
  orchestrator now passes the resolved `CurationPolicy` to `build_evidence` on
  both the `fetch_context` and `run` paths, enabling workspace-scoped retrieval
  filtering.
- **Bounded, query-relevant global route (§28.2 / F4).** Community reports are
  scored by query-term overlap and capped at 10 (`_MAX_GLOBAL_REPORTS`);
  synthesis nodes capped at 6. Omitted report counts are recorded in
  `pack.omitted_counts["global_reports"]`.
- **Explicit evidence-block omission marker (§28.3 / F5).** `evidence_block()`
  appends `[N items omitted — character budget reached]` when the character
  budget causes items to be dropped. Previously items were silently truncated.
- **StructuredLocator dataclass (§29.2).** A transport-neutral, in-memory
  locator providing `source_id`, `source_kind` (vault_markdown/vault_pdf/
  external_uri/promoted_wiki), `relpath`, `heading`, `block_id`, `page_number`,
  `toc_id`, `external_uri`, and `locator_status` (exact/fallback_file/
  fallback_source/duplicate_anchor/stale/unavailable).
- **Locator resolution on source-span evidence items (§29.4).** `_span_items()`
  batch-fetches source metadata and resolves a `StructuredLocator` for every
  span-backed `EvidenceItem`. The `source-section` route is refactored to use
  the same path, gaining locators for free.
- **Plan-F handoff contract in `fetch_context` (§30.2).** The response now
  includes `retrieval_execution_id` at the top level, and each evidence item
  carries a serialized `locator` dict for Plan F to consume without re-querying.
- **`EvidencePack` extended fields (§22.3).** Added `retrieval_execution_id`
  (str) and `omitted_counts` (dict) to `EvidencePack`. Added `locator`
  (StructuredLocator | None) to `EvidenceItem`.

### Fixed

- **F3 — CurationPolicy not enforced (§28.1).** `build_evidence` now applies the
  workspace source-scope globs (`source_include`/`source_exclude`) via
  `CurationPolicy.allows_source` with a **strict all-spans rule**: an item is kept
  only when *every* backing span is in scope. Multi-source artifacts (community
  reports, synthesis, entities) are excluded entirely if any backing span is out
  of scope — their text commingles all sources, so partial inclusion would leak
  excluded content and trimming `source_span_ids` would corrupt provenance;
  `source_span_ids` is never mutated. Items dropped by scope are counted in
  `omitted_counts["policy_excluded"]`. (PR #31 review: the policy kwarg had been
  plumbed but the filter was missing; a follow-up review then tightened the
  initial "any-in-scope" rule to strict exclusion to close a private-data leak.
  The F3 oracle is behavioral — it seeds a mixed public+private report and asserts
  it is excluded whole.)
- **F4 — Global evidence query-independent and unbounded (§28.2).** All
  community reports were loaded regardless of query relevance or count.
- **F5 — Evidence block silent truncation (§28.3).** Character-budget cutoffs
  dropped items without any indicator; now always emits an explicit marker, and
  the marker (plus `\n\n` separators) never pushes the block past `max_chars` —
  it replaces the last partial item to fit. (PR #31 review fix.)
- **Locator `promoted_wiki` kind (§29.2).** Sources under `02_Wiki/` now classify
  as `promoted_wiki` instead of `vault_markdown`. (PR #31 review fix.)
- **Retrieval-trace `candidate_count` (§30.2).** `candidate_count` now reports
  `selected_count + omitted total` instead of being hardwired equal to
  `selected_count`. (PR #31 review fix.)

---

## [0.9.0] — 2026-06-15

Graph Quality release (Plan C). The trusted v0.8.0 claim layer compiles into a
reversible, support-aware knowledge graph and deterministic, claim-grounded
community reports — with a read-only graph audit that gates the serving path.
Specs: SCHEMA.md §21, SYSTEM_BEHAVIOR.md §27.

### Added

- **Entity resolution and reversible merges (§27.1).** Similar names are only
  ever *candidates*: synonyms, abbreviations, and translations merge only after
  type/context/contradiction/`avoid_merges` guards pass; ambiguous homonyms stay
  unmerged until an explicit decision. Every accepted merge keeps the origin
  identity (`redirected`) and a complete `entity_resolution_lineage` rewrite
  record, so it reverses to byte-identical pre-merge endpoints. A homonym
  surrogate-key alias model (`ALI-` ids) lets one surface form resolve to many
  distinct entities without collision.
- **Independent claim-level relation support (§27.2).** A relation is a
  proposition; re-asserting it *aggregates* `graph_relation_supports` instead of
  overwriting. Independence is counted by source lineage, so copied/forked
  sources count once. A relation becomes `active` only with **≥2 independent
  source lineages** of verified support — so a single source per topic builds no
  community reports until a second independent source corroborates the same
  relations.
- **Relation lifecycle and quarantine (§27.3).** Every relation carries
  `lifecycle_status ∈ {active, provisional, quarantined, retired}`. Weak edges
  are quarantined with a frozen reason (`unsupported`, `self_loop`,
  `contradiction`, `copied_source_only`, `bridge_risk`, `endpoint_unresolved`)
  and a re-evaluation trigger — never silently dropped or admitted. Purely
  topological cut-edge (bridge) detection gates on structure, not on the
  non-discriminative production confidence (GQ07). Authored vs extracted edge
  classes stay distinct.
- **Deterministic community construction (§27.4).** Filtered connected components
  over `active` relations between canonical entities is the explicit degraded
  fallback; the same `(graph, config, seed)` yields an identical partition, pinned
  by `config_hash`. Seeded weighted Leiden stays a benchmark-gated candidate
  (blocked on labeled relation-quality data; modularity alone is insufficient).
- **Claim-grounded community reports + reconciliation (§27.5/§27.8).**
  `rebuild_graph_generation` compiles the authoritative graph into reports whose
  identity is content/config-derived (`community_key = f(level, member_hash,
  support_hash, config_hash)`); a changed membership/support restructures and
  retires the superseded community before synthesis consumes it. Reports cite
  exact eligible active claim support — the broad whole-community-span fallback is
  removed. An unchanged rebuild is idempotent (no count amplification); a one-source
  edit/delete reconciles only its measured downstream closure.
- **Graph audit + `wiki lint` Graph Quality section (§27.6).** A read-only
  `graph_audit` asserts the §21.8 invariants (no active relation below the
  ≥2-lineage floor, no endpoint that is not a canonical entity, no reference to a
  redirected entity, every quarantined relation carries a reason + re-eval
  trigger, every served report finding cites active support). `wiki lint` gains a
  Graph Quality section that exits non-zero on release-blocking findings.
- **Live claim-grounded cutover.** The L2 compile writes one
  `graph_relation_supports` row per asserting claim, keyed by the source's lineage;
  `wiki build`/`wiki update`'s L3 (`compile_global_l3`) now grounds community
  reports on `rebuild_graph_generation`'s corroborated `active` relations, replacing
  the prior broad-span community path on the serving path.

### Changed

- **Schema v9 (additive, forward-only).** New `entity_aliases`,
  `entity_merge_proposals`, `entity_resolution_lineage`, `graph_relation_supports`
  tables + resolution/lifecycle/identity columns on `graph_entities` /
  `graph_relations` / `community_reports`. The migration infers nothing (legacy
  entities `canonical`, legacy relations `provisional`, zero alias/support rows).
- **MCP/plugin contracts unchanged.** Plan C is CLI-side; agents/plugin clients
  observe it only as better evidence on already-returned records (canonical
  entities, active relations, claim-grounded reports).

## [0.8.1] — 2026-06-15

Hotfix for the PDF crop (`Cmd+Shift+X`) context regression.

### Fixed

- **PDF crop now captures region-scoped text as primary focus.** The previous
  hotfix made the crop image-only with empty text, which caused two regressions:
  the crop image had no `<primary_focus_selection>` anchor and got buried under
  the full-page background context, and the crop's text ("line") extraction was
  lost entirely. The crop now extracts **only the text lines inside the drawn
  rectangle** (via text-layer span ∩ crop-rect intersection, in reading order)
  and uses that region text as the crop's primary focus — never the whole page
  text (the original pollution bug stays fixed) and never empty. Scanned regions
  with no selectable text fall back to an image-only reference.
- **Image-only primary context is no longer buried.** A primary user reference
  that carries an image but no text (a scanned-PDF crop or a dragged image) now
  emits an explicit `<primary_focus_selection>` anchor naming the attached image
  as the core subject, instead of the weak, ignorable "(Image context attached
  below.)" line.

---

## [0.8.0] — 2026-06-14

Evidence Compiler Integrity release (Plan B + Plan B2). Markdown/PDF source
truth compiles into stable, minimal, claim-level grounded L2 knowledge
without formula loss, unsupported broad-span grounding, duplicate
accumulation, stale records, or partial authoritative publishes.

### Added

- **Claim-level minimal support lifecycle (§26.1).** Every extracted claim
  is validated by a deterministic structural gate (verified/failed/uncertain
  trichotomy) against hydrated full span text, with ordered LaTeX
  token-sequence formula matching (direction/binding-preserving, contiguous
  sub-formula aware). Wrong-real-span citations (F6) are release-blocking.
  Evidence freshness re-checks detect stale claim supports. No gold-fixture
  lookup at runtime (overfitting ban).
- **Formula lifecycle and selective recovery (§26.2).** Provider-free
  measured-loss classification (`fragmented|image_only|parser_omitted`),
  additive `source_spans.metadata.formula_recovery` candidates with 0.80
  acceptance threshold + validator-trace + exact-claim-formula gates, and
  page-hash invalidation. Formula-bearing graph input is never destructively
  truncated.
- **Staged compile generations and atomic publish (§26.3, Plan B2).** Every
  compile runs inside a `GEN-` generation. Visibility gated at
  write/materialization time: staged units are never emitted as ATM pages,
  upserted into the graph, or materialized into search. Atomic publish
  wraps reconcile + graph persist + generation flip in a single DB
  transaction. Graph extraction (LLM) runs during staging but persistence
  is deferred to the publish transaction. A failed gate/error discards the
  staged generation with the prior authoritative state byte-untouched.
- **Source edit/delete/split reconciliation (§26.4).** Unchanged claims
  (per `semantic_hash` + exact statement equality) keep their stable ids
  and verified supports. Changed claims are re-extracted. Claims whose
  source basis disappeared are retired. Stale spans are reconciled.
- **Compiler audit surface (§26.5).** `wiki lint` gains a Compiler
  Integrity section reporting unsupported/failed/stale claims, dangling
  supports, formula inconsistencies, staged leftovers, duplicate candidates,
  and broad-fallback findings (Plan-C-assigned). Exits non-zero on
  release-blocking findings.
- **Full-span hydration (F10, SEARCH_ENGINE_SCHEMA §10.2).** Evidence items
  carry `evidence_status='ok'` when hydrated, `'stale'` when falling back
  to the 200-char preview.
- **`list_serving_units` / `list_generation_units` APIs (§26.3).**
  Serving surfaces read only authoritative-generation ∧ verified ∧
  not-retired units. Compiler reads its own staged generation.
- **Legacy NULL-generation backfill.** `init_db` attributes pre-B2 verified
  units to a deterministic synthetic authoritative generation so
  generation-scoped visibility has no permanent NULL escape hatch.

### Changed

- `SCHEMA_VERSION` bumped from 7 → 8 (`claim_supports` table,
  `compiler_generations` table, `knowledge_units` additive columns).
- `db_sync` exports/imports both new canonical tables (`claim_supports` with
  LWW, `compiler_generations` with always-upsert).
- `compile_source_l2` now runs the full copy-on-stage pipeline: stage →
  validate → gate → reconcile + graph persist + publish (atomic txn) →
  re-emit ATM/search from the authoritative served set.
- `materializer` and `reemit_projections` read `list_serving_units`.

### Fixed

- F6 (wrong-real-span citations): release-blocking gate rejects zero-overlap
  span citations.
- F7 (stale span accumulation): reconciliation removes the edited source's
  prior spans instead of lingering beside replacements.
- F10 (truncated evidence): full-span hydration replaces the 200-char
  preview in evidence packs.
- Re-publish publish gate now audits the uncommitted re-validated state
  inside the same transaction (§26.3), so it checks exactly what is about to
  be committed and a re-validation can heal a transiently-dangling support
  instead of being permanently blocked.
- Stale `formula` support rows are cleared on re-validation when the claim
  lost its formula or no longer cites the support's span (§20.5), preventing
  lingering/dangling formula links; valid recovery links are preserved.

---

## [0.7.0] — 2026-06-12

Program 1 D2 quality-observatory release.

### Added

- Fine-grained provider-free retrieval evaluation with per-family Recall@k,
  MRR, citation correctness/completeness, authoritative provenance resolution,
  hard-negative outranks, indexed-character cost, and latency.
- Query-level minimal-support labels and an auditable D2 Q06 holdout result.
- Final Program 2/3 Failure Atlas handoff contracts.
- A tracked current-architecture testbed scenario gate covering CTX/ATM/CON/SYN,
  DB-native retrieval, query traceability, and unchanged-update correctness.

### Fixed

- Search-hit `source_span_ids` now survive the public search adapter and
  evidence assembly, including global search fallback.
- Orchestrated queries persist one authoritative `QTR-` containing the engine
  retrieval trace instead of a disconnected second trace.

---

## [0.6.1] — 2026-06-12

Hotfix release. No schema or API changes.

### Fixed

- **SQLite connection leak in `db.init_db`** (`backend/src/curator/db.py`).
  `init_db()` used `with sqlite3.connect(...)`, but Python's sqlite3 context
  manager only commits/rolls back the transaction — it never closes the
  connection. The leaked connection kept the `state.sqlite-wal` /
  `state.sqlite-shm` sidecar files alive until garbage collection, which is
  timing-dependent across platforms and caused environment-dependent
  `sqlite3.OperationalError: database is locked` failures on Ubuntu 24.04
  (observed in `wiki status` bootstrap paths and the corresponding test).
  `init_db()` now closes its connection explicitly in a `finally` block, so
  no WAL sidecars outlive the call.
- **Same leak class in `db.connect()` on the setup-failure path** (review
  follow-up). `connect()` ran `executescript(SCHEMA_SQL)` and
  `_apply_migrations()` *before* its `try`/`finally`, so an exception during
  schema setup or migration leaked the connection and its WAL sidecars
  exactly like the `init_db` bug. All post-instantiation work now runs inside
  the `try` block. Regression test holds a reference to the connection and
  asserts it is closed (GC-independent) with no surviving sidecars.
- **Unbound `conn` in Zotero readers' error paths.** One site in `zotero.py`
  and both sites in `zotero_integration.py` referenced `conn` in `finally`
  without initializing it before `try`; if `sqlite3.connect()` itself raised,
  the cleanup raised `UnboundLocalError` and masked the original error. All
  sites now initialize `conn = None` first, matching the existing pattern in
  the other `zotero.py` readers. With these, every production
  `sqlite3.connect` call site is leak-safe on both success and failure paths.

---

## [0.6.0] — 2026-06-12

Program 1 (RAG & Knowledge Quality Stabilization) — Plan D1 diagnostic
baseline release. **No runtime behavior, schema, or API changes**: this
release freezes the truth contract that Programs 2/3 will be measured
against.

### Added

- **Failure Atlas diagnostic contract** (`docs/specs/failure_atlas/`).
  Versioned machine-readable case records for all thirteen suspected
  end-to-end quality failures (F1–F13), each with exact code boundary,
  minimal deterministic fixture, capture-before-repair evidence, frozen
  oracle, status lifecycle (`suspected → reproduced → assigned/accepted |
  disproven`), and downstream owner (Plan D2, Program 2, or Program 3). All
  thirteen were reproduced deterministically and assigned.
- **Deterministic reproduction suite**
  (`backend/tests/test_failure_atlas_repro.py`). Baseline tests pin the
  current defective behavior; strict-xfail oracle tests encode the desired
  contract and intentionally fail CI (XPASS) when a failure is fixed without
  updating the atlas — the mechanical anti-silent-redefinition handoff.
- **Atlas contract tests** (`backend/tests/test_failure_atlas_contract.py`)
  rejecting missing snapshot identities, missing oracles, aggregate-only
  reporting, unsupported status transitions, and dangling fixture references.
- **Mutation/degradation/atomicity experiments**
  (`backend/tests/test_failure_atlas_experiments.py`): unchanged-rebuild
  idempotency at L1/search, rename-duplication, failed-batch partial graph
  state, and provider-free lexical degradation evidence.
- **Frozen evaluation baseline** (`fixture_corpus.yml`, `qrels.yml`,
  `EVALUATION_BASELINE.md`, `backend/tests/test_failure_atlas_eval.py`):
  synthetic corpus with dev/regression/holdout/adversarial partitions,
  deterministic lexical baseline metrics (binding regression floor:
  Recall@1 = 1.0, 0 hard-negative outranks), and a runner-enforced
  no-holdout-tuning rule. Proposed Program 1/2/3 thresholds recorded,
  pending user approval.
- **Docs**: `SYSTEM_BEHAVIOR.md` §25 (Failure Atlas diagnostic contract) and
  `AGENT_WORKFLOW_GUIDE(_KR).md` §5 (running the diagnostic suite; rules when
  a change touches an atlas case).

---

## [0.5.6] — 2026-06-12

### Added

- **PDF add-source asset routing (`--asset-dir`).** Images extracted from an
  added PDF during instant L1 no longer always land in the hardcoded
  `05_Assets/<slug>/`. `wiki plugin source register` accepts a vault-relative
  `--asset-dir`; the plugin resolves it per source — Zotero-backed PDFs reuse
  the Zotero import profile's asset folder (plus a per-item subfolder from the
  item's display name), other PDFs use a sanitized source-name subfolder under
  the new `incuratorPdfAssetFolder` base folder. Unsafe values (absolute paths,
  `..` escapes, or path-resolution errors) and an empty setting fall back to
  the legacy `05_Assets/<slug>/`, and the L1 page's `![[...]]` embeds always
  reference the folder actually written (PLUGIN_SCHEMA §1.1).
- **Inert "Added" badge for tracked sources.** A successfully built source
  (`l1_ready` … `l4_ready`) now shows a single non-clickable **Added** badge in
  the chat context chip instead of clickable layer labels, so an
  already-tracked PDF can no longer be re-imported by accident. The tooltip
  still exposes the underlying layer state, and a refresh that re-derives
  `stale`/`moved`/`changed`/`missing`/`error` makes the badge actionable again
  (PLUGIN_SCHEMA §4.1.1).

### Fixed

- **PDF viewer-to-L1 adaptive routing.** Passive PDF chat no longer registers an
  untracked source. Local PDF.js text/crops remain the fast path; after an
  explicit Add Source completes L1, durable CTX ToC/section projection becomes
  available without reparsing the original PDF. Missing or preview-only CTX
  projections visibly degrade to read-only parsing, and PDF-focused turns do
  not use concept-grounded `curator_query` until the relevant source reaches L3.

### Documentation

- Documented what add-source actually does (instant L1 immediately, L2/L3
  queued to the background worker) and where extracted PDF figures land, in
  `PLUGIN_GUIDE` (EN/KR). PDF math-extraction fidelity is explicitly out of
  scope here and tracked by the RAG & Knowledge Quality Stabilization program.
- Reconciled the documentation authority and workflow contracts with the
  implementation: `state.sqlite` is authoritative, Collections Markdown is a
  disposable projection, queries are sessionless, CLI `wiki add` stops at L1
  while plugin Add Source queues L2/L3, PDF.js remains the viewer fast path,
  and correction proposals classify without silently patching generated nodes.
  Also repaired internal documentation links and advanced the spec-sync guard
  to v0.5.6.

---

## [0.5.5] — 2026-06-11

### Fixed

- **LaTeX-copy review fixes (PR #22):** an escaped backtick (`\``) no longer makes
  the math-source parser mistake it for an inline-code opener (which could drop a
  later formula); the chat/quick-query copy handler reads the element's own
  document selection (`el.ownerDocument`) so it works in Obsidian pop-out windows;
  and the reading-view math post-processor extracts section source by line index
  instead of splitting the whole document on every render (large-note perf).
- **Zotero reload emitted absolute cache image paths.** "Reload Source"
  (`Cmd+Shift+R`, formerly "Refresh Zotero Item") read the deprecated `imageFolder`
  profile field, which was empty after the wizard migrated to
  `assetFolder`/`assetSubfolder`, so it skipped localization and wrote
  `![[/Users/.../Zotero/cache/...]]` instead of vault-relative `![[05_Assets/...]]`.
  Reload and import now share one localization path (`src/zotero/assetLocalization`).
- **Changed annotation regions did not refresh.** Localization skipped any asset
  that already existed; it now overwrites an asset whose source region bytes
  changed (and only then), so edited annotations update.
- **`zotero_app_url` PDF open failed with "attachment key not found".** That URL
  carries the **parent item** key; backend `resolve-pdf` now resolves it to the
  item's child PDF attachment and returns the effective `attachment_key`.
- **Zotero annotation links did not jump to the annotation.** The plugin now uses
  the resolved child attachment key for annotation lookups, so a parent/select link
  can open the PDF *and* navigate to + highlight the annotation.
- **`Cmd+Shift+R` reloads the active Zotero note OR external PDF view**, via the
  same code path as the PDF viewer's toolbar Reload button.
- **Dashboard showed a stale backend version / provider.** The dashboard read a
  cached `runtime/status.json` first; it now forces a fresh `wiki status` snapshot
  (deduped per render burst) and reports the backend as *unavailable* instead of
  trusting a stale snapshot when `wiki status` fails. A backend upgrade or
  `wiki config provider` change is reflected on the next dashboard open/refresh
  without restarting Obsidian.
- **External PDF view lost its document after restart** (`resolveDoc failed: no
  path in docState or cache for ID`). The persisted-doc cache no longer drops a
  path-bearing entry at load (startup `existsSync` race), `setState` keeps the doc
  identity even when a restored state lacks a name, and `getState` always persists
  the path — so a reopened/restored PDF resolves the same document; a genuinely
  missing file is reported distinctly at use time.

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
