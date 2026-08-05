# plugin_lifecycle Proposal: Gate G0 Adjudication of Pass A Findings F1–F4
Date: 2026-08-04 | Agent Persona: Plugin Correctness Adjudicator

> **Purpose.** Pass A of `01_proposal_plugin_lifecycle.md` filed four findings (F1..F4)
> that no critique document has yet refuted or confirmed. This document closes Gate G0
> by independently re-verifying each one against the repo at
> `/Users/shin/shinywings/Incurator` (branch `chore/system-defect-audit-arena`, HEAD
> `c69c620`, v0.42.1 baseline merged). Every quote below was read by me from the live
> file at the stated line; I did not carry over the inspector's citations on trust.
>
> **Verdict summary**
>
> | # | Pass A severity | My verdict | My severity |
> |---|---|---|---|
> | F1 | P1 | **CONFIRMED — and deepened** | **P1** |
> | F2 | P2 | **CONFIRMED** | P2 |
> | F3 | P3 | **CONFIRMED as latent** (spec violation live, user impact latent) | P3 |
> | F4 | P3 | **DOWNGRADED** — real spec-vs-code divergence, but the failure branch is not reachable on any shipping macOS | P3 |
>
> No finding was refuted. No new finding is filed — the adjacent surfaces I probed
> (§2 below) were clean or already covered by tests.

---

## 1. Core Logic & Implementation

### F1 [P1] — CONFIRMED, and worse than filed: the popover's cross-reference fetcher is unpinned, and the foreign page text is written back into the *original* document's live BM25 index

Pass A's claim was that a tab switch during quick-query cross-reference resolution
splices pages from the wrong PDF into `<resolved_cross_references>`. I set out to break
that claim on four axes and could not. Each axis, with the evidence I read:

#### (a) Is the identity really unpinned on that path? — YES

`plugin/main.ts:1772-1786` — the guard exists and is explicitly opt-in:

```ts
  async fetchActivePdfPage(
    pageNum: number,
    expectedDocumentId?: string
  ): Promise<string | undefined> {
    const pdf = this.activeContext.pdfPage;
    // Pin the viewer and its identity BEFORE any await. The viewer fallback
    // below must never re-resolve to whatever document happens to be active
    // after the backend round-trip: a tab switch during that await would
    // otherwise read a page out of the wrong PDF, using bounds that were
    // validated against the original one (PLUGIN_SCHEMA §13.7).
    const pinnedView = this.app.workspace.getActiveViewOfType(ExternalPdfView);
    const pinnedDocumentId = pinnedView?.getDocumentId();
    if (expectedDocumentId !== undefined && pinnedDocumentId !== expectedDocumentId) {
      return undefined;
    }
```

The `expectedDocumentId !== undefined` conjunct is the entire opt-in. Note precisely what
the comment's own pin does and does not cover: `pinnedView`/`pinnedDocumentId` pin the
**viewer fallback** (re-checked at `main.ts:1808`), but the **backend-first branch** at
`main.ts:1787-1799` keys on `pdf = this.activeContext.pdfPage` read at line 1776 — fresh
on *every* invocation. So even with the viewer fallback pinned, an unpinned caller gets
whatever `activeContext` says at the moment of each call.

The local-PDF-tool runner opts in (`plugin/main.ts:1857-1860`):

```ts
      // Identity is passed down so the fetch fails closed if the document
      // changes mid-flight, rather than silently reading the swapped one.
      fetchPage: (pageNum: number) =>
        this.fetchActivePdfPage(pageNum, this.getActivePdfDocumentId()),
```

Quick Query does not (`plugin/src/ui/quickQueryPopover.ts:484-492`):

```ts
        resolvedReferencesBlock = await resolveSelectionReferencesBlockAsync(
          this.capturedSelection,
          {
            ...activeContext.pdfPage,
            searchIndex: this.plugin.getActivePdfDocumentIndex(),
            searchDocumentId: this.plugin.getActivePdfDocumentId(),
          },
          (pageNum) => this.plugin.fetchActivePdfPage(pageNum)
        );
```

