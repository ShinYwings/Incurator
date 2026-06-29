# Briefing: Chat Crop Vision-Passthrough

Date: 2026-06-29 | Author: main agent (Briefing for the Arena)

## Problem Statement

The **Cmd+Shift+X "Snip PDF Region to Chat"** flow is slow and architecturally
redundant. When a user crops a PDF region into the chat sidebar and presses Send,
the plugin performs a backend VLM round-trip (`plugin pdf transcribe`) to convert
the crop image to LaTeX text, then sends that text to the main chat model. For the
**default configuration** (no dedicated `latex_extract_model` / `vision_model`),
the backend transcribe resolver falls back to *"main chat model if vision-capable"*
— i.e. it calls **the same provider CLI the chat is about to use**. The result is
the same model invoked twice for one crop, and the user experiences a ~1 minute
"frozen Send" because the VLM blocks before any thinking indicator appears.

This briefing captures TWO distinct sub-problems that were conflated in the
v0.27.9 hotfix:

### Problem A — Timing (partially addressed, still broken)

v0.27.9 (`fix(plugin): defer VLM transcription from crop-time to send-time`) moved
the VLM call from the snip callback to `handleSend → materializeContextRefs`. But
it still runs the blocking `await` **before** `renderMessages()` paints the user
bubble + thinking indicator ([chatSidebar.ts:991](../../../plugin/src/ui/chatSidebar.ts)).
So Send still looks frozen for the full VLM duration; the timer/feedback only
starts after transcription completes. The fix relocated the freeze; it did not
remove it.

### Problem B — Redundancy (the real architectural issue, user-identified)

The backend `plugin pdf transcribe` does NOT use a separate dedicated vision
service. It uses the *same agentic provider CLI* as the chat:

- `backend/src/curator/cli.py::plugin_pdf_transcribe` → `_resolve_extract_client`
  → resolver `latex_extract_model → vision_model → main-if-vision`.
- `ClaudeCodeClient._run_with_image_path` runs:
  `claude -p "Follow the instructions..." --allowedTools Read --add-dir <.cache/vision_render>`
  — the same `claude` CLI, just with `Read` ENABLED and scoped to the `.cache`
  image dir.
- `AntigravityCliClient` reads files natively (trust-workspace); `CodexCliClient`
  uses `--sandbox read-only` to read the PNG. All three are the same CLIs the chat
  uses.

Meanwhile the chat CLI path (`llmClient.ts`) deliberately **disables `Read`**
(`--disallowedTools Bash Read Write Edit WebFetch` for claude) and saves chat
images to a temp file it tells the model to "read" — which the model then cannot
open. So today the only channel for crop content → a CLI chat model is the
backend transcribe text.

**The capability to feed an image to the chat model already exists and is proven
in the backend.** The chat path just opted out of it. Doing the transcribe as a
separate round-trip is therefore redundant for the default config.

## User Intent (verbatim constraints)

- "어차피 그 VLM Latex도 똑같은 CLI로 하는거잖아 … 어차피 똑같은 Provider로 할텐데
  그걸 왜 두번 나눠서 하는지가 이해가 안돼." → collapse the double round-trip when
  it is the same provider.
- "일부러 막은 Read 는 여기에 원래 풀기로 되어있었어. 왜냐하면 Temp 이미지 디렉터리가
  Incurator .cache 혹은 obsidian vault 안 .curator 안에 있어야하기때문에." → re-enable
  `Read`, scoped to a `.cache` / `.curator` image dir. (Security tradeoff
  pre-accepted by the user.)
- "주로 쓰는 provider는 antigravity임. claude도 할수있게 해야지. codex또한." → must work
  for antigravity (primary), claude, and codex.
- VLM-for-crops makes sense (crops are images/equations); the issue is *where* and
  *whether* to double it, not removing vision entirely.

## Hard Constraints / Invariants the Arena MUST respect

1. **§26.2a is a CHANGE, not a violation.** SYSTEM_BEHAVIOR §26.2a currently
   mandates the transcribe routing and forbids attaching the crop image to the
   main chat model's vision path. The plan MUST revise §26.2a in the same change;
   schema_guardian signs off.
2. **Convert-to-LaTeX (right-click, `transcribePdfRegion({text})`) and `add
   source` PDF ingest stay on the dedicated `vision_model`/`latex_extract_model`
   slots.** Out of scope. Only the Cmd+Shift+X → chat crop path changes.
3. **Dedicated extract/vision model opt-in is preserved.** If a user has
   configured `latex_extract_model` or `vision_model`, that is a deliberate choice
   of a separate model for transcription; the plan must not silently override it.
4. **Read scoping decision is locked** (user-approved): denylist-minus-Read +
   `--add-dir <scoped image dir>`. Not `--allowedTools Read` (allowlist) — that
   would kill the DB-scoped MCP curator tools the chat relies on.
5. **No temp-file leaks.** Mirror the backend's guaranteed-cleanup discipline
   (write under `.cache`, remove in `finally`, sweep stale on startup).
6. **OS sandbox stays.** Every CLI subprocess remains wrapped in the OS sandbox
   (v0.23.0). Adding `--add-dir <image dir>` must not widen the OS sandbox beyond
   that dir + existing allowed roots.

## Definition of Done

- Cmd+Shift+X crop → Send shows the thinking indicator instantly (no freeze).
- In the default config with a vision-capable chat model (antigravity/claude/
  codex), NO backend `plugin pdf transcribe` round-trip occurs for the crop; the
  chat model reads the crop image directly from a scoped `.cache` dir.
- Ollama / non-vision main model still gets crop content (via transcribe when a
  vision/extract model is configured) and never sees a frozen Send.
- §26.2a + PLUGIN_SCHEMA + guides updated; tests cover the new routing decision;
  v0.28.0 shipped.

## Open Questions for the Arena

- Q1: When `latex_extract_model`/`vision_model` IS configured, should the chat
  crop still route through transcribe (respect opt-in) or always prefer direct
  image (simpler)? → propose + critique.
- Q2: Where exactly should the chat image dir live — `<repo>/.cache/cli/chat_images`
  vs the vault's `.curator/`? Cleanup ownership?
- Q3: How to scope `Read` so the model reads the crop but the change is minimal
  and per-turn (only when the turn carries an image)?
- Q4: Codex/agy read-permission specifics — does `--add-dir` suffice, or is a
  sandbox mode change needed per provider?
