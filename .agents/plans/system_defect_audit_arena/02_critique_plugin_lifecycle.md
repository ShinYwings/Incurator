# Critique on `01_proposal_plugin_lifecycle.md` (Pass B, PL-1..PL-4)
Date: 2026-08-04 | Agent Persona: Red-Team Critic (Plugin Lifecycle)

Scope: the four findings handed to me as `plugin_lifecycle-1..4` (= Pass B's
PL-1..PL-4). Pass A's F1–F4 were not in my remit and are not adjudicated here.
Read-only pass; this file is my only write. Every quotation below was re-read
from the working tree at `/Users/shin/shinywings/Incurator` (branch
`chore/system-defect-audit-arena`), not copied from the proposal. I attacked each
finding on five axes: (a) is the quoted code current, (b) is the failure path
reachable from a live call site, (c) is it already pinned green by a test,
(d) does the cited spec really promise what is claimed, (e) is the severity
inflated.

**Verdict summary**

| id | inspector | my verdict | final severity |
|---|---|---|---|
| plugin_lifecycle-1 | P2 | **confirmed** | P2 |
| plugin_lifecycle-2 | P2 | **downgraded** | P3 |
| plugin_lifecycle-3 | P2 | **confirmed** | P2 |
| plugin_lifecycle-4 | P3 | **confirmed** | P3 |

Three of the four write-ups carry a secondary claim or a fix direction that is
wrong, unnecessary, or self-defeating. Those corrections matter more than the
verdicts, because they are what a coder would implement verbatim.

---

## 1. Vulnerabilities & Flaws

### plugin_lifecycle-1 — CONFIRMED [P2]. Every attack failed; the scoping is correct for a reason the proposal never states.

**Attack (a) "the quoted code is stale or misread."** Failed. Verbatim, current:

- `LLMClient.ts:1234` opens the `try`; `:1249-1251` is
  `if (this.shouldUseCli(messages)) { return this.completeViaCli(messages, toolPolicy, model, controller.signal); }`;
  `:1318` is the identical unawaited statement in the 401/403 retry inside the
  same `try`; `:1325-1327` is `} finally { this.endRequest(controller); }`.
- `beginRequest` (`:704-722`) and `endRequest` (`:724-732`) match the proposal
  exactly, including `this.requestAbortCleanup.get(controller)?.()` as
  `endRequest`'s **first** statement — i.e. the owner-signal
  `removeEventListener` closure installed at `:712-714`.

**Attack (b) "the try/finally semantics are folklore."** Failed. I re-ran the
experiment independently rather than trusting the inspector's script:
`node -e 'const later=ms=>new Promise(r=>setTimeout(()=>{console.log("inner-settled");r("v")},ms)); async function f(){try{return later(50)}finally{console.log("finally-ran")}} f().then(v=>console.log("outer-resolved",v));'`
→ `finally-ran` precedes `inner-settled` precedes `outer-resolved`. A `return`
inside an async `try` produces the return completion immediately; the implicit
await that adopts the inner promise happens *after* the `finally`.

**Attack (c) "something else keeps the owner→controller bridge alive."** Failed.
`beginRequest` is the sole bridge, via a `{ once: true }` listener whose only
removal handle is the `requestAbortCleanup` entry `endRequest` invokes. After
`endRequest`, `ownerSignal.abort()` is inert w.r.t. `controller.signal`, and
`completeViaCli` binds that signal straight into
`execFileAsync(command, args, { cwd, env, timeout: CLI_TIMEOUT_MS, …, signal })`
(`:1964-1972`). `CLI_TIMEOUT_MS = 5 * 60 * 1000` (`:526`), so an uncancellable
child can sit for five minutes.

**Attack (d) "streaming has the same shape, so either it's P1 or the analysis is
wrong."** Failed, and this is a point *for* the inspector. I grepped every
`return this.` in `LLMClient.ts`: `streamChat` reaches the CLI as
`const text = await this.streamChatViaCli(` at `:1024` and `:1098` — genuinely
awaited. Only `:1250` and `:1318` are defective. The proposal does not
over-claim.

**Attack (e) "already pinned green."** Failed. `llmClient.test.ts:257-277`
("preserves non-streaming Ollama AbortError") really is the only
`complete()`+signal abort test and it hardcodes `provider: "ollama"`, which
`shouldUseCli` (`:1330-1333`) short-circuits before `completeViaCli`.
`grep -rn "endRequest" plugin/src --include=*.test.ts` → nothing.