Grep confirms these are the only two call sites in the plugin:
`grep -n "fetchActivePdfPage" plugin/main.ts plugin/src/**` returns `main.ts:1772` (def),
`main.ts:1860` (guarded), `quickQueryPopover.ts:491` (unguarded). Nothing else.

#### (b) Is a document swap actually reachable during that await? — YES, by a registered workspace event

This is the axis Pass A argued but did not demonstrate. I traced it. `plugin/main.ts:710-720`:

```ts
    this.registerEvent(
      this.app.workspace.on("active-leaf-change", (leaf) => {
        // Don't overwrite PDF/markdown context when the chat sidebar gets focus
        if (leaf?.view.getViewType() === CHAT_VIEW_TYPE) return;
        this.lastContentLeaf = leaf;
        this.updateActiveContext(leaf);
```

and `updateActiveContext` **wholesale reassigns** the field, it does not patch it
(`plugin/main.ts:1917-1938`):

```ts
    } else if (viewType === EXTERNAL_PDF_VIEW_TYPE) {
      ...
      this.activeContext = {
        viewType: "pdf",
        filePath: file?.path,
        ...
      };
      ...
        if (pdfCtx) this.activeContext.pdfPage = pdfCtx;
```

So a tab switch to paper B fires `active-leaf-change`, which runs synchronously on the
event loop — i.e. it *can and will* interleave with any `await` inside
`resolveSelectionReferencesBlockAsync` — and replaces `activeContext.pdfPage` with B's
`filePath`/`fileHash`/`zoteroAttachmentKey`. The very next `fetchActivePdfPage(n)` then
issues `incuratorClient.getPdfContext({ filePath: B.filePath, fileHash: B.fileHash, ... })`
(`main.ts:1789-1796`) and returns **page n of paper B**. Nothing in the call chain
compares that against paper A. The `pinnedView` fallback re-resolves through
`getActiveViewOfType(ExternalPdfView)`, which is also now B's view.

The await window is not theoretical. `resolveSelectionReferencesAsync` is a multi-round
resolver with three separate `await fetchPages(...)` sites:
`plugin/src/context/pdfReferenceContext.ts:355` (direct-fetch round loop, up to
`DIRECT_FETCH_ROUND_LIMIT` iterations), `:366` (adjacent-equation probe, one page per
iteration), `:401` (outline fallback, batched). Each round awaits a backend round trip
before deciding the next round's targets, so the whole operation spans several sequential
backend calls — a multi-second window in which the user is, by construction, sitting
there waiting and free to click another tab.

#### (c) Does `resolveSelectionReferencesBlockAsync` or any upstream guard pin identity? — NO. It does the opposite: it *writes the foreign text back into paper A's index*

This is the part Pass A missed, and it upgrades the blast radius from "this one answer"
to "this document's search index for the rest of the session."

`plugin/src/context/pdfReferenceContext.ts:261-263`:

```ts
  const searchDocId = source.searchDocumentId ?? "selection";
  const index = source.searchIndex ?? new PdfDocumentIndexService();
  if (!source.searchIndex && pages.length) index.upsertDocument("selection", pages, outline);
```

`searchDocId` and `index` are captured **once**, before any fetch, from what the popover
passed at `quickQueryPopover.ts:488-489` — i.e. paper A's live document index and paper
A's document id. Then, per fetched page (`pdfReferenceContext.ts:296-302`):

```ts
    for (const result of fetched) {
      if (!result) continue;
      pageTextMap.set(result.pageNum, result.text);
      const page: PdfWindowPage = { pageNum: result.pageNum, text: result.text };
      index.upsertPage(searchDocId, page, outline);
      changed = true;
    }
```

`index` is `this.plugin.getActivePdfDocumentIndex()`, which is `pdfView?.getDocumentIndex()`
(`main.ts:1813-1817`) — the **viewer's own persistent index**, not a scratch copy. So
paper B's page text is upserted under paper A's `documentId`, permanently, for the
lifetime of that view. Every subsequent `searchPages(...)` in this resolution
(`pdfReferenceContext.ts:273`) and every later `search_pdf_anchor` local-PDF-tool call
(`main.ts:1861-1866`) can now retrieve paper B's prose as if it were paper A's. The
identity guard on the *tool* path (which Pass B correctly praises) is bypassed by
poisoning the index the tool reads from.

