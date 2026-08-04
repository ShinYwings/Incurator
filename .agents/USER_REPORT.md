# User Report

This document is a **plain Inbox (backlog) log** that records bugs reported by the user, required features, ideas, etc., in chronological order without any filtering.

Agents must check this document and triage the received items into the `To-Do (Queuing)` area or `Icebox` area of `.agents/ROADMAP.md`. Once the triage is complete, **immediately delete** the item from this document.

## 📝 User Inbox

### 2026-08-04 — [perf] Quick Query popover answers and Convert-to-LaTeX are too slow

User report: both the popover's answer latency and the right-click
**Convert to LaTeX** action need speed work.

NOT yet diagnosed — per the stability-overhaul rule that performance work is
benchmark-first, this must start with measurement, not with a guess at the
cause. Required before any change:

1. Measure where the wall-clock actually goes on each path, separating
   (a) context assembly in the plugin, (b) backend round-trip, and
   (c) provider inference time. Provider time is the one Incurator cannot fix,
   so it must be isolated before anything is optimized.
2. Only then propose changes, and accept them only with a measured speedup and
   no answer-quality regression.

**RESOLVED / CLOSED 2026-08-04 10:55 — measured, and the bottleneck is not ours.**

Full measurement on this machine:

| Path | Wall clock |
|---|---|
| Ollama local model, warm | 0.26–0.32 s |
| Incurator backend round-trip | 0.20 s |
| `agy` CLI binary startup (`--version`) | 0.29 s |
| **`agy --print` full call, one-word answer** | **8.2–12.2 s** |

`gemini-3.1-pro` at effort `low` took 12.17 s and at effort `high` took 8.52 s;
`gemini-3.6-flash` at `low` took 8.18 s. Latency is therefore **independent of
model and effort** — for a two-token reply it cannot be inference. Since the CLI
binary itself starts in 0.29 s, it is not process startup either. It is the
Antigravity **service** handshake, which Incurator cannot shorten.

Consequences, and what was and was NOT changed:

- **PDF reference-fetch optimization: rejected.** Even the worst case (~8–10
  sequential round-trips ≈ 2 s) is a minority of a ~13 s action, and the
  existing tests at `pdfReferenceContext.test.ts:80` prove the common case
  already issues exactly ONE fetch — batching would have made the *common* path
  do 4× the backend work to speed up only the rare path. Correctness risk with
  no meaningful payoff.
- **Neither slow path makes a redundant provider call.** Verified:
  `shouldInjectLocalTools` returns false for CLI providers, so the popover's
  v0.41.0 `local-only` policy adds no tool round-trip for this user; and with
  `latex_extract_model` empty, Convert-to-LaTeX resolves straight to
  `vision_model` — one invocation.
- **Shipped instead: perceived latency.** The popover now ticks elapsed seconds
  (PLUGIN_SCHEMA §1.4.3). A frozen "Thinking…" for 8–12 s is indistinguishable
  from a hang — that exact ambiguity made a real crash read as slowness earlier
  in this session.
- **Real remaining lever is provider choice, not code.** A warm local Ollama
  round-trip is ~0.3 s against `agy`'s 8–12 s. If these surfaces need to feel
  fast, point them at a local or direct-API provider; no amount of Incurator
  optimization closes a 30× gap.

**Original first measurements (backend side only):**

- One backend round-trip costs **~0.20 s** wall-clock, warm
  (`wiki plugin version` 0.30/0.20/0.20 s; `wiki plugin pdf context` for a real
  vault PDF 0.21/0.20 s). That floor is Python process startup + imports, paid
  fresh on EVERY call — the plugin spawns a new `wiki` process per fetch.
- The popover's pre-request reference resolution
  (`plugin/src/context/pdfReferenceContext.ts`) issues **several SEQUENTIAL
  rounds** of those calls before the provider is ever invoked:
  `DIRECT_FETCH_ROUND_LIMIT = 3` rounds, then an adjacent-equation probe over
  `ADJACENT_EQUATION_PAGE_OFFSETS = [1, -1, 2, -2]` that awaits **one page at a
  time**, plus outline batches of 6. Within a round `fetchPages` does
  parallelize via `Promise.all`, so the cost is per-ROUND, not per-page.
