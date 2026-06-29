# Architecture Proposal: Crop Vision-Passthrough at the Image-Channel Layer

Date: 2026-06-29 | Agent Persona: lead_architect (The Proposer)

## 1. Core Logic & Implementation

### 1.1 Decision rule (resolves Q1) — drive off `modelSupportsVision(mainModel)`

The plugin already computes `canSendImages = modelSupportsVision(catalogue,
provider, model)` for the *main chat model*. Use that single signal — the plugin
does NOT need to learn the backend's `latex_extract_model` config:

```
crop in chat turn:
  if modelSupportsVision(mainChatModel):       # antigravity / claude / codex / vision-ollama
      → VISION-PASSTHROUGH: keep imageBase64, DO NOT call backend transcribe.
        The chat CLI reads the image directly (scoped Read, §1.3).
  else:                                          # ollama text model, no vision
      → TRANSCRIBE FALLBACK: call backend `plugin pdf transcribe`
        (latex_extract_model → vision_model resolver). If none configured,
        carry regionText + an explicit "attach a vision model" note.
```

Rationale: in the default config the backend transcribe resolves to *main-if-
vision* anyway, so for any vision-capable main model the transcribe is the same
model twice. Gating on `modelSupportsVision(mainModel)` collapses exactly that
redundant case and nothing else. The dedicated `vision_model`/`latex_extract_model`
slots remain authoritative for `add source` ingest and the right-click
Convert-to-LaTeX action (both out of scope).

### 1.2 Two independent change sites

**Site 1 — image channel (generalizes to ALL chat images), `llmClient.ts`:**

`contentToCliText` currently writes chat images to `<cwd>/tmp_images` and tells the
model to read them — but `Read` is disabled, so the model can't. Fix both halves:

```ts
// contentToCliText(part): image branch
const dir = this.chatImageDir();                 // <repo>/.cache/cli/chat_images/<run>
const filepath = join(dir, `img_${seq}.${ext}`);
writeFileSync(filepath, Buffer.from(part.data, "base64"));
this._pendingChatImagePaths.push(filepath);      // tracked for cleanup + add-dir
return `Read the image file at ${filepath} to see the attached image/crop, then use it to answer.`;
```

`buildCliCommand` — when the turn carries image parts, enable scoped Read per
provider (§1.3) and `--add-dir <chatImageDir>`. Gate strictly on "turn has an
image" so text-only turns keep the hardened no-Read denylist.

**Site 2 — transcribe-skip (crop-specific), `chatSidebar.ts`:**

`materializeContextRefs` runs the deferred crop VLM. Change it to honor §1.1:

```ts
if (out.pendingCropBase64) {
  if (this.mainChatModelSupportsVision()) {
    // VISION-PASSTHROUGH: keep imageBase64 so it flows through the image channel.
    // No backend round-trip. (Optionally keep regionText as caption.)
  } else {
    const extracted = await this.plugin.transcribePdfCrop(out.pendingCropBase64);
    if (extracted?.latex) { out.content = extracted.latex; out.imageBase64 = undefined; }
  }
  ref.pendingCropBase64 = undefined;
  delete out.pendingCropBase64;
}
```

### 1.3 Read scoping per provider (resolves Q3, Q4) — locked: denylist-minus-Read

```ts
// buildCliCommand, claude branch, when turn has image:
const toolArgs = ephemeral
  ? ["--tools", ""]
  : hasImage
    ? ["--disallowedTools", "Bash", "Write", "Edit", "WebFetch"]   // Read allowed
    : ["--disallowedTools", "Bash", "Read", "Write", "Edit", "WebFetch"];
// + always, when hasImage: addDirs includes chatImageDir() via --add-dir
```

- **claude**: drop `Read` from the denylist for image turns; MCP curator tools stay
  available (we keep `--mcp-config` + denylist mode, NOT `--allowedTools`).
- **antigravity (agy)**: already reads files (trust-workspace); just ensure
  `--add-dir <chatImageDir>` is present so the path is inside an allowed root.
- **codex**: `--sandbox workspace-write` already permits reads inside `--add-dir`;
  add `--add-dir <chatImageDir>`. (Backend uses read-only; workspace-write ⊇ reads.)

### 1.4 Timing (resolves Problem A), `chatSidebar.ts::handleSend`

Render the user bubble + thinking indicator BEFORE any blocking await:

1. Build `userMsg` with raw refs (crop chip shows its image thumbnail), push,
   `renderContextChips`.
2. Push `assistantMsg{isStreaming:true}`, reset `prepareStatusText=""`,
   `renderMessages()` → "Thinking… (0s)" timer starts instantly.
3. THEN materialize refs (vision-passthrough = no await; ollama = transcribe await
   happens here, with the timer already visible).
4. `userMsg.contextRefs = materialized`, persist, `buildLLMMessages`, stream.

For the vision-passthrough path there is no VLM await at all → Send is instant and
the model "sees" the crop during its own thinking.

### 1.5 Image dir + cleanup (resolves Q2)

- Location: `<repo>/.cache/cli/chat_images/<run-id>/` via `cliCacheBase()` (already
  gitignored, already the CLI cwd → inside the OS sandbox). NOT the vault `.curator/`
  (keeps disposable CLI byproducts out of the synced vault).
- Lifetime: written at prompt-build, read by the CLI subprocess, removed in a
  `finally` after the CLI call returns (mirror backend `vision_temp_png`). Add a
  startup sweep of stale `chat_images/*` dirs.

## 2. Pros & Cons

**Pros**
- Eliminates the redundant round-trip for the exact case the user flagged; one
  signal (`modelSupportsVision`) decides, no new backend config plumbing.
- Generalizes: pasted images and PDF-page captures also become readable by the CLI
  vision model (today they silently don't reach claude).
- Reuses the proven backend pattern (scoped Read + `.cache` temp PNG). Low novelty.
- Preserves the dedicated-model opt-in for ingest + Convert-to-LaTeX.

**Cons / limitations**
- Re-enables `Read` (scoped) for image turns — widens the model's file reach to the
  add-dir set (vault + image dir) during those turns. User pre-accepted; still a
  hardening delta from v0.23.0 that red_team + schema_guardian must scrutinize.
- A user who configured a dedicated `latex_extract_model` AND uses a vision main
  model loses the dedicated model for the *chat snip* (Convert-to-LaTeX still uses
  it). Behavior change to §26.2a.
- Relies on the model *choosing* to Read the referenced file (tool round-trip)
  rather than a native inline image block — same mechanism the backend already
  depends on, so acceptable, but slightly less deterministic than an API image
  block.