There is also no compensating guard anywhere upstream: the resolver never sees a document
id it can compare against, and `runQuery` captures nothing but `capturedSelection`
(`quickQueryPopover.ts:477-497`).

#### (d) Does an existing test cover it? — NO

```
grep -rn "fetchActivePdfPage|expectedDocumentId|documentId" \
  plugin/src/ui/quickQueryPopover.test.ts plugin/src/context/pdfReferenceContext.test.ts \
  plugin/src/context/crossReferenceResolver.test.ts plugin/src/context/quickQueryContext.test.ts
```
→ **zero matches.** No test in the popover, resolver, cross-reference, or quick-query
context suites references document identity at all. The identity re-check that *is*
tested lives on the tool path (`localPdfToolExecution.test.ts`), which is the guarded
call site.

#### Spec position

`docs/specs/plugin_schema/PLUGIN_SCHEMA.md:2033-2053` (§13.2) states the contract the
code breaks, in one sentence:

> "The fetch path must match sidechat: try backend PDF context first using the richest
> available portable identity (`source_id`, file hash, vault relpath, or Zotero attachment
> key …), then fall back to the open PDF.js viewer."

Sidechat genuinely satisfies this — its fetcher closes over locals captured *before* the
resolver starts (`plugin/src/ui/chat/ChatSidebarView.ts:1782-1797`):

```ts
          async (pageNum) => {
            if (
              !client.available ||
              (!sourcePath && !sourceStatus?.sourceId && !pdf.fileHash && !pdf.zoteroAttachmentKey)
            ) {
              return undefined;
            }
            ...
            const targetCtx = await client.getPdfContext({
              filePath: sourcePath,
              sourceId: sourceStatus?.sourceId,
              fileHash: pdf.fileHash,
              zoteroAttachmentKey: pdf.zoteroAttachmentKey,
```

`sourcePath`, `sourceStatus`, and `pdf` are closure locals — a tab switch cannot move
them. The popover's `(pageNum) => this.plugin.fetchActivePdfPage(pageNum)` re-reads
mutable plugin state on every call. That is the divergence, stated in the spec's own
words. §13.2 further requires the fetched text land in `<resolved_cross_references>` and
"remain higher priority than generic current-page background" — so the wrong-document
text is inserted at the *highest* context priority.

#### Failure scenario (concrete, as I reconstructed it)

1. User reads paper A in `ExternalPdfView`, selects on p.12: *"…as shown in Theorem 4.2 (p. 31)"*, opens Quick Query, asks "what does that theorem assume?".
2. `runQuery` (`quickQueryPopover.ts:477`) refreshes context (paper A) and enters
   `resolveSelectionReferencesBlockAsync`. Round 1 awaits `fetchPages([31])`
   (`pdfReferenceContext.ts:355`).
3. During that await the user clicks the tab holding paper B. `active-leaf-change` fires
   → `updateActiveContext` (`main.ts:715`) → `this.activeContext.pdfPage` is now B.
4. Round 2's `fetchActivePdfPage(31)` reads `activeContext.pdfPage` = B (`main.ts:1776`),
   `expectedDocumentId` is `undefined` so the guard at `main.ts:1784` is skipped, and the
   backend returns **paper B page 31**.
5. That text is `index.upsertPage(paperA_documentId, …)` (`pdfReferenceContext.ts:300`) —
   paper A's live index now contains paper B's page 31 — and is emitted into
   `<resolved_cross_references>`.
6. The model answers about paper A's Theorem 4.2 using paper B's text, at top context
   priority, with no marker that the two came from different documents. Under the audit
   rubric this is **serving wrong knowledge** with no visible signal.

**Severity: P1 confirmed.** I considered P0 ("serving wrong knowledge") and deliberately
held at P1 because nothing is written to the vault or to `state.sqlite` — the corruption
is confined to one in-memory answer plus one in-memory viewer index, and closing/reopening
the PDF tab clears it. It is P1 rather than P2 because there is no workaround available to
a user who does not know the hazard exists.