- Worst case is therefore roughly 8–10 sequential round-trips ≈ **1.6–2.0 s of
  pure subprocess overhead** before the model is asked anything.

**Highest-leverage candidate fix (contract-preserving):** the adjacent-equation
probe fetches pages `+1, -1, +2, -2` in four separate awaited calls, but the CLI
already accepts `--page-num N --radius R --max-pages M` and could return that
whole neighborhood in ONE call. The v0.39.2 contract requires *next-first
ordering and stopping at the first exact label match* — that governs which match
is ACCEPTED, not how many pages are fetched, so fetching the neighborhood once
and then evaluating it in the documented order preserves the fail-closed
semantics while collapsing 4 round-trips into 1.

**Still unmeasured — do this before optimizing:** the provider's share of
wall-clock. If inference dominates, the ~2 s of overhead above is a minority of
the total and the ordering of work should change accordingly. This needs
instrumentation in the running plugin (the backend timings above cannot show
it). Convert-to-LaTeX was NOT timed because doing so spends provider quota;
measure it deliberately.

Known structural candidates to CONFIRM OR REFUTE by measurement (each is a
hypothesis, not a finding):
- The popover resolves PDF cross-references before the request
  (`resolveSelectionReferencesBlockAsync`) and, since v0.41.0, runs with
  `toolPolicy: "local-only"` so a tool round-trip can add a whole extra
  provider turn.
- Convert-to-LaTeX resolves through `latex_extract_model → vision_model →
  main-if-vision`; when the resolved slot is the same CLI the chat already
  uses, the work may be one provider invocation more than necessary.
- CLI-backed providers pay process startup per call; check whether either path
  makes more than one such call.



### 2026-08-04 — [HOTFIX] Post-v0.41.0: popover stuck "Thinking", sidechat send dead, purple pins gone

User report: right after updating to v0.41.0, the Quick Query popover spins on
"Thinking" forever, sidechat Send does nothing, and the purple context pins are
not visible.

**RESOLVED in v0.41.1 (2026-08-04 10:05).** Console errors supplied by the user
identified the true cause; both are fixed on `hotfix/v0.41.1-deferred-view-crash`.

1. `Uncaught TypeError: t.getRuntimePath is not a function` — **the single cause
   of all three symptoms.** Obsidian 1.7.2+ restores tabs as *deferred* views:
   `leaf.view` reports the real `getViewType()` but is a placeholder without the
   concrete class's methods. `main.ts` narrowed external-PDF leaves on that
   string alone (6 sites) and then called `getRuntimePath()`. The throw landed in
   `getLeafFile()`, which feeds BOTH `updateActiveContext()` (→ `refreshActiveContext`,
   used by sidechat `handleSend` and the popover) AND the open-tab inventory
   (→ purple pins). One restored PDF tab therefore killed all three at once, and
   **restarting Obsidian made it more likely, not less** — a restart is what
   creates deferred tabs. This also explains why the dashboard still showed
   0.41.0 correctly: it reads a different field and never touches this path.
   Fix: capability-checked `asLoadedExternalPdfView()` guard; a deferred or stale
   leaf degrades to persisted state and is never force-loaded.
2. `pdf.min.mjs: Cannot use the same canvas during multiple render() operations`
   — page canvases are reused across zoom/scroll/document swap while the PDF.js
   render task was fire-and-forget. Fix: per-page render tasks are retained,
   cancelled, and awaited before the next render claims the canvas, plus a
   cancel-all on swap/reload/close. The render token was never sufficient — it
   stops work scheduled after the bump but cannot release a canvas already
   owned by PDF.js.

Contracts added: PLUGIN_SCHEMA §1.4.1 (leaf narrowing must not trust the
view-type string) and §1.4.2 (page canvases are exclusive to one render task),
plus troubleshooting sections in PLUGIN_GUIDE.md and PLUGIN_GUIDE_KR.md.

**Superseded diagnosis (2026-08-04 09:55).** The first diagnosis below (stale
runtime bundle / "reload Obsidian") is **WRONG and retracted** — the user had
already restarted the app, and a restart in fact *triggers* the real bug. Kept
only as the record of a refuted hypothesis. The `wiki` 0.4.3 finding that
follows is real and independent, but was NOT the cause of these three symptoms.

