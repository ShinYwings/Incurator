# v0.28.0 Master Implementation Plan — Chat Crop Vision-Passthrough

Date: 2026-06-29
Status: PROPOSED — Arena debate concluded; awaiting USER APPROVAL before any code.
Branch: `feature/chat-crop-vision-passthrough` (from `master`)
Arena: `.agents/plans/chat_crop_vision_arena/` (00_problem, 01_proposal_architecture,
02_critique_redteam, 02_critique_schema_guardian)
Evidence Ledger: `.agents/plans/02_roadmap_evidence.md`

## 1. Objective

For the **Cmd+Shift+X "Snip PDF Region to Chat"** path, when the main chat model is
vision-capable, let that model **read the crop image directly** through the chat CLI
(scoped `Read` on a `.cache` image dir) instead of first doing a separate backend
`plugin pdf transcribe` round-trip that — in the default config — resolves to the
**same provider CLI**. Also fix the residual Send-freeze from v0.27.9.

**Definition of done:**
1. Cmd+Shift+X crop → Send paints the user bubble + "Thinking… (0s)" timer
   *instantly* (no pre-feedback blocking await).
2. With a vision-capable main chat model (antigravity / claude / codex,
   live-verified), pressing Send issues **no** `plugin pdf transcribe` call for the
   crop; the chat model reads the crop PNG from `<repo>/.cache/cli/chat_images/<run>`.
3. Non-vision main model (Ollama text) still gets crop content (backend transcribe
   when a vision/`latex_extract_model`/`vision_model` is configured) and never sees
   a frozen Send.
4. SYSTEM_BEHAVIOR §26.2a + PLUGIN_SCHEMA + EN/KR guides updated; four spec titles +
   three manifests + lockfile at `0.28.0`; tests green.

## 2. Explicit Non-Goals

- **Convert-to-LaTeX (right-click, `transcribePdfRegion({text})`) is untouched** —
  keeps the dedicated resolver. It explicitly wants LaTeX output, not a chat answer.
- **`add source` PDF ingest (`vision_model` page-VLM) is untouched.**
- **No DB / SCHEMA change.** No node prefix, frontmatter, or column changes.
- **No new provider API-key path.** Transport stays CLI-subscription.
- **No allowlist tool mode.** We keep denylist mode so DB-scoped MCP curator tools
  survive; we only remove `Read` from the denylist for image turns.
- **No change to the OS sandbox model** beyond adding the image dir to allowed reads.

## 3. Strict Quality Conditions & Release Gates

- **G-Timing:** a source-level test asserts `handleSend` renders the assistant
  thinking message BEFORE any `materializeContextRefs`/transcribe await.
- **G-Routing:** tests assert `materializeContextRefs` skips `transcribePdfCrop`
  when the main model is vision-capable and runs it only when it is not.
- **G-Scope:** a test asserts text-only CLI turns still emit
  `--disallowedTools …Read…` and NO `--add-dir <imagedir>`; image turns drop `Read`
  and add the image dir.
- **G-NoRegress:** guard test that Convert-to-LaTeX (`transcribePdfRegion({text})`)
  and ingest call sites are unchanged.
- **G-LiveVision (manual/testbed, RELEASE GATE):** antigravity, claude, codex each
  demonstrably read a crop and answer about it. A provider that cannot read falls
  back to transcribe for that provider (no silent black hole).
- **G-CI:** `npx vitest run -c ./plugin/vitest.config.ts` green; backend
  `scripts/backend-check ruff|mypy|pytest` green (incl. `test_spec_sync`).
- **G-Cleanup:** no temp PNG survives a send (success, error, or abort); startup
  sweep removes stale `chat_images/*`.

## 4. Locked Design Decisions (Arena Consensus)

1. **Single decision signal = `modelSupportsVision(mainChatModel)`** (proposal §1.1).
   Vision → direct image passthrough; non-vision → transcribe fallback. The plugin
   does NOT query the backend's dedicated-model config.
2. **Two change sites** (proposal §1.2):
   - *Image channel* (`llmClient.ts`, generalizes to all chat images): write images
     to `<repo>/.cache/cli/chat_images/<run>`, reference by path, and for
     image-bearing turns enable scoped `Read` + `--add-dir <imagedir>`.
   - *Transcribe-skip* (`chatSidebar.ts::materializeContextRefs`, crop-specific):
     keep `imageBase64` (+ `regionText` caption) when vision; transcribe only when
     non-vision.
3. **Read scoping = denylist-minus-Read, gated on payload images** (proposal §1.3 +
   red_team R2). claude drops `Read` from `--disallowedTools` for image turns; agy
   relies on native read + `--add-dir`; codex `workspace-write` + `--add-dir`. MCP
   stays (no `--allowedTools`). Gate is "any message in the assembled `LLMMessage[]`
   carries an image part," not the pending refs.