**Fix direction.** Capture the document identity once at `runQuery` entry, alongside
`capturedSelection`, and thread it as `expectedDocumentId` on every fetch:
`const pinnedDocId = this.plugin.getActivePdfDocumentId();` then
`(pageNum) => this.plugin.fetchActivePdfPage(pageNum, pinnedDocId)`. Additionally make
`expectedDocumentId` a **required** parameter of `fetchActivePdfPage` so no future call
site can silently opt out (there are only two call sites — this is cheap). Consider
having the resolver stop upserting when a fetch returns `undefined`, so a guard-rejected
fetch degrades to "unresolved" rather than half-populating the index. Regression test:
drive `resolveSelectionReferencesBlockAsync` with a `fetchPageText` stub that flips
`getActivePdfDocumentId()` between rounds and assert (i) no foreign text reaches the
block, and (ii) `index.upsertPage` is never called with foreign text under the pinned id.

---

### F2 [P2] — CONFIRMED: `syncAgyMcpConfig` silently discards a malformed `~/.gemini/settings.json` and commits non-atomically, while the function it calls on the next line refuses to

Re-read from source. `plugin/src/agent/llm/LLMClient.ts:2518-2546`:

```ts
  private syncAgyMcpConfig(): void {
    const geminiDir = join(homedir(), ".gemini");
    mkdirSync(geminiDir, { recursive: true });
    ...
    const settingsPath = join(geminiDir, "settings.json");
    let existing: Record<string, unknown> = {};
    try {
      existing = JSON.parse(readFileSync(settingsPath, "utf-8"));
    } catch { /* file missing or malformed — start fresh */ }

    const merged = {
      ...existing,
      admin: { ...(existing.admin as Record<string, unknown> | undefined ?? {}), mcp: { enabled: true } },
      mcpServers,
    };

    writeFileSync(settingsPath, `${JSON.stringify(merged, null, 2)}\n`);
    syncAgyHeadlessReadPermission(geminiDir);
  }
```

The sibling handling the *adjacent* file, invoked one line later —
`plugin/src/agent/llm/LLMClient.ts:70-86` and `:118-127`:

```ts
  let existing: Record<string, unknown> = {};
  if (existsSync(settingsPath)) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(readFileSync(settingsPath, "utf-8"));
    } catch (error) {
      throw new Error(
        `Antigravity CLI settings are malformed; refusing to overwrite ${settingsPath}: ${...}`,
      );
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error(
        `Antigravity CLI settings must be a JSON object; refusing to overwrite ${settingsPath}.`,
      );
    }
```

```ts
  const tempPath = join(cliDir, `settings.json.incurator-${process.pid}-${...}.tmp`);
  try {
    writeFileSync(tempPath, `${JSON.stringify(merged, null, 2)}\n`);
    renameSync(tempPath, settingsPath);
  } finally {
    rmSync(tempPath, { force: true });
  }
```

Two verified defects, plus one Pass A did not name:

1. **Silent replacement on parse failure.** `catch { }` with no `logger.warn`, no `Notice`,
   no rethrow. The `...existing` spread shows the *intent* is to preserve unrelated
   top-level keys (theme, auth selection, telemetry, context file names) — that intent is
   silently abandoned the moment the parse fails, and the file becomes a two-key
   `{admin, mcpServers}` document. §32's observable-degradation posture applied to a file
   the plugin does not own.
2. **Non-atomic commit.** `writeFileSync` straight onto the live path (`:2544`), on **every**
   agy launch (`buildCliCommand` → `syncAgyMcpConfig` at `:2184`). A crash or quit mid-write
   truncates the file; the next launch's `catch` at `:2533` swallows the truncation and
   finishes the destruction. The plugin's own durable-write contract (§2.2,
   `utils/durableJsonStore.ts`) and the sibling at `:118-127` both use temp+rename.
3. **Not caught by Pass A: non-object valid JSON is also silently discarded.**
   `JSON.parse("null")`, `JSON.parse("[]")`, `JSON.parse("42")` all succeed, so `existing`
   becomes `null`/`[]`/`42`; `{...null}` is `{}` and `(42).admin` is `undefined`, so the
   file is replaced with no error on that path either. The sibling explicitly rejects
   exactly this shape at `:80-84`. There is no type narrowing at all on `:2532`.