**CONFIRMED ROOT CAUSE — the plugin calls the wrong `wiki` binary.**

`data.json` has `incuratorBackendCommand: "wiki"` (a bare name), so it resolves
against the PATH of the Obsidian GUI process, not the user's shell. On this
machine that resolves to `/Users/shin/anaconda3/bin/wiki`, an OLD editable
install whose package metadata is pinned at **0.4.3**. Evidence:

```
/Users/shin/anaconda3/bin/wiki version         → incurator 0.4.3
/Users/shin/shinywings/Incurator/.venv/bin/wiki version → incurator 0.41.0
```

That is the `0.4.3` the user sees. Because the anaconda install is *editable*
and points at `/Users/shin/shinywings/Incurator/backend/src/curator`, it still
executes CURRENT repo code — the `wiki plugin --help` surfaces are byte-identical
and `wiki plugin source status` against the real vault returns correct data
(35 sources). So only the reported VERSION is stale, not the behavior.

**CORRECTION (2026-08-04 10:30) — the plugin was NOT calling the wrong binary.**
Verified by reading the resolution chain rather than inferring it:
`runBackendCommand` spawns only what `resolveBackendCommand()` returns;
that function deliberately refuses the bare name (`return command && command
!== "wiki" ? command : null`), `resolveWikiBinary()` checks only
`<repo>/.venv/bin/wiki` and never searches PATH, and this machine's
`devices.json` holds no cached launcher — so the repo hint resolves to
`/Users/shin/shinywings/Incurator/.venv/bin/wiki`, which reports 0.41.0. That
matches the user's own observation that the dashboard showed 0.41.0. The
`0.4.3` was therefore TERMINAL-ONLY, produced by the broken shell alias. The
earlier claim that the plugin used the anaconda install was an over-reach and
is retracted; item 4 below was already implemented and is now pinned by
regression tests instead of "fixed".

**[P1] Genuine Incurator defect this exposes — inconsistent version payload.**
`wiki plugin version` from that install returns a self-contradictory object:

```json
{"version": "0.4.3", "build": {"backend_version": "0.41.0", ...}}
```

Top-level `version` comes from installed package metadata
(`importlib.metadata`), while `build.backend_version` comes from the packaged
`build_manifest.json`. They disagree for any editable install whose metadata
was written by an older `pip install -e`. `IncuratorClient.checkBackendVersion`
(`plugin/src/agent/incuratorClient.ts:120-141`) compares the METADATA-derived
`version` against the plugin's bundled manifest, so `needsUpdate` is stuck
`true` forever and the sidechat renders a permanent
"Expected 0.41.0, got 0.4.3 — Run Setup" banner
(`ChatSidebarView.ts:2726`) that re-running setup can never clear.
SYSTEM_BEHAVIOR §11.2 makes `build.*` the authoritative build identity, so the
comparison is reading the wrong field. Fix: compare `build.backend_version`
when present, falling back to `version` only when the manifest is absent.

**Why the wrong binary wins — two independent paths, both verified:**

- The Obsidian plugin spawns the bare name `wiki`, resolved against the GUI
  process PATH (shell aliases do not apply to spawned processes), which finds
  the anaconda install.
- The user's `~/.zshrc:122` alias is
  `alias wiki='VIRTUAL_ENV=/home/shin/shinywings/Incurator/.venv uv run wiki'`.
  `/home/shin` **does not exist on macOS** (`$HOME` is `/Users/shin`;
  `ls /home/shin` → No such file). With a non-existent `VIRTUAL_ENV`, `uv run`
  only lands on the repo `.venv` when the cwd is inside the repo. Measured:
  from the repo → `incurator 0.41.0`; from `/tmp` → **`incurator 0.4.3`**. The
  plugin runs with the vault as cwd, so it gets the wrong one either way.

