# Critique on the Architecture Proposal

Date: 2026-06-29 | Agent Persona: red_teamer (The Adversary)

## 1. Vulnerabilities & Flaws

### R1 — "Read for the crop" is actually "Read for the whole vault" (HIGH)
Denylist-minus-Read means Read works on **every `--add-dir`**, which already
includes the vault root + Zotero (`allowedRoots()`), not just the image dir. So
during ANY image turn the model can read arbitrary vault files, not just the crop.
The proposal's framing ("read the crop") undersells the actual capability grant.
This is a real hardening regression from v0.23.0 (which disabled Read precisely to
force vault access through DB-scoped MCP tools).
→ Must be stated honestly in §26.2a and the security note. The user pre-accepted
"Read on my own vault," but the plan MUST NOT pretend the scope is just the image.

### R2 — `hasImage` gate must scan the WHOLE payload, not the last turn (MED)
`buildCliCommand` builds one prompt from all history messages. An image can sit in
a prior turn. If the gate only checks the current turn, a history-replayed image
turn would NOT get Read/add-dir and silently fail. Conversely every send re-writes
all in-window images to fresh temp files (base64 is persisted on the refs), so the
gate must be "any message in the payload carries an image part."
→ Gate on the assembled `LLMMessage[]`, not on `pendingContextRefs`.

### R3 — Temp-file lifetime vs long agentic turns (MED)
Cleanup in `finally` after the CLI call is correct ONLY if the file persists for the
entire turn. A long claude turn may Read the image late. If cleanup is tied to
anything earlier than full-stream completion, the Read 404s. Also abort (user hits
Stop) must still clean up.
→ Cleanup strictly in the outermost `finally` of the CLI/stream call; per-run
subdir; startup sweep for crash leftovers. Verify abort path.

### R4 — Provider read-capability is UNVERIFIED for the chat path (HIGH, gating)
The backend proves: claude `--allowedTools Read`, codex `--sandbox read-only`, agy
native. The CHAT path differs: claude denylist-minus-Read (not allowlist), codex
`--sandbox workspace-write` (not read-only), agy with `--sandbox`. These are
*different invocations*. "workspace-write ⊇ reads" is an assumption. agy reading a
file under `--add-dir` in `-p` mode is an assumption.
→ STOP-CONDITION: each of antigravity/claude/codex must be LIVE-verified to
actually read the crop before shipping. If a provider can't, fall back to transcribe
for that provider (don't ship a silent black hole).

### R5 — `modelSupportsVision` defaults TRUE for unknown non-Ollama models (MED)
[types.ts:235] returns `true` for any non-Ollama provider+model not in the
catalogue. A text-only model on a CLI provider → treated as vision → image attached
→ model can't see it → NO transcribe fallback → crop content silently lost.
→ Either keep a transcribe fallback when the image channel yields nothing, or
document that CLI providers are assumed vision-capable (true for all current
claude/agy/codex models). At minimum: don't drop `regionText` — keep it as a
caption so something survives.

### R6 — Silent loss of normalized LaTeX in chat context (MED)
Today the chat receives a clean `<transcription>` LaTeX block. Direct-image means
the model improvises. For dense math the user MAY get worse fidelity than the
dedicated transcribe. The user accepted this for speed, but it is a real quality
delta for equation-heavy crops.
→ Keep `regionText` (pymupdf text layer) as a textual caption alongside the image
so a text fallback exists even when vision is mediocre. Document the tradeoff.

### R7 — sessions.json bloat / base64 persistence (LOW)
Vision-passthrough keeps `imageBase64` on the crop ref and persists it (today a
successful transcribe DROPPED it). Long sessions with many crops grow sessions.json
with base64. Pre-existing for pasted images, but crops now join them.
→ Acceptable; note it. Consider not persisting base64 for crops if size becomes a
problem (follow-up).

### R8 — OS sandbox may not cover the per-run image subdir (MED)
`wrapWithOsSandbox` must allow reads of `chat_images/<run>/`. It's under
`getCliCwd()` (`.cache/cli`), but Seatbelt subpath rules are exact; a new subdir
must be covered by the rule (realpath/firmlink canonicalization, per the existing
`getCliCwd` comment).
→ Verify the sandbox profile includes the image dir; reuse the resolved cwd path.

## 2. Suggested Alternatives / Required Guards

1. **Gate Read on assembled payload images, per-turn** (R2). Text-only turns keep
   the hardened denylist verbatim.
2. **Keep `regionText` as a caption** in the vision-passthrough ref (R5, R6) — the
   image is primary, the text is a safety net; never produce an empty ref.
3. **Per-provider live verification is a release gate** (R4). Ship only providers
   that demonstrably read the crop; otherwise transcribe-fallback that provider.
4. **Honest §26.2a rewrite** (R1): state that image turns grant scoped Read over
   the add-dir set (vault + image dir), gated to image-bearing turns, OS-sandboxed.
5. **Cleanup + sweep discipline** (R3, R8): outermost `finally`, per-run subdir,
   startup sweep, sandbox-covered path.
6. **Do not regress text-only turns**: assert (test) that a text-only chat turn
   still emits `--disallowedTools ... Read ...` with no `--add-dir <imagedir>`.