**Existing coverage:** `grep -rn "syncAgyMcpConfig" plugin/src` → the only test reference is
`llmCliLifecycle.test.ts:57`, which **stubs the method out**. Behavior is unpinned.

**Spec position.** `PLUGIN_SCHEMA.md:2160-2164` (§13.6) states the rule — but scoped only to
the sibling file:

> "…the plugin MUST atomically merge the single read-only rule `$read_file$()` into
> `permissions.allow` in the CLI-owned `~/.gemini/antigravity-cli/settings.json`. It MUST
> preserve unknown top-level keys, unknown `permissions` keys, and existing allow entries,
> and MUST refuse to overwrite malformed JSON…"

`grep -n "mcpServers|\.gemini/settings" docs/specs/plugin_schema/PLUGIN_SCHEMA.md` returns
`:373` (a type field), `:531`, `:2239` — none of which govern the write to
`~/.gemini/settings.json`. So the spec gap Pass A alleged is real: the file is written by
the plugin and governed by nothing. Under ground rule 5 the doc and the code are both wrong.

**Failure scenario.** User keeps `"theme": "GitHub"` and a `// my servers` line comment in
`~/.gemini/settings.json` for standalone Gemini CLI use. They send one antigravity-backed
message from Obsidian. `buildCliCommand` (`:2184`) → `syncAgyMcpConfig` → parse throws on
the comment → `existing = {}` → `writeFileSync` replaces the file with `{admin, mcpServers}`.
Their CLI config is gone, silently.

**Severity: P2 confirmed.** I considered P0/P1 — destroying a user config file *is* data
loss — and held at P2 for two reasons: the loss is conditioned on the file already being
unparseable-as-strict-JSON (I could not verify from this repo whether the Gemini CLI
tolerates JSONC, so I do not assert the comment case as certainly reachable), and the file
is outside the vault and outside Incurator's data model. The non-atomic write, by contrast,
is unconditionally live on every agy launch, which is what keeps this above P3.

**Fix direction.** Lift the validated sibling pattern into a shared helper and use it for
both files: strict parse → reject non-object → `logger.warn` + skip (or throw, matching the
sibling) on malformed → commit via temp+`renameSync`. Then add one sentence to §13.6
covering `~/.gemini/settings.json` so both files are held to one rule. Test by pointing
`homedir()` at a temp dir with a malformed file and asserting the file is unchanged.

---

### F3 [P3] — CONFIRMED as a live spec violation with latent user impact: the non-streaming CLI path cannot clean up after a pre-spawn throw

The spec sentence is real and unqualified — `PLUGIN_SCHEMA.md:818-820` (§2.1.3):

> "**Cleanup robustness.** Cleanup (below) MUST also run if pre-spawn setup
> (`getCliCwd`/`buildCliCommand`) throws synchronously before any child spawns, since no
> `close`/`error` event fires in that case."

Streaming path — conforms (`plugin/src/agent/llm/LLMClient.ts:1348-1377`):

```ts
      const prompt = this.messagesToCliPrompt(messages);
      const imageRunDir = this._chatImageRunDir;
      ...
      try {
        cwd = this.getCliCwd();
        ...
        ({ command, args, env, stdin } = this.buildCliCommand(...));
      } catch (err) {
        // Synchronous setup failed before any child spawn, so neither "close"
        // nor "error" will fire — clean the image dir here so it never leaks.
        this.cleanupChatImageDir(imageRunDir);
        reject(err instanceof Error ? err : new Error(String(err)));
        return;
      }
```

Non-streaming path — the identical prologue sits **outside** the `try`
(`plugin/src/agent/llm/LLMClient.ts:1945-1962`, `:2008-2013`):

```ts
    const prompt = this.messagesToCliPrompt(messages);   // writes the PNGs
    const imageRunDir = this._chatImageRunDir;
    const cwd = this.getCliCwd();                        // CAN THROW
    ...
    const { command, args, env } = this.buildCliCommand(  // CAN THROW
      prompt, outputFile, provider, false, toolPolicy, model,
    );

    try {
      const { stdout, stderr } = await execFileAsync(...);
      ...
    } finally {
      if (outputFile && existsSync(outputFile)) { unlinkSync(outputFile); }
      this.cleanupChatImageDir(imageRunDir);              // unreachable on a pre-spawn throw
    }
```