**[P2] Installer gap — Incurator never provisions the `wiki` entry point.**
Confirmed by search: no file in the repo writes to `.zshrc`/`.bashrc`/any shell
rc, and `git log -S"Added by Incurator"` / `-S"alias wiki"` return NOTHING —
`setup.sh` has never created that alias in any tracked revision (it only sets
`VIRTUAL_ENV="$ROOT_DIR/.venv"` internally, correctly derived, at `setup.sh:7`).
So the `# Added by Incurator` comment is misleading provenance: the alias was
hand-rolled or carried over from the user's Linux machine (hence the
`/home/shin` path). Because setup.sh leaves entry-point provisioning to the
user, a wrong/foreign `wiki` on PATH is an unguarded failure mode. Fix
direction: have `setup.sh` print (or optionally install) a correct
absolute-path launcher, and have the plugin prefer the backend-reported
`repo_path`'s `.venv/bin/wiki` over a bare PATH lookup.

**WHY IT LOOKED FINE FOR ~37 RELEASES (the important part).**
The anaconda install is an **editable** install:
`/Users/shin/anaconda3/lib/python3.10/site-packages/_editable_impl_incurator.pth`
contains exactly one line — `/Users/shin/shinywings/Incurator/backend/src`. So
`import curator` has always loaded the **live repo source**, and anaconda runs
the same Python 3.10.9 as `.venv` with the required deps present. The code that
executed was therefore always the current checkout; only
`importlib.metadata.version("incurator")` stayed frozen at the value written when
`pip install -e` was first run at v0.4.3.

The systemic lesson: an editable install **decouples "which code runs" from
"which version is reported"**, so every behavioral test passed while the identity
label was a lie. The one mechanism that could have caught it — the plugin's
version check — did fire, but rendered it as an unactionable "Run Setup" banner
instead of "you are running a different install at <path>". That is why the
defect survived silently.

**[P2] Latent hazard found alongside it:** a stale PHYSICAL package tree sits at
`/Users/shin/anaconda3/lib/python3.10/site-packages/curator/` (dated 2026-06-08,
no `__init__.py`; contains `data/models.json`, `data/build_manifest.json`, and
`workspace/templates/**`). It is inert today because the editable finder wins,
but if that `.pth` is ever removed the imports would silently fall back to
June-8 workspace templates and model catalogue rather than failing loudly. The
same pair is duplicated under `.../python3.1/site-packages/`.

**[P2 → now a confirmed user requirement] `setup.sh` MUST provision the `wiki`
entry point.** User instruction 2026-08-04: setup.sh should create the shell
alias. Requirements for that work: derive the path from `$ROOT_DIR` (never
hardcode, never emit a `/home/...` path on macOS); be idempotent (repair an
existing `# Added by Incurator` block instead of appending a duplicate); support
zsh and bash; and DETECT a conflicting `wiki` earlier on PATH (exactly the
anaconda case) and warn loudly rather than silently losing to it.

**Note (not a defect):** `.venv` lacks the `mcp` module while anaconda has it.
That is by design — `setup.sh:56` installs `-e backend` without extras, and MCP
is a dev/external-agent extra. Dependency availability does NOT explain the UI
symptoms; the anaconda backend answers plugin commands correctly.

**Immediate user remedy:** set the plugin's backend command to the absolute
path `/Users/shin/shinywings/Incurator/.venv/bin/wiki` (Settings → Incurator),
fix or delete the `~/.zshrc:122` alias (the `/home/shin` path is invalid on this
machine), and consider removing the stale anaconda install
(`/Users/shin/anaconda3/bin/wiki`) so the ambiguity cannot recur.

**STILL UNEXPLAINED** — the banner is additive and does not block the composer,
and the backend responds correctly, so the three UI symptoms (popover stuck
"Thinking", Send dead, purple pins missing) are NOT yet explained by either
hypothesis. Needs the Obsidian developer-console error to proceed.

**Original (REFUTED) hypothesis, kept for the record:**

The shipped v0.41.0 code is NOT broken. Verified on master `521b420`:
`npx tsc --noEmit` clean, `npm run build` clean, plugin Vitest 778/778 green,
and the bundle installed at
`second_brain/.obsidian/plugins/incurator-obsidian-agent/main.js` is
BYTE-IDENTICAL (md5 `f1183d75…`) to a fresh build of current master.