**Attack (f) "not reachable from a live UI path."** Half-landed, and this is my
one substantive correction. `grep -rn "llmClient\.complete("` over `plugin/`
yields exactly **one** non-test caller — `quickQueryPopover.ts:535` — and it
sits in the `else` of `if (this.plugin.settings.streamingEnabled)` at `:509`.
The only other `complete()` caller is `LLMClient.editText` itself (`:2653`),
gated at `:2650` by `if (onChunk && this.settings.streamingEnabled)`, whose
callers `inlinePrompt.ts:181,222` split on the same flag (`:175`).
`streamingEnabled` defaults to `true` (`types.ts:182`; toggle `settings.ts:382-385`).
**So today every reachable `complete()` path requires the user to have turned
streaming off.** That does not refute the finding — it explains why P2 and not
P1 is the right band (breakage *with* a workaround), a justification the
proposal never gives. State it in the master plan so the batch does not oversell
the impact, and state the inverse: this becomes a default-path cancellation hole
the moment any surface adds a non-streaming `complete()` caller.

**Spec re-read.** §1.4 L258-259 does say "Every public provider request owns a
locally captured `AbortController` **for its complete lifetime**"; L266-267 does
say "When a newer request **finishes**, an older still-active request becomes
foreground again". §13.4's "An in-flight quick query is aborted when its popover
is dismissed" is at **L2095**, not L2084 as the finding's `spec_ref` claims — a
citation nit only; the sentence exists and says what is claimed. The dismissal
path is real (`quickQueryPopover.ts:632-636`).

**What I am striking from the write-up.** Failure scenario B (foreground
mis-cancellation via `editText`) is the weak half: it needs a sidebar
`streamChat` and an inline edit concurrently alive *while streaming is
disabled*, and the inspector concedes they never instrumented the foreground
pointer. Scenario A alone is a clean §1.4 + §13.4 violation with a one-caller
repro. Demote B to a corollary so no reviewer chases it.

---

### plugin_lifecycle-2 — DOWNGRADED to P3. The mechanism is real; the user-visible symptom and the spec hook are not.

**What survived my attack.** The asymmetry is real and current:
`quickQueryPopover.ts:144-146` (`activeWin` derived from `activeDoc`), `:268-282`
(attach adds `scroll` capture + `resize` on `this.activeWin`), `:284-289`
(detach removes from `this.activeWin` resolved *at detach time*, then nulls
`repositionHandler`), `:191-194` (`this.activeDoc = doc;` … `this.showButton(rect)`),
`:233` (`showButton` opens with `this.removeButton()`), `:291-295`
(`removeButton` → `detachRepositionListeners`). Multi-window is genuinely wired:
`main.ts:300-307` registers `registerQuickQueryDom` on `document` **and** on
every `window-open`; `main.ts:215-221` routes each doc's `mouseup` into
`handleSelectionChange(doc)`. The sibling drag teardown does store its window
(`:453-456`, `dragState.win`), so this is a real missed application of an
in-repo pattern. Nothing pins it: `quickQueryPopover.test.ts:170-172` asserts the
`removeButton`-before-`activeDoc` ordering **only** for `openForCurrentSelection`,
and the reposition test (`:211-219`) asserts substrings of the handler body.
The defect is real and the primary fix direction is right.

**Attack that landed #1 — "visibly jitters the 'Ask AI' button in another
window" is false.** I traced the leaked closure (`handler`, `:270-278`). When it
fires on the *old* window it reads `this.buttonEl` — now the **new** window's
button — and `this.anchorRange` — the **new** window's range — then calls
`applyFloatingPosition(this.buttonEl, rect, BUTTON_SIZE)`, which resolves
`const win = this.activeWin` (`:256-262`) to the **new** window. It therefore
recomputes the button's *correct* position using the *correct* window's
`innerWidth/innerHeight`. There is no mispositioning and no jitter. Once that
button is torn down, `if (!this.buttonEl)` sends the leaked handler into
`detachRepositionListeners()`, which early-returns on the null
`repositionHandler` — so the leaked listener degenerates permanently into an
early-returning no-op. The headline symptom does not exist.