Both prologue calls really do throw on live paths, verified:
`getCliCwd` → `cliCacheBase()` throws `"Incurator CLI cache requires incuratorRepoPath."`
when the setting is empty (`:2295-2299`, reached via `:2336`); `buildCliCommand` →
`syncAgyMcpConfig` → `syncAgyHeadlessReadPermission` throws at `:76`, `:81`, `:93`, `:103`;
`buildCliCommand` → `wrapWithOsSandbox` throws the agy refusal at `:2443-2447`.

**Coverage gap verified.** `plugin/src/agent/llmClient.test.ts:1002-1007`:

```ts
  it("cleans up the per-call image dir if streaming setup throws before spawn", () => {
    ...
    expect(source).toContain("this.cleanupChatImageDir(imageRunDir);\n        reject(");
  });
```

That is a source-substring assertion matching the *streaming* branch's exact indentation
and its `reject(` continuation. It is structurally incapable of noticing the
`completeViaCli` gap. Note the spec sentence itself is not scoped to streaming, so the
test under-implements the spec it is meant to pin.

**Why I still hold this at P3, not P2.** I checked reachability rather than assuming it.
`grep -rn "\.complete(" plugin/src plugin/main.ts` (excluding tests) returns exactly two
call sites: `quickQueryPopover.ts:535` and `LLMClient.editText:2653`. `editText` builds two
messages whose `content` is a plain string (`:2628-2648`) — no image parts possible. The
popover's messages come from `buildQuickQueryContextMessages`, and
`grep -rn "image|Image" plugin/src/context/quickQueryContext.ts` returns **zero matches** —
that builder never emits an image content part. Since `cleanupChatImageDir(dir)` early-returns
on a falsy dir (`:2312-2313`) and `_chatImageRunDir` is only set by an image part, the leak
cannot fire today. It is one image-capable `complete()` caller away from firing, and the
spec clause is violated *now*.

**Failure scenario (once a caller exists).** An image-bearing turn sent with
`streamingEnabled: false`, provider `antigravity`, on a Linux host without `bwrap`:
`contentToCliText` writes `<repo>/.cache/cli/chat_images/<run-id>/img_0.png`;
`buildCliCommand` → `wrapWithOsSandbox` throws the refusal at `:2443`; the decoded user
crop survives on disk until the next plugin load runs `sweepStaleChatImages()`. Spec: "No
temp image survives a completed send" (`PLUGIN_SCHEMA.md:823-824`).

**Fix direction.** Move `getCliCwd()`/`buildCliCommand()` inside the existing `try` in
`completeViaCli` (the `finally` already does the right thing), or wrap them in their own
try/catch that calls `cleanupChatImageDir(imageRunDir)` and rethrows. Replace the
indentation-sensitive source assertion with a behavioral test that stubs `getCliCwd` to
throw and asserts the run dir is gone — parameterized over **both** CLI entry points.

---

### F4 [P3] — DOWNGRADED: real spec-vs-code divergence, but the "macOS without `sandbox-exec`" branch is unreachable on any shipping macOS, so the user-facing misdiagnosis Pass A described is hypothetical

The code claim is exactly as filed. `plugin/src/agent/llm/LLMClient.ts:2427-2435`:

```ts
    const plan = buildSandboxPlan({
      platform: process.platform,
      allowedRoots: roots,
      home: realOr(homedir()),
      tmpdir: realOr(this.cliTempDir()),
      sandboxExecPath: process.platform === "darwin" ? "/usr/bin/sandbox-exec" : "",
      bwrapPath: process.platform === "linux" ? this.resolveBwrap() : "",
      provider,
    });
```

The asymmetry is genuine: the Linux arm probes for real
(`resolveBwrap`, `:2393-2405`, a memoized PATH scan with `existsSync`); the macOS arm
asserts a string constant. `buildSandboxPlan` is a pure function that decides purely on
the injected value (`plugin/src/agent/sandboxWrapper.ts:150-153`):