Root cause of the send/popover symptoms is the v0.36.7 stale-runtime gate
working as designed. `plugin/main.ts:182` fingerprints the vault's `main.js`
at plugin load; `plugin/main.ts:1293-1318` re-hashes the same file per request
and throws when they differ. The installed bundle was replaced in place at
09:12 while Obsidian was still running the previously-loaded bundle, so every
request now throws before provider launch
(`LLMClient.ts:874` in `streamChat`, `LLMClient.ts:1238` in `complete`).
`ChatSidebarView.handleSend` (`ChatSidebarView.ts:996-1000`) converts that
throw into a transient Notice and `return`s — which is why Send looks dead.
**Immediate user remedy: reload Obsidian.**

Two GENUINE defects this exposed (these are the hotfix scope):

1. **[P1] The reload error message is self-contradictory when only the bundle
   hash changed.** `plugin/main.ts:1314-1316` interpolates
   `installedVersion` and `runtimeVersion`, which are the SAME string whenever
   the user rebuilds the version they are already on. The user sees
   "Incurator was updated on disk (0.41.0) but Obsidian is still running
   0.41.0" — nonsensical and unactionable. `assessPluginActivation`
   (`plugin/src/utils/pluginActivation.ts:35-38`) correctly decides via hash,
   but the message only knows how to talk about versions. Fix: when the
   versions match and the hashes differ, say the bundle changed on disk and
   name the reload action; keep the version-diff wording for a real version
   change.

2. **[P2] A blocking, persistent condition is surfaced as a transient toast.**
   `ChatSidebarView.handleSend` shows a Notice and silently returns, leaving no
   durable indication in the composer. A missed/auto-dismissed toast makes the
   whole surface look dead. Fix: render a persistent reload-required state in
   the composer (with the reload action) instead of a fire-and-forget Notice.

**UNEXPLAINED — needs user input:** the missing purple pins are NOT explained
by this gate. `ChatSidebarView.renderContextChips` (`ChatSidebarView.ts:4240`)
never calls the bundle guard, so a gate throw cannot blank the chip row.
Working hypothesis is a separate exception inside `refreshActiveContext()` /
`buildAutoContextRefs()` — note `renderContextChips` empties the container at
line 4241 BEFORE building, so ANY throw during the build leaves the row
permanently blank (a fail-open-to-blank rendering pattern worth hardening
regardless). Need the Obsidian developer-console error, or confirmation of
whether the pins return after an Obsidian reload, to separate "stale runtime"
from a real v0.41.0 regression.

### 2026-08-04 — Deep system-defect audit findings (scenario conformance + P9 dry passes)

Source: user-instructed audit sweep (documented-scenario conformance, failure-case
coverage, edge cases, code defects, comparative check). Baseline master @
`521b420`, all four local gates green (pytest 1407P/6S/4XF, ruff, mypy 127
files, Vitest 778). Every finding below survived two consecutive verification
passes.

1. **[P2][bug] `wiki lint --fix` silently swallows search-index refresh failure.**
   `backend/src/curator/lint.py:1326-1329` wraps the post-fix
   `search.update_index(paths, embed=True)` in bare `except Exception: pass`.
   If lint rewrites N pages and the refresh raises (locked DB, missing embedding
   model), the command reports fixes applied while search keeps serving stale
   content with no warning. Violates SYSTEM_BEHAVIOR §32 ("must not claim a
   requested maintenance/indexing action completed when it was skipped"; degraded
   indexing must surface a CLI warning). Fix: propagate a warning to the lint
   CLI surface (same pattern as the v0.36.1 MCP refresh-warning fix).

2. **[P2][bug] Sync conflict archive breaks permanently across filesystems.**
   `backend/src/curator/db_sync.py` `_archive_conflict` moves
   `*.sync-conflict-*` files from the vault's `.curator/sync/` into repo-cache
   `runtime/sync_conflicts/` via `Path.rename`. When vault and repo cache are on
   different filesystems/volumes (external drive, iCloud vault), `os.rename`
   raises EXDEV — every autosync pass then fails visibly and **every retry fails
   forever** (spec §13.1 promises retry is safe/idempotent, but retry can never
   succeed here). Fix: `shutil.move` (copy+unlink) instead of `rename`.