**Attack that landed #2 — the `spec_ref` is invented.** I read §1.4 L256-281 in
full. Its bullets are: request-local `AbortController` lifetime; the foreground
pointer rule; settle-before-transport; CLI signal binding + non-streaming env
parity; the **External PDF view** render-token/timer/observer/cache ordering;
MCP stdin/`args` normalization. There is **no** general "surface teardown must
release its own timers/observers/listeners" clause — the finding manufactures it
by generalizing the PDF-view bullet. §13.4 L2093+ ("The popover is a temporary
session-local surface. Closing it … discards that popover's exchange") governs
the *popover exchange*, not the manager instance's trigger-button window
listeners. `grep -n "listener" docs/specs/plugin_schema/PLUGIN_SCHEMA.md`
returns only L462 (the `fs.watch` error listener). **No contract is violated**,
which is exactly what the rubric requires for P2.

**What is actually left.** N leaked capture-phase no-op listeners per
popout↔main selection alternation, surviving `unload()` — they are raw
`addEventListener` calls on a `Window`, not `registerDomEvent`, so Obsidian's
auto-teardown never reaches them — each retaining the `QuickQueryPopover`, its
`capturedSelection`, and a `Range` over a detached document. That is a
memory/hygiene leak with no user-visible breakage and no spec sentence violated.
Under the briefing rubric that is **P3 (hygiene)**, not P2 ("contract
violation, silent degradation, or edge-case breakage with workaround").

This is a downgrade, not a dismissal. The fix is ~4 lines with an in-repo
template and should still ship; I am refusing only the P2 label, the jitter
narrative, and the fabricated spec citation.

---

### plugin_lifecycle-3 — CONFIRMED [P2], after my best refutation failed. Two sub-claims must be deleted.

**Re-verification.** `LLMClient.ts:2295-2299` `cliCacheBase()` is verbatim and
keys **only** on `incuratorRepoPath`, despite `vaultRoot` being a constructor
parameter of the same class (`main.ts:194-201` passes it). `:2325-2331`
`sweepStaleChatImages()` is a single
`rmSync(join(this.cliCacheBase(), "chat_images"), { recursive: true, force: true })`
at the **parent** level with no per-subdir age or liveness check; constructor
`:627-628` calls it unconditionally. Writes go to
`join(this.getCliCwd(), "chat_images", …)` (`:2579-2580`), and `getCliCwd()`
(`:2335-2336`) is `cliCacheBase()` realpath-resolved — the same directory, so
the sweep does target the live tree. The vault-scoped siblings are real:
`main.ts:951` and `:984` use `vaultMachineCacheDir(repoPath, this.vaultRoot)`
(helper at `src/utils/machineCache.ts:13`). `chat_images` is the only
device-local plugin cache that is not vault-scoped.

**My best shot, and why it missed.** If `LLMClient` were constructed before
settings load, `incuratorRepoPath` would be `""`, `cliCacheBase()` would throw,
and the sweep would be a permanent caught no-op — refuting the finding outright.
It is not: `main.ts:176` `await this.loadSettings()` and `main.ts:191`
`this.settings.incuratorRepoPath = this.resolveRepoPath() || "";` both precede
`new LLMClient(` at `:194`. The sweep fires with a resolved path. I also bounded
the blast radius: `new LLMClient(` appears exactly once outside tests, so the
sweep is once-per-plugin-load — which confines the race to *cross-process* (two
vaults) rather than intra-vault, but does not eliminate it.

**Delete sub-claim 1 — the "Reload app without saving" race.** The proposal
adds "The same `rmSync` also races a second window of a single vault after
'Reload app without saving'." A reload tears down the renderer that owns the
in-flight `execFileAsync` promise, so no live consumer remains to be degraded.
This sentence only hands a reviewer an easy rebuttal. The two-vaults-one-repo
case is the entire finding.

**Delete sub-claim 2 — "silently degraded … with no error surfaced."** When the
run dir vanishes, claude's re-enabled `Read` of the absolute path fails and the
model will frequently *say* it could not read the file; for `agy` a missing
`--add-dir` target may fail at launch. The honest characterization is "degraded
and confusing", not "silent". Do not rest the severity on that word.

**Why P2 survives both deletions.** Briefing rule 5 makes spec-vs-code
divergence a finding in its own right, and there is a literal one:
PLUGIN_SCHEMA L823 says "**stale** `chat_images/*` dirs are swept on plugin
load." The implementation sweeps *all* dirs, live ones included, and the spec
never defines staleness — both are wrong until reconciled. Combined with a real
(if narrow) cross-vault destruction window against a 5-minute-timeout
subprocess, this lands squarely in the rubric's P2 band ("contract violation …
or edge-case breakage with workaround"). I also endorse the proposal's warning
that this is not a one-liner: the path feeds `sandboxWriteRoots()`/`getCliCwd()`
into `wrapWithOsSandbox` (`:2426-2434`) and the §2.1.3 `--add-dir` confinement
rule.

---

### plugin_lifecycle-4 — CONFIRMED [P3]. The primary claim is exact; the secondary claim is misdiagnosed and its fix would be a no-op.

**Primary claim re-verified.** `syncScheduler.ts` is 68 lines; I read all of it.
`dispose()` (`:64-69`) clears only `timer`. `pending` is never cleared and no
disposed flag exists. `fire()` (`:47-62`) ends with
`finally { this.running = false; if (this.pending) { this.pending = false; void this.fire(); } }`
with no disposal gate; `schedule()` and `runNow()` are equally ungated.
Teardown is `main.ts:2384-2387`
`this.register(() => { this.syncWatcher?.close(); this.syncScheduler?.dispose(); });`.
Mid-run triggers exist: the `fs.watch` callback (`main.ts:2413-2415`) and the
60 s `registerInterval` fallback (`main.ts:2378-2382`). Post-unload effects are
real: `runAutoSyncPass` (`main.ts:2424-2439`) does
`this.syncStatusBar?.setText("⟳ Sync")`, then
`await this.incuratorClient.dbAutosync()`, then possibly `new Notice(...)`.
`grep -rn "dispose" plugin/src --include=*.test.ts` → nothing. No attack landed.

**Attack that landed — the secondary "ordering gap" is wrong as stated.** The
proposal says the watcher leaks "*because* `startSyncWatcher()` is invoked
inside `onLayoutReady` (`main.ts:2369-2374`) **after the teardown closure was
registered** at `:2384`". Registration order is irrelevant: the teardown closure
reads `this.syncWatcher` **lazily at call time**, so any watcher created before
unload is always closed. Consequently the proposal's own fix option — "*or have
teardown re-read `this.syncWatcher` post-layout-ready*" — describes what the
code already does and would change nothing.

The real gap in that region is different, and the master plan should carry this
version instead: the `onLayoutReady` callback is registered on `app.workspace`,
**not** through the plugin's `registerEvent`/`register` disposal chain. If the
plugin is unloaded before layout-ready, that callback still fires afterwards and
runs *both* `void this.syncScheduler?.runNow()` (a full sync pass after unload —
the same bug class as the primary claim, reached by a different door) *and*
`this.startSyncWatcher()` (a watcher nothing will ever close). "Move the
teardown registration to where the watcher is created" does not fix it either: a
`this.register` call made after `onunload` is never invoked. It needs an
explicit unloaded guard read *inside* the callback.

**Severity.** P3 is right and not inflated: one extra idempotent
`wiki db autosync` subprocess, one `setText` on a detached element, possibly one
stray `Notice`. No data loss, no wrong knowledge served.

---

## 2. Suggested Alternatives

### 2.1 plugin_lifecycle-1 — take the fix, then close the *class*, and test behaviour not source text

- `return await this.completeViaCli(...)` at `:1250` and `:1318` is correct and
  minimal. Ship it.
- **Close the defect class, not the instance.** The bug is "`return <promise>`
  inside a `try/finally` that owns lifecycle state". Enable
  `@typescript-eslint/return-await` with `"in-try-catch"` in the plugin's ESLint
  config; it flags exactly this and protects `streamChat`'s currently-correct
  `await`s (`:1024`, `:1098`) against future edits. Cheaper and broader than any
  single test.
- **Make the regression test behavioural.** The existing CLI tests lean on
  source-substring assertions (`llmClient.test.ts:964-1012` asserts literal
  strings including indentation) — which is precisely why this bug was invisible
  to CI. Instead: stub `execFileAsync` to never resolve, set
  `provider: "claude"`, pass an owner `AbortController`, call `owner.abort()`,
  and assert the `signal` handed to `execFileAsync` reports `aborted === true`.
  That asserts the contract, not the formatting.
- Record the `streamingEnabled: false` reachability caveat (my §1 attack (f)) in
  the plan entry.

### 2.2 plugin_lifecycle-2 — prefer the structural fix over the field-sync fix

- The proposed `this.repositionWin` field (mirroring `dragState.win`) works, but
  the **strictly better fix** is to route these two listeners through the
  plugin's `registerDomEvent(win, …)` — the same mechanism
  `registerQuickQueryDom` already uses at `main.ts:216`. The manager is
  plugin-scoped, so this is available to it, and it makes the only genuinely bad
  consequence (survival past `unload()`) *structurally* impossible instead of
  contingent on a field staying in sync with a getter. Keep the
  `handleSelectionChange` reorder for consistency with `openForCurrentSelection`.
- **Replace the proposed test.** Extending `quickQueryPopover.test.ts:170-172`
  means extending an `indexOf`-on-source-text assertion that would pass on any
  refactor that moves the statements into helpers. Use two `jsdom` documents (or
  a pair of stub `Window`s recording `addEventListener`/`removeEventListener`),
  run `handleSelectionChange(docA)` then `handleSelectionChange(docB)`, and
  assert `winA.removeEventListener` was called with the **same handler identity**
  `winA.addEventListener` received. That is the invariant.
- **Fix the write-up before it reaches the master plan.** Remove the "visibly
  jitters the button in another window" claim (traced false in §1) and drop the
  §1.4/§13.4 `spec_ref` (neither section contains the cited sentence). If the
  batch wants a spec hook, the honest move is to *add* one to §1.4 — e.g. "a
  surface that attaches listeners to a `Window` MUST detach them from the window
  captured at attach time, and MUST do so on `unload`" — and label it as new
  contract, not as a pre-existing violation.

### 2.3 plugin_lifecycle-3 — choose the age-guard; do NOT relocate the directory in this batch

The proposal offers two options and declines to choose. Choose the guard:

- Relocating to `vaultMachineCacheDir(repoPath, vaultRoot)/chat_images` moves a
  path consumed by `getCliCwd()`, `sandboxWriteRoots()`, `wrapWithOsSandbox`
  (`:2426-2434`), the claude `--add-dir` confinement rule, and §2.1.3's explicit
  "This is the **only** allowed temp/cache root for plugin-created chat images"
  (L797-799). That is a sandbox-surface change requiring `sandboxWrapper.test.ts`
  extension plus a rewrite of the §2.1.3 root rule — disproportionate to the
  defect.
- The guard is contained and testable: `readdirSync(chat_images)`,
  `statSync(entry).mtimeMs`, skip anything younger than `CLI_TIMEOUT_MS` (reuse
  the existing `:526` constant so the two can never drift), `rmSync` the rest.
  It fixes the cross-vault race and makes the code match the word "stale" the
  spec already uses.
- **Amend §2.1.3 in the same commit** with the missing definition: "A run dir is
  *stale* when its mtime is older than the CLI request timeout; the load-time
  sweep MUST skip younger dirs, because a concurrently open vault sharing the
  same `incuratorRepoPath` may still own them." Without this the divergence is
  only half-closed and the next agent restores the parent-level `rmSync`.
- Delete the two sub-claims identified in §1 before the entry is carried
  forward.

### 2.4 plugin_lifecycle-4 — one guard in the scheduler, one guard in the callback

- `SyncScheduler`: add `private disposed = false;` set in `dispose()`, clear
  `pending` there, and early-return from `schedule()`, `runNow()`, and `fire()`
  when disposed. Test: start a run that never resolves, call `schedule()` to arm
  `pending`, call `dispose()`, resolve the run, assert the injected `run` was
  invoked exactly once.
- `main.ts`: guard the `onLayoutReady` callback itself, because it is outside
  the plugin's disposal chain. Install `private unloaded = false` set by a
  `this.register(() => { this.unloaded = true; })` registered *first*, then
  `if (this.unloaded) return;` as the first statement of the `onLayoutReady`
  callback — this covers both the post-unload `runNow()` and the orphaned
  watcher. **Do not** implement the proposal's "move the teardown registration"
  or "re-read `this.syncWatcher` post-layout-ready" suggestions: the first is
  unreachable after `onunload`, the second is already the code's behaviour.

### 2.5 Batching note for the synthesizer

`plugin_lifecycle-1` and `plugin_lifecycle-3` both live in the CLI region of
`LLMClient.ts` (`:1229-1330` and `:2295-2340`) — one reviewed change.
`plugin_lifecycle-2` (P3) and `plugin_lifecycle-4` (P3) are both listener/
teardown hygiene — a second, lower-priority change. Only `plugin_lifecycle-3`
carries a spec amendment against an existing sentence (§2.1.3 staleness);
`plugin_lifecycle-2`'s spec hook must be *added* if wanted, never cited as
pre-existing. None of the four implies a schema change, a migration, or a
`MAJOR.MINOR` spec-title bump; per the CLAUDE.md 0.x criteria a batch of only
these four would be a **patch** bump (`### Fixed` only).