```ts
  if (args.platform === "darwin") {
    if (!args.sandboxExecPath) {
      return { prefix: [], unavailable: true, reason: "sandbox-exec unavailable on macOS." };
    }
```

Because the constant is never empty on darwin, `plan.unavailable` is never `true` there,
so the agy refusal at `:2442-2447` and the `logger.warn` at `:2449-2452` are dead code on
macOS. The spec explicitly enumerates that branch
(`PLUGIN_SCHEMA.md:2210-2219`, §13.6):

> "**Unavailable-sandbox degradation** — when no OS sandbox is available (Linux without
> `bwrap`, **macOS without `sandbox-exec`**, Windows/other): **agy is refused** … but
> **Claude/Codex proceed under their own flag-based containment** … the plugin emits a
> `console.warn` when it drops the OS layer."

Coverage: `grep -rn "wrapWithOsSandbox|sandboxExecPath" plugin/src` shows the sandbox tests
only exercise the pure function with an injected path
(`sandboxWrapper.test.ts:72`, `:104`), and both `llmClient.test.ts:906` and
`llmCliLifecycle.test.ts:58` **stub `wrapWithOsSandbox` out**. Nothing covers the caller's
path resolution.

**Why I downgrade the reasoning while keeping the finding.** Pass A's argued user impact —
the user sees `"antigravity CLI is not installed or not found on PATH"` (`:2000-2003`, which
I confirmed does fire on any `ENOENT`, including a missing `sandbox-exec`) and is sent to
reinstall the wrong binary — requires `/usr/bin/sandbox-exec` to be absent or
non-executable. `sandbox-exec` ships in `/usr/bin` on every macOS release to date; it is
deprecated, not removed. I could find nothing in this repo establishing a configuration
where it is absent, and I did not probe the host. So the *misdiagnosis* is not a defect
users hit today — it is contingent on a future Apple removal or a hardened/MDM image.
What remains, and is not contingent, is that the spec documents a degradation branch the
code makes structurally unreachable on one of the two supported platforms: a §13.6
spec-vs-code divergence, which ground rule 5 makes reportable on its own. Hence: finding
stands, at **P3**, on conformance grounds rather than on Pass A's user-impact grounds.

**Fix direction.** Mirror `resolveBwrap()`: memoized `existsSync` (or
`accessSync(path, X_OK)`) probe of `/usr/bin/sandbox-exec`, passing `""` when absent so the
documented refusal/warn branch becomes live. Roughly ten lines, no spec change needed
(the spec is already correct — the code under-implements it), plus a test that injects a
fake probe and asserts the agy refusal fires on darwin.

---

## 2. Pros & Cons

### What I could NOT verify

- **No runtime reproduction of anything.** This is a read-only static pass: no `wiki`
  command, no `testbed/`, no Obsidian instance, no vitest run. F1's tab-switch interleaving
  is argued from the registered `active-leaf-change` handler plus the resolver's three
  `await` sites — I did not observe the race fire. It is a strong static case (the mutation
  path and the read path are both on `this.activeContext`), but a manual repro should
  precede the fix landing.
- **F2's JSONC premise.** I could not verify from this repo whether the Gemini CLI tolerates
  comments in `~/.gemini/settings.json`, which is what makes the "user's hand-edited file"
  scenario likely rather than merely possible. I rested the finding on the in-repo asymmetry
  and the unconditional non-atomic write instead, both of which are verifiable here.
- **F4's platform premise.** I did not check the host for `/usr/bin/sandbox-exec` (out of
  scope for a read-only repo audit, and one host proves nothing about the fleet). The
  downgrade rests on general macOS knowledge, which is exactly the kind of claim this audit
  says to treat cautiously — hence I kept the finding rather than dropping it.
- **`getDocumentIndex()` lifetime.** I confirmed `getActivePdfDocumentIndex()` returns
  `pdfView?.getDocumentIndex()` (`main.ts:1813-1817`) and that the resolver upserts into
  whatever object it is handed, but I did not read `externalPdfView.ts` to establish exactly
  how long that index object outlives a `setState` document swap. If the view discards the
  index on document change, F1's poisoning is bounded by the tab's lifetime rather than the
  view's — the wrong-answer half of F1 is unaffected either way.