4. **Honest scope statement** (red_team R1): image turns grant the model scoped
   `Read` over the existing add-dir set (vault + Zotero + image dir), gated to
   image-bearing turns, still OS-sandboxed. §26.2a + PLUGIN_SCHEMA say so plainly.
5. **Never produce an empty ref** (red_team R5/R6): the vision-passthrough crop ref
   keeps `regionText` as a text caption beside the image, so a non-vision or
   weak-vision model still has something.
6. **Timing**: `handleSend` renders thinking BEFORE materialize; reset
   `prepareStatusText=""` so the timer starts fresh (proposal §1.4).
7. **Image dir + cleanup** (proposal §1.5 + red_team R3/R8): per-run subdir under
   `cliCacheBase()`, removed in the outermost `finally` of the CLI/stream call,
   startup sweep, OS-sandbox path verified via the resolved cwd.
8. **§26.2a is revised, not violated** (schema_guardian S1): invert only the two
   snip clauses; keep Convert-to-LaTeX + ingest + resolver discipline verbatim.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions:** Convert-to-LaTeX, ingest, DB/SCHEMA, API-key transport, allowlist
  tools, sessions.json base64 dieting (follow-up if size bites — red_team R7).
- **Stop Conditions (STOP and ask the user):**
  - **SC1:** a target provider (antigravity/claude/codex) cannot be made to read the
    crop in the chat path after reasonable effort → STOP; decide per-provider
    transcribe fallback vs deeper change.
  - **SC2:** enabling scoped Read measurably lets the model wander the vault in a way
    the user did not intend → STOP; reconsider scoping.
  - **SC3:** OS sandbox cannot be made to allow the image dir without widening it
    dangerously → STOP.
  - **SC4:** `test_spec_sync` or `version-consistency` cannot be satisfied → STOP
    (do not hack around the gate).

## 6. Evidence Ledger

See `.agents/plans/02_roadmap_evidence.md` (rollback anchor, current repo/spec
reality, dirty worktree, pre/post validation). Created before P0 coding.

## 7. Execution Phases (TDD + CI at each phase)

- **P0 — Baseline & live-vision probe (RELEASE GATE first).**
  Before writing logic, manually confirm each of antigravity/claude/codex can read a
  PNG from `<repo>/.cache/cli/chat_images/...` in the chat CLI invocation shape
  (denylist-minus-Read + `--add-dir`). Record results in the Evidence Ledger. If a
  provider fails → SC1.
- **P1 — Contract specification (docs-first, STOP gate already passed = this plan).**
  Revise SYSTEM_BEHAVIOR §26.2a (surgical, two snip clauses) + add PLUGIN_SCHEMA
  "Interactive image channel" subsection. Update EN guide(s) then `_KR.md`. Bump the
  four spec titles to `v0.28`. (No SCHEMA.md behavior edit.)
- **P2 — TDD (write failing tests).** vitest source-assertion + behavior tests for
  G-Timing, G-Routing, G-Scope, G-NoRegress; update the two existing crop tests in
  `chatSidebarSource.test.ts` to the new contract.
- **P3 — Image channel (`llmClient.ts`).** `chatImageDir()`, `contentToCliText`
  write+reference, `buildCliCommand` per-turn scoped Read + `--add-dir`, cleanup in
  the CLI/stream `finally`, startup sweep, OS-sandbox path. Verify: vitest + ruff/
  mypy unaffected (TS only).
- **P4 — Routing + timing (`chatSidebar.ts`).** `materializeContextRefs`
  vision/non-vision branch (keep image + caption vs transcribe); `handleSend` render-
  before-await reorder. Verify: vitest green.
- **P5 — Testbed/manual smoke + release.** Re-run the live-vision probe end-to-end
  per provider (G-LiveVision). Then version bump v0.28.0 (manifests + lockfile +
  four spec titles), CHANGELOG, delete this plan + arena, release commit, PR.

## 8. Files In Scope (anticipated)

- `plugin/src/agent/llmClient.ts` — image channel, scoped Read, cleanup, sweep.
- `plugin/src/ui/chatSidebar.ts` — `materializeContextRefs` routing, `handleSend`
  timing.
- `plugin/src/ui/chatSidebarSource.test.ts` (+ possibly a new `llmClient.test.ts`).
- `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md` (§26.2a) — four spec titles bump.
- `docs/specs/plugin_schema/PLUGIN_SCHEMA.md` (+ curator_schema/search_engine title
  bumps only).
- `docs/guides/PLUGIN_GUIDE.md` + `PLUGIN_GUIDE_KR.md` (and any PDF/LaTeX workflow
  guide section).
- `backend/pyproject.toml`, `plugin/package.json`, `plugin/manifest.json`,
  `plugin/package-lock.json`, `CHANGELOG.md`.