3. **[P2][bug] StructuredLocator resolution fabricates `exact` and never emits
   `duplicate_anchor`/`stale`/`unavailable` (spec §29.3/§29.4 not implemented).**
   Both `retrieval/evidence.py` `_build_locator` and `context_service.py`
   `_locator_from_span` derive `locator_status` from DB span fields only: a span
   with heading/toc/page metadata is labeled `exact` without checking the file
   exists or still contains the heading; `block_id` is always `None`; file-level
   `stale` (content-hash drift) and `unavailable` (unreadable file) are never
   produced (`context_service.py:409`'s `unavailable` means "span row missing in
   DB" — a different condition). Since §29.3 allows clickable rendering only for
   `exact`/`fallback_file` and SEARCH_ENGINE_SCHEMA §12.2 makes rendering
   anything else clickable release-blocking, a renamed/deleted/edited source
   still yields a confident clickable locator — exactly the "working-looking
   link must never be fabricated" defect (§31.5). Reconcile: either implement
   file-level resolution (scan for heading/anchor, hash comparison, duplicate
   detection) or amend §29 to the DB-metadata contract — per repo rules,
   divergence means both are wrong until reconciled.

4. **[P2][bug] Sidechat never binds the active note's workspace — the workspace
   KRS curation lens is inert for the whole chat surface.**
   `plugin/src/ui/chat/ChatSidebarView.ts:1868` always passes
   `vault.adapter.getBasePath()` (the vault ROOT) as `workspacePath` to
   `fetchContext`; no plugin code references `01_Workspaces` or ancestor-walks
   for `curate.yml`, and the backend does not ancestor-walk either. Consequences:
   (a) a chat turn on a note inside `01_Workspaces/<proj>/` never applies that
   workspace's include/exclude KRS policy (SYSTEM_BEHAVIOR §9.1 implies
   in-workspace notes bind their workspace; §16.1 forbids discarding the
   selected workspace); (b) the adjacent comment claims "when wsPath is empty
   the backend resolves default" but wsPath is never empty — a user-created
   `curate.yml` at the vault root would silently bind as a workspace for every
   chat turn. Fix: derive the active note's ancestor workspace (nearest
   `curate.yml`) and pass it; else pass "" so default is explicit.

5. **[P3][docs] SCHEMA §7 MCP payload contracts are stale.**
   §7.1 `check_source_status` omits the `l4_complete`/`relpath`/`source` fields
   the implementation returns (`mcp/server.py:1263`) and does not document
   list/path modes (`state: untracked`, `stats`). §7.3 `get_available_models`
   lacks the `ok` wrapper and the `deepseek`/`ollama` provider keys the
   catalogue returns. Refresh the §7 examples (English first, then any KR
   mirror).

6. **[P3][docs/hygiene] `llm_identity.py:60,89` broad `except Exception: pass`
   without reason or logging** when reading optional CLI auth JSON for account
   display. Cosmetic fallback ("Authenticated"), but §32 requires an explicit
   reason + module logging on broad catches. Add a comment + debug log, or
   narrow to `(OSError, ValueError, KeyError)`.

### 2026-08-04 — Comparative-systems enhancement candidates (audit part 5)

Compared against GraphRAG v2.x, LightRAG, HippoRAG 2, khoj, Smart Connections,
RAGFlow. Not defects — candidate roadmap items, strongest first:

- **[enh] Incremental L4 synthesis**: L4 currently regenerates wholesale when
  any community report changes (`pipeline/synthesis.py:10,145`). Scope
  regeneration to synthesis nodes whose contributing report set changed
  (mirrors §27.5 report-identity discipline one layer up); biggest recurring
  LLM-cost cut for large vaults. GraphRAG 2.x ships the equivalent.
- **[enh] PPR-based local-route graph expansion** (HippoRAG 2): deterministic
  personalized PageRank over `active` relations; graph tables and lifecycle
  gates already exist. Already deferred to Program 3 by §20.1/§27 — this is
  the evidence it stays worth doing.
- **[enh] DRIFT-style explore trees** (§20.1 deferred item, GraphRAG parity).
- **[enh] Passive related-concepts sidebar**: read-only "related L3/L4 nodes
  for the active note" pane reusing existing `search_chunks` embeddings
  (Smart Connections UX parity, no new backend state).
- **[enh] Dashboard community-hierarchy view**: read-only visualization of
  `community_reports.level`/`parent_community_key` so the compiled L3
  structure is inspectable without SQLite access.