- **`ChatSidebarView.ts` (~4.9k lines)** — I read only the reference-fetch region
  (`1770-1800`) needed for the F1 contrast. No claim about the rest.

### What I judged CLEAN in the course of adjudicating (checked, no finding filed)

- **The local-PDF-tool fetch path is correctly pinned.** `main.ts:1857-1860` passes
  `getActivePdfDocumentId()`, and `fetchActivePdfPage` re-checks the viewer's identity
  *after* the backend await too (`main.ts:1806-1808`: `if (pinnedView.getDocumentId() !==
  pinnedDocumentId) return undefined;`). Pass A and Pass B both said so; I re-read it and
  agree. F1 is specifically about the *other* call site, not about the guard's quality.
- **Sidechat's cross-reference fetcher.** Verified genuinely immune to F1's hazard —
  `ChatSidebarView.ts:1782-1797` closes over `sourcePath` / `sourceStatus?.sourceId` /
  `pdf.fileHash` / `pdf.zoteroAttachmentKey` as locals captured before the resolver runs. It
  is the correct reference implementation for the F1 fix.
- **`syncAgyHeadlessReadPermission` itself.** `LLMClient.ts:65-127` is exemplary: strict
  parse, non-object rejection, `permissions`-shape rejection, `permissions.allow`
  string-array rejection, preservation of unknown keys, temp+rename commit, and a `finally`
  that removes the temp file. It is the pattern F2 should copy — nothing to fix here.
- **The streaming CLI cleanup path.** `LLMClient.ts:1348-1377` fully satisfies §2.1.3's
  cleanup-robustness clause. F3 is a one-sided gap, not a systemic one.
- **`cleanupChatImageDir` null-safety.** `:2312-2313` early-returns on a falsy dir, so the
  text-only path is not silently doing anything wrong — which is precisely what keeps F3 at
  P3 rather than P2.
- **`buildSandboxPlan`'s Linux arm.** `sandboxWrapper.ts:158-165` refuses with an actionable
  install hint when `bwrapPath` is empty, and `resolveBwrap` (`LLMClient.ts:2393-2405`) does
  an in-process PATH scan with no subprocess. The behavior F4 asks for on macOS already
  exists on Linux — the fix is a copy, not a design.
- **`quickQueryPopover`'s abort wiring, re-checked while reading `runQuery`.** The controller
  is created per query (`:468-469`) and cleared in a `finally` only if it is still the
  current one (`:553-557`), so a superseded request cannot null out its successor's
  controller. No finding. (This is orthogonal to Pass B's PL-1, which is about
  `LLMClient.complete`'s `try { return promise } finally {}` and is out of scope here.)

### Cost / risk of the proposed fixes

- **F1** is the highest value in this pass and remains the highest-severity unresolved item
  in the audit. The minimal fix is two lines in `quickQueryPopover.ts`; making
  `expectedDocumentId` required is a further two-call-site change that permanently closes the
  class. The index-poisoning half may warrant a small resolver change (skip `upsertPage`
  when the fetch was guard-rejected) — decide that during planning, since it touches
  `pdfReferenceContext.ts`, which is heavily tested and shared with sidechat. **Do not**
  bundle the resolver change with the call-site change if review budget is tight; the
  call-site fix alone removes the wrong-answer path.
- **F2** needs a shared helper plus a §13.6 spec sentence. Code-only would leave the same
  doc gap that permitted the divergence.
- **F3** is a scope move of two statements into an existing `try`, plus generalizing one
  test away from an indentation-sensitive string match. Near-zero risk.
- **F4** is a ten-line memoized probe mirroring `resolveBwrap`. Zero risk, but also zero
  present-day user impact — schedule it only alongside other `LLMClient.ts` CLI-region work.
- **Batching.** F2, F3, F4 all live in the same ~600-line CLI region of `LLMClient.ts`
  (`:2150-2550`), together with Pass B's PL-1 and PL-3. One change, one review of that block.
  F1 is in a different file and a different risk class — it should be its own reviewed change
  and should land first.
