# Evidence Ledger — v0.28.0 Chat Crop Vision-Passthrough

Date: 2026-06-29 | Companion to `02_chat_crop_vision_passthrough.md`

## Rollback Anchor

- **Base commit (master HEAD at branch point):**
  `0cf6a76033c76556e764d8ecbe04cf7c27d97001` — "Merge pull request #68 from
  ShinYwings/hotfix/crop-vlm-defer" (v0.27.9).
- **Branch:** `feature/chat-crop-vision-passthrough`.
- **Rollback:** `git reset --hard 0cf6a76` (local branch only — never on a shared
  branch). If a merged PR regresses: `git revert -m 1 <merge-hash>` per CLAUDE.md.

## Current Dirty Worktree (pre-existing, NOT this feature)

- `plugin/package-lock.json`: benign version sync `0.27.8 → 0.27.9` (lockfile
  catch-up missed in the v0.27.9 release). Will be carried to `0.28.0` at version
  bump. No dependency graph change (`git diff` = 2 lines, the `version` fields only).
- `.agents/RELAY.md`, `.agents/ROADMAP.md`, `.agents/plans/…`: this planning change.

## Current Repository & Spec Reality (verified 2026-06-29)

- **Versions:** `backend/pyproject.toml`, `plugin/package.json`,
  `plugin/manifest.json` = `0.27.9`. Lockfile = `0.27.9` (after the pending sync).
- **Spec titles (all four at v0.27.0 line):**
  - `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md` → `# Incurator - System Behavior (v0.27.0)`
  - `docs/specs/plugin_schema/PLUGIN_SCHEMA.md` → `(v0.27.0)`
  - `docs/specs/curator_schema/SCHEMA.md` → `(v0.27.0)`
  - `docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md` → `(v0.27.0)`
  → On the v0.28.0 minor bump ALL FOUR must move to `(v0.28.0)` (test_spec_sync).
- **§26.2a current contract (to be revised):** SYSTEM_BEHAVIOR.md:1767-1772 MANDATES
  the crop path call the backend transcribe resolver and PROHIBITS attaching the
  crop image to the main chat model vision path. latex_extract_model is bound to
  "interactive surfaces (Cmd+Shift+X snip, Convert-to-LaTeX)".
- **Backend proof of same-provider transcribe (Problem B):**
  - `backend/src/curator/cli.py::plugin_pdf_transcribe` → `_resolve_extract_client`
    (`ingest_raw.py`) → resolver `latex_extract_model → vision_model → main-if-vision`.
  - `backend/src/curator/llm.py::ClaudeCodeClient._run_with_image_path` =
    `claude -p … --allowedTools Read --add-dir <vision_render_dir()>` — same CLI,
    Read enabled, scoped to `.cache/vision_render`.
  - `AntigravityCliClient.describe_image` = native file read; `CodexCliClient` uses
    `--sandbox read-only` to read the PNG. (`vision.describe_image_via_cli` prompt =
    `"Read the image file at {png}. {prompt}"`.)
- **Chat path opt-out (root cause):**
  - `llmClient.ts::buildCliCommand` claude branch: `--disallowedTools Bash Read
    Write Edit WebFetch` (Read OFF).
  - `llmClient.ts::contentToCliText`: writes chat images to `<cwd>/tmp_images`,
    returns `[Attached image saved to: <path> - Please read/view this file …]` —
    unreadable while Read is disabled.
  - `llmClient.ts::shouldUseCli`: antigravity/claude/openai → CLI; ollama/deepseek →
    HTTP. (HTTP path has real image blocks but only meets text-models.)
  - `chatSidebar.ts::materializeContextRefs`: deferred crop VLM; drops image on
    successful transcribe (`out.imageBase64 = undefined`).
  - `chatSidebar.ts::handleSend`: `await materializeContextRefs(...)` at L991 runs
    BEFORE `renderMessages()` at L1018 → residual Send-freeze (Problem A).
- **`modelSupportsVision` (types.ts:220-236):** returns `true` by default for any
  non-Ollama provider/model; Ollama needs a vision-name heuristic. → CLI providers
  treated vision-capable (red_team R5 footgun noted).
- **Existing tests to update:** `plugin/src/ui/chatSidebarSource.test.ts` lines
  ~326 ("defers VLM to send-time") and ~347 ("materializeContextRefs handles
  deferred VLM") encode the OLD contract; they must change to the new routing.

## Rollback Requirements

- Plugin-only logic + docs; **no DB migration, no destructive op.** Rollback = git
  revert/reset. No data backup needed.
- The only filesystem side effect is `<repo>/.cache/cli/chat_images/` (gitignored,
  swept). Safe to delete anytime.

## Validation Results (filled during execution)

- [x] **P0 live-vision probe (2026-06-29) — ALL PASS.** Solid-red 64×64 PNG written
  to `.cache/cli/chat_images/probe/`, each CLI invoked in the chat-path flag shape
  and asked for the dominant color:
  - **claude** `claude -p "Read the image file at <abs>…" --disallowedTools Bash
    Write Edit WebFetch --add-dir <dir>` → `red`, exit 0, **no permission hang**
    (confirms denylist-minus-Read is sufficient; allowlist `Read` not required).
  - **codex** `codex --profile obsidian exec --sandbox workspace-write --add-dir
    <dir> --skip-git-repo-check "…"` → `red`, exit 0. (Agentic cwd-echo noise
    present → plugin already uses `--output-last-message` for clean output.)
  - **agy (antigravity)** `agy --print-timeout 150s --sandbox --add-dir <dir> -p
    "…"` → `red`, exit 0. (No 429 this run.)
  → SC1 NOT triggered. All three target providers read a scoped `.cache` PNG in the
  chat-path invocation. Gate cleared.
- [ ] vitest (`plugin/vitest.config.ts`): ____
- [ ] backend ruff/mypy/pytest (incl. test_spec_sync): ____
- [ ] version-consistency (3 manifests + lockfile + 4 spec titles = 0.28.0): ____
- [ ] cleanup/no-leak check (`.cache/cli/chat_images` empty post-send): ____
