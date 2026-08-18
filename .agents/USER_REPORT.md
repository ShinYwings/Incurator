# User Report

This document is a **plain Inbox (backlog) log** that records bugs reported by the user, required features, ideas, etc., in chronological order without any filtering.

Agents must check this document and triage the received items into the `To-Do (Queuing)` area or `Icebox` area of `.agents/ROADMAP.md`. Once the triage is complete, **immediately delete** the item from this document.

## 📝 User Inbox

### 2026-08-09 — [P0] jetski "no output produced": the agy CLI wipes our permission grant on every run

User, correctly angry: *"이거 v30부터 수차례 나온 버그인데 고쳤다고하고 제대로
검증도 안되고 계속 버그나고"* — reported repeatedly since v0.30, declared fixed
each time, never verified, still broken.

**Root cause, reproduced deterministically 3/3.** The message comes from the
Antigravity CLI, not from us. `syncAgyHeadlessReadPermission`
(`LLMClient.ts:67`, called once at `:2582`) writes
`permissions.allow = ["$read_file$()"]` into
`~/.gemini/antigravity-cli/settings.json`. **The agy CLI deletes that key on its
very next invocation:**

```
before agy runs : permissions = {'allow': ['$read_file$()']}
agy --print ... : exit=0
after agy runs  : permissions = None      <- wiped
run 1 -> None
run 2 -> None
```

So the grant survives exactly zero model calls. Every tool the model reaches for
in headless mode is auto-denied, producing empty output. Writing the file at
startup can never work; nothing re-asserts it, and **no test ever checked that
the value survived a run** — which is precisely the verification gap the user is
naming.

**Second, independent defect: we grant the wrong permission.** The observed
denial names the **`command`** permission (`"a tool required the \"command\"
permission"`), and the CLI's own remedy text suggests `command()`. We only ever
add `$read_file$()`. Even a grant that survived would not cover this failure.

**Every prior fix was at the wrong layer.** v0.48.4 changed the *prompt* so the
model would be less likely to reach for a denied tool. That is a mitigation of a
symptom; the tool is still denied whenever the model does reach for it.

Fix direction: stop treating this as a one-shot settings write. Either re-assert
the permission immediately before each `agy --print` invocation (and verify it
survived), or pass the allowance on the command line so no persisted file is
involved. Whichever is chosen, the test must run a real `agy` call and assert the
permission is still in effect afterwards — a unit test that only checks we wrote
the file would have passed every time while the bug shipped.

### 2026-08-09 — [P1/DESIGN] Benchmark Chrome's "Ask Gemini", which already does what we keep failing to build

User, for at least the second time: *"구글 chrome의 ask gemini 기능은 이런거
바로바로 잘 해주거든? pdf 불러왔을때 지금 렌더링된 페이지 아니더라도 다른
페이지 정보의 수식같은거 잘 불러와서 설명하는거. 그거 벤치마킹 하자고 했는데
계속 못하네"* — Chrome's Ask Gemini reads equations from pages that are not
currently rendered and explains them, immediately. Benchmarking it was requested
and has not happened.

**The request is right and the v0.54.0 plan took the wrong road.** That plan
(`.agents/plans/04_pdf_background_index.md`) designs a background BM25 **text**
index over every page. Chrome does not do that: it hands page images to a
multimodal model, which reads the page as drawn.

Consequences of having chosen text search:

- It cannot read a rasterized equation at all. Equation 29 of this very paper is
  `**==> picture [185 x 12] intentionally omitted <==**` — there is no text to
  index, so a whole-document text index still returns nothing for it.
- The CMMI10/no-ToUnicode problem (v0.52.3) exists only because we read the text
  layer. A vision read never encounters it.
- `source_spans.page_number` being a section index stops mattering.
- The quadratic `upsertPage`, the idle scheduler, the coverage disclosure, the
  page cap — all of it is machinery for making text search work.

The capability is already present and unused for this: `fetch_pdf_page` loads any
page, `extractCanvasRegion` rasterizes a region, `transcribePdfCrop` sends an
image to the vision model, and `llm.vision_model` is configured. The missing
piece is a policy that routes "I need a page I do not have" to a **rendered-page
vision read** instead of a text lookup.

The v0.54.0 plan should be re-opened with this as the primary route and text
search demoted to a cheap pre-filter, not the mechanism.


### 2026-08-08 — [P1] The job spinner keeps running while `wiki jobs list` and the dashboard show nothing

User report: the sidechat job-running indicator spins, but neither
`wiki jobs list` nor the dashboard's Jobs card shows any such job.

**Root-caused in the worker, not in the plugin.** `runtime/jobs.json` is the
only thing the passive indicator reads, and **nothing rewrites it on a terminal
job transition.** Inside `run_next_job` the snapshot is written at exactly two
points — `ingest_worker.py:199` (after L2 completes) and `:215` (before L3) —
and both write `running: [<this job>]`. The three terminal transitions write
nothing: `db.mark_job_done` (`:163`, `:243`), `db.mark_job_failed` (`:272`),
and `db.requeue_job_for_retry` (`:270`) are each followed by a plain `return`,
and the `finally` block only does `db_sync.maybe_auto_export` and
`client.close()`.

The long-lived thread does not close the gap either. `IngestWorker.run()`
(`:473`) calls `self._write_dashboard()` after every job, but
`_write_dashboard` (`:330`) writes the **markdown** build-status page
(`paths.dashboard`) — it never calls `runtime_state.write_runtime_snapshots`.
Its own docstring claims it is "Called at job start, completion, and failure",
which is true of the markdown file and false of the JSON snapshot the plugin
actually polls.

So after the last job of a batch ends, `runtime/jobs.json` stays frozen with
that job in `running` and `idle: false`, permanently.

**Why the three surfaces disagree, exactly as reported:**

| surface | reads | shows |
|---|---|---|
| sidechat indicator (`ChatSidebarView.ts:489`) | `runtime/jobs.json` only, polled | stale `running` → spins forever |
| `wiki jobs list` (`commands/jobs.py:18-24`) | refreshes the snapshot, then queries the DB | correctly empty |
| Dashboard Jobs card (`incuratorDashboardModal.ts:649`) | same JSON — but any CLI-backed surface (`jobs.py`, `sources.py`, `core.py`, `config.py`) calls `write_runtime_snapshots` first | refreshed → empty |

`build_jobs_snapshot` (`runtime_state.py:96-118`) is itself correct: it derives
`running`/`queued`/`idle` from one DB read, so a snapshot is never internally
inconsistent. The defect is purely that it is not **re-derived** when a job ends.

**Secondary contributor, not the cause.** The never-blank rule shipped in
v0.48.2 (PR #129) has no staleness bound: `ChatSidebarView.ts:493` does
`if (!jobs) return;` and the `catch {}` at `:509` is empty, both by design, so
the indicator also cannot clear itself if the snapshot ever becomes unreadable.
That is worth a max-age, but it is not what produced this report — the file here
is perfectly readable and simply stale.

Live state at time of diagnosis (quiescent, so the frozen snapshot has since
been refreshed by an unrelated command): snapshot `running: []`, `queued: []`;
DB `ingest_jobs` = 37 `done`, 2 `cancelled`.

### 2026-08-08 — [P1] LaTeX conversion copy fails and blames the LLM provider, which is fine

User report (recurring): copying a PDF selection as LaTeX fails with a notice
telling them to check the provider. The provider is **not** the problem.

**Two independent defects, both reproduced.**

**(a) Backend — `_CLI_NOISE_RE` deletes any digits-only line from a real
transcription.** `vision.py:106-110` ends its noise alternation with
`\d[\d,]*`, added to strip an agentic CLI's "tokens used" count. It is applied
per line to the model's actual output in `normalize_vision_latex` (`:131`), so
it also deletes legitimate numeric-only lines — an equation number on its own
line, a table cell, a page number, a matrix row. Measured end to end against
the user's real config:

```
$ wiki plugin pdf transcribe --text "1"
{ "ok": true, "latex": "", "model": "gemini-3.6-flash" }
```

and at the normalizer directly:

```
'<transcription>1</transcription>'   -> ''        # eaten
'<transcription>$1$</transcription>' -> '$1$'     # survives
```

The intro/outro strippers are innocent — neither regex matches `1`. When the
whole selection normalizes to empty the copy fails; when only part of it does,
content is silently dropped into the clipboard with no failure at all, which is
the worse half.

**(b) Plugin — every failure is reported as a provider misconfiguration.**
`ExternalPdfView.ts:1394` `convertSelectionToLatex` wraps the whole operation
in one `try` and its `catch` shows a single hardcoded string:
`"LaTeX conversion failed. Check Incurator Dashboard → LLM Provider."` The real
cause is thrown into `err` and sent only to `logger.error`, never to the user.
Three distinct causes land on that one message:

1. backend `ok: true` with an empty `latex` (defect (a)) — the guard is
   `if (!result.ok || !latex) throw new Error(result.error || "No transcription
   returned")`, so a **successful** backend call is reported as a provider fault;
2. `navigator.clipboard.writeText(latex)` — also inside the `try`, so a
   clipboard rejection (e.g. document not focused) reads as a provider fault;
3. an actual provider/spawn failure — the only case the message is true for.

**The provider was verified working throughout.** `.cache/config/config.yml`
sets `vision_model: antigravity-cli::gemini-3.6-flash` and
`latex_extract_model: ''`, so `_resolve_extract_client`
(`ingest_raw.py:1555-1576`) correctly falls through to the vision slot. Live
runs returned `ok: true` with faithful output, e.g.
`"where λ1 and λ2 are the eigenvalues of Σ"` →
`"where $\lambda_1$ and $\lambda_2$ are the eigenvalues of $\mathbf{\Sigma}$"`.

Fix direction: drop the numeric-only alternative from `_CLI_NOISE_RE` (or scope
it to lines adjacent to a recognized banner, which is what it was for), and make
the notice report the actual error, distinguishing "model returned nothing" from
"clipboard write refused" from "provider unavailable".

### 2026-08-08 — [P3] `npm audit fix` at the repo root fails with ENOLOCK

User report: `npm audit fix` errors with `ENOLOCK … This command requires an
existing lockfile`, and a suspicion that a previously-agreed lockfile policy
regressed because the lockfile is now pushed to the remote.

**Not a regression, and the lockfile belongs on the remote.** There is no
`package.json` and no `package-lock.json` at the repo root — this is a Python
backend plus an Obsidian plugin, and the entire npm project lives in `plugin/`.
Run npm from there:

```
cd plugin && npm audit fix
```

Tracking `plugin/package-lock.json` is deliberate and load-bearing: the Universal
Strict Workflow's Step 10 requires its top-level `version` **and**
`packages[""].version` to agree with `pyproject.toml` / `package.json` /
`manifest.json`, the CI `version-consistency` job blocks the merge otherwise,
and `backend/tests/test_spec_sync.py` reads that file directly as the single
source of truth for the active version. It has been tracked since the plugin was
imported into the monorepo (`9633497`, 2026-05-28) and has not changed policy.

Side effect to clean up: npm's own suggestion (`npm i --package-lock-only`)
creates a stray 88-byte `package-lock.json` with `"packages": {}` at the repo
root. It is meaningless and should be deleted, not committed.

### 2026-08-06 — [P1] Moving or deleting a vault file after import breaks every stored reference to it

User report: after importing a Zotero item, moving the resulting markdown note
to a different folder inside the vault made the sidechat unable to read it. The
agent answered `⚠ File not found: 03_Notes/Vision/3DRec/3D Line Mapping
Revisited.md` while the file was sitting at
`03_Notes/Papers/3DRec/3D Line Mapping Revisited.md`.

**Measured. The stale path is NOT in the database.** Checked every column that
stores a path against the reported string:

| table / column | rows matching the stale path |
|---|---|
| `sources.relpath` | 0 |
| `source_spans.relpath` | 0 |
| `search_documents.projection_path` | 0 |

So the reported symptom is **plugin-side**, and the root cause is blunt:

**The plugin subscribes to no vault file events at all.** Repo-wide there are
exactly two `registerEvent` calls, both in `ChatSidebarView.ts:266,273`, and
both are workspace events (`active-leaf-change`, `layout-change`). There is no
`vault.on("rename")` and no `vault.on("delete")` anywhere in `plugin/src`.
Obsidian fires both, with the old path supplied on rename — the plugin simply
never listens. Pinned context chips and session context therefore keep whatever
path they captured, and the agent dutifully tries to read it.

The existing comment at `ChatSidebarView.ts:264-265` says stale keys are
"harmlessly ignored" because `renderContextChips` will not render them. That
reasoning covers *rendering* only. It is not harmless for the agent's file read,
which is the path the user actually hit.

**The user's instinct — that the backend also stores locations that need
updating — is correct, and it is a second, independent defect.** The path is
denormalized into at least three places (`sources.relpath`,
`source_spans.relpath`, `search_documents.projection_path`), and nothing
reconciles them when a file moves. `sources.relpath` is only ever corrected
through an explicit re-add (`ingest_raw.py:2270`), which additionally resets
every layer status to `pending` — so even the one recovery path is destructive.
There is no vault watcher on the backend side either.

**This is already rotting in the live vault, independent of the plugin.**
Source 32 is registered as
`04_Resources/References/2D-Gaussian-Splatting-...-ref-5.md`, a path that exists
nowhere on disk; the real file is
`04_Resources/References/2D Gaussian Splatting for Geometrically Accurate
Radiance Fields2024 - Huang et al. - .md` (registered separately as source 33).
48 L2 atoms descend from the dead row, and they are exactly the 48
`invalid_source_path` errors that survive the v0.44.1 lint fix. That is a
rename that was never reconciled, showing the same gap without any plugin
involvement.

**Scope note for whoever plans this.** Reference Mode makes it more than a
string update: source 37 carries `is_reference=1`,
`logical_source_id='zotero:YACIRUKK'`, and
`sync_key='vault:04_Resources/References/…'`. A move has to decide what happens
to the sync key (it embeds the path), whether the Zotero logical identity should
survive a move (it should), and what a *delete* means — retire the source and
its dependency closure, or keep the derived knowledge. `wiki source rm` already
implements the retire-closure semantics, so delete handling likely routes there
rather than inventing a second path.

**Not a trivial fix — needs a plan.** It spans plugin event handling, backend
path reconciliation across three tables, Reference Mode identity, delete
semantics, and a repair for vaults already carrying dead rows (this one has at
least source 32). Per the Review Feedback Loop rule this gets a
`PLAN_TEMPLATE.md`-compliant plan before implementation, not a hot patch.

### 2026-08-06 — [P1] `wiki lint` reports 70 unfixable ERRORs; 22 of them are a macOS NFC/NFD false positive

Audit of `.curator/Collections/` after the post-v0.43.0 `wiki build`
(37 sources, health score 85/100, **70 errors / 0 warnings / 1736 infos**).
Every one of the 70 errors is `invalid_source_path`, and they split into two
distinct causes.

**(a) 22 errors — the file exists; the comparison is byte-exact across two
Unicode normalizations.** Proven, not inferred:

```
disk : b'...using Plu\xcc\x88cker Coordinate...'   (NFD, u + combining diaeresis)
db   : b'...using Pl\xc3\xbccker Coordinates...'   (NFC, precomposed ü)
equal as-is = False        equal after NFC = True
```

`lint.py:238` builds `inv.raw_paths` by walking the filesystem
(`raw_path.relative_to(paths.root)`), which on APFS yields **NFD** names.
`lint.py:802` then tests `candidate in inv.raw_paths` — a plain `set[str]`
membership test — against the atom's `source_path` frontmatter, which carries
the **NFC** form written from `sources.relpath`. NFC never equals NFD, so every
atom whose source filename contains a non-ASCII character is falsely reported
as a missing source. `Path.exists()` would have succeeded (APFS resolves the
two forms transparently); only the in-Python string compare fails.

**The suggested remedy makes it permanent.** The issue is marked `fixable` and
tells the user to run `wiki lint --fix`. The repair value comes from
`_source_relpath_for_context` (`lint.py:757-767`), which reads
`sources.relpath` — the NFC form again. So `--fix` rewrites the field to the
identical value it already holds and the same 22 errors reappear on the next
run. This is an error the user cannot clear by following the tool's own advice.

Scope note: 17 of 36 sources have non-ASCII relpaths in this vault. Only the
`Plücker`/`Přibyl` paper tripped it here, so the trigger is narrower than "any
non-ASCII" — the Hangul paths did not decompose the same way. Worth
establishing exactly which characters diverge before choosing a fix. The
obvious fix is to normalize both sides (`unicodedata.normalize("NFC", …)`)
at the comparison boundary rather than at any single writer.

**(b) 48 errors — a genuinely mangled `sources.relpath` that never existed.**
Source 32 is stored as:

```
04_Resources/References/2D-Gaussian-Splatting-for-Geometrically-Accurate-Radiance-Fields2024---Huang-et--ref-5.md
```

The real file on disk is
`2D Gaussian Splatting for Geometrically Accurate Radiance Fields2024 - Huang et al. - .md`.
The stored value is a hyphen-slugified form of the title with a `-ref-5`
disambiguation suffix — spaces collapsed to `-`, `et al.` truncated to `et`.
It is the only one of the 36 sources whose path does not resolve on disk at
all. Whatever wrote it produced a slug where a relpath belongs; the 48 atoms
descending from that source all inherit the broken pointer.

Both causes are cosmetic for retrieval today — the DB-native index keys off
`source_spans`, not these paths — but they make the health check unusable as a
signal, which is the point of having one.

### 2026-08-06 — [P2] Community hierarchy is flat by construction, and nothing tells the user

Measured on the post-build graph: **240 community reports, every one at
`level = 0`**, `parent_community_key` never populated.

`_entities.py:2229` hardcodes `level = 0`. SYSTEM_BEHAVIOR §27.4 explicitly
sanctions this — "Filtered connected components is the EXPLICIT degraded
fallback" — but attaches a condition: the fallback "never silently changes
serving mode: when the degraded filtered-connected-components path runs, it is
recorded in `config_hash` and **surfaced by the audit**, not hidden."

Half of that holds. `_GRAPH_FALLBACK_CONFIG` (`_entities.py:2074`) does carry
`"algorithm": "connected_components"` and is folded into `config_hash`. But
`config_hash` is an opaque 16-hex digest (`fc3c931ce6b59403`), and `graph_audit`
returns **only violations** — there is no code path that reports which
construction mode ran. `wiki lint`'s 1736 infos never mention it either. A user
looking at 233 flat concept pages has no way to learn that hierarchical
construction never executed. Same defect family as the §32 work in v0.44.0.

**The distribution is what makes it matter.** Over active relations only:

| | components | largest | size-2 components |
|---|---|---|---|
| active-only (what ships) | 233 | **176 entities** | 152 |

One community holds 176 of the vault's 965 entities (18%) — "GPU Optimization
and Parallel CUDA Pipelines for 3D Gaussian Splatting", 243 relations. §27.4
names this case directly: "**No unexplained giant component.** A single
component spanning more than the approved threshold of the graph is a benchmark
failure unless explained by the authored-topology structure." No threshold
constant exists in the code and nothing checks for it.

Meanwhile 152 of 233 concepts (65%) are single-relation, 1–2 entity
communities. Sampled, they are not garbage — "Analytic-Splatting and Custom
CUDA Implementation", "Prefiltering and Anti-Aliasing in EWA Splatting" are
coherent atomic notes — but 19 of them contain a summary that admits the
evidence is thin ("The available evidence is thin, covering only the
containment relationship…"). The layer is simultaneously too coarse at the top
and too granular in the tail, which is exactly the gap a real hierarchy closes.

Checked and **refuted** during this audit, so nobody re-reports it:
`community_reports.detect_communities` reads *all* relations with no
`lifecycle_status` filter, which looked like a §27.4 "active-canonical input
only" violation. It is not — that function is dead in production (callers are
tests only); the shipped path is `db.rebuild_graph_generation`, which uses
`connected_components(only_active=True)`. Verified against the artifacts: the
stored reports contain 782 active relation ids and **zero** quarantined ones,
and the 233/176 component profile matches active-only exactly (all-relations
would give 157 components with a 263-entity giant). The dead function's
docstring ("A later version may use Leiden") is stale and misdescribes the
architecture.

### 2026-08-06 — [P2] The L1 projection leaks a stale CTX file on re-ingest

`.curator/Collections/01_Contexts/` holds **37 files for 36 sources**.
`CTX-f349d7bf` belongs to no source row: source 37 ("3D Line Mapping
Revisited") now carries `context_id = CTX-f3a44022`. The source was
re-ingested, a new context id was minted, and the previous CTX markdown was
never deleted.

Severity is bounded by the fact that the search index is DB-native and indexes
`source_spans` directly — `record_type` counts are `source_span 2363`,
`knowledge_unit 1098`, `graph_entity 965`, `graph_relation 782`,
`community_report 233`, `synthesis_node 4`, total 5445, with **no CTX
projection at all**. So the stale file cannot be retrieved or cited. It is
filesystem litter and a wikilink target that outlives its source, not a
wrong-knowledge defect.

Every other layer is exactly 1:1 with the DB, which is worth recording as the
baseline this violates:

| layer | files | live DB rows | orphan files | missing files |
|---|---|---|---|---|
| 01_Contexts | 37 | 36 | **1** | 0 |
| 02_Atoms | 1098 | 1098 | 0 | 0 |
| 03_Concepts | 233 | 233 | 0 | 0 |
| 04_Synthesis | 4 | 4 | 0 | 0 |

(03_Concepts compared through each CON page's `community_report_id`
frontmatter, since CON ids and REP ids are different namespaces.)

### 2026-08-06 — [P2] Ten sources report `l2_status='skipped'` with no reason, and two of them have knowledge units anyway

10 of 36 sources carry `l2_status = l3_status = l4_status = 'skipped'` while
`status = 'curated'`. **All ten have an empty `layer_error` and an empty
`error_reason`** — nothing records why. This is the B3 compile-status
truthfulness item, now observable on real data.

Two of them contradict their own status:

| source | spans | knowledge_units | l2_status |
|---|---|---|---|
| 28 `03_Notes/.../Pfaffian System.md` | 9 | **11** | skipped |
| 31 `04_Resources/.../Multiple_View_Geometry...EN.md` | 1 | **11** | skipped |
| 17, 30, 33 | 8 / 1 / 1 | 1 / 2 / 2 | skipped |

A layer that produced 11 units is not "skipped". Either the status is wrong or
the units are stale from an earlier generation — both need distinguishing, and
today nothing in the record lets a user tell which.

The other five (19, 21, 22, 23, 24) produced 0 units from 6–7 spans each, and
all are 1.5–2 KB note stubs. Sources 30/31/33 are Reference-Mode markdown
stubs of 320-ish bytes. So "too little content to extract" is the plausible
reason for most — which is fine as behavior and unacceptable as a silent one.

Related, and confirming the earlier jobs-observability report: **source 36 (the
MVG book PDF) is gone from `sources` entirely** after the cancel, taking its
8,692 spans with it — the vault went from 11,052 `source_spans` to 2,363. Its
`04_Resources/References/MultipleViewGeometryHartley - .md` stub is still on
disk. So a cancelled job leaves the stub file behind with no source row.

### 2026-08-06 — [P3] L4 Synthesis pages are ~93% frontmatter

All 4 SYN files are ~11 KB on disk while `full_content` is 611–775 characters.
The bulk is the frontmatter `community_report_ids` list — each node cites all
**233** reports, and all four share one `dependency_hash` (`8979bbd05f45`) and
an identical report set.

The prose itself is good and is the strongest evidence the pipeline now works —
four distinct, accurate, cross-source themes with limitations stated (kernel
fusion in GS pipelines, line/quadric primitives in SLAM, hierarchical
localization, surface resampling in radiance fields). But as an Obsidian
artifact the page is a 10 KB ID dump wrapping a 700-character insight, and the
"cites all 233 reports" provenance is not selective enough to tell a reader
which reports actually produced the claim.

### 2026-08-05 — [P2] `wiki jobs list` cannot distinguish "working" from "hung", and names a PDF as `.md`

User observation during the post-v0.43.0 build: job 37 (MVG book) sat at "10%"
with no visible movement, and both jobs are PDFs but display a `.md` name.

**(a) The `.md` name is correct data, misleading display.** Both sources are
`file_type='pdf'`, `is_reference=1`, `logical_source_id='zotero:<key>'` — i.e.
Reference Mode. Per SYSTEM_BEHAVIOR §3.1 the backend keeps the PDF in place and
writes a lightweight markdown STUB under `04_Resources/`, storing the stub path
in `sources.relpath`. `wiki jobs list` renders that `relpath`, so a PDF job
shows the stub's `.md` filename. Fix direction: for `is_reference` sources
display the PDF/Zotero identity (or mark the row as PDF) rather than the stub
path. Cosmetic but actively confusing.

Noticed alongside: the generated stub names carry a trailing empty field —
`"MultipleViewGeometryHartley - .md"`, `"3D Line Mapping Revisited2023 - Liu et
al. - .md"` — so the stub filename template renders a separator for a metadata
field it did not fill.

**(b) The job was NOT hung; the progress number is a fixed marker.** Measured
3.7 minutes after start:

- `progress = 0.1` comes from `ingest_worker.py:180`, written **once** when L2
  begins. The next update is `progress=0.5` at `:195`, only after the whole L2
  extraction returns. Nothing moves in between.
- `progress_current / progress_total = 0 / 1` — the real counters are never
  advanced, so the "10%" is not derived from work done.
- `job_events` for that job: **0 rows**. SYSTEM_BEHAVIOR §6 says "Running jobs
  should publish phase/progress in `ingest_jobs` and `job_events`" — nothing is
  published, so there is no per-batch trace either.
- `input_tokens/output_tokens = 0/0`: no provider call had completed yet.

Scale explains the wait rather than a hang: **source 36 alone holds 8,692
source_spans — 79% of the entire vault's 11,052.** With a measured CLI provider
round-trip of 8–12 s, a batched L2 extraction over that source is inherently a
long job.

This is the same defect class as the Quick Query "Thinking…" fix (PLUGIN_SCHEMA
§1.4.3): a long operation that emits no progress is indistinguishable from a
hang. Fix direction: advance `progress_current/progress_total` per L2 batch and
emit a `job_events` row per batch, so `wiki jobs list` and the dashboard show
real movement and a stall becomes diagnosable.

### 2026-08-05 — [P1/DESIGN] The `local` route never descends L4→L3→L2→L1, so most queries read raw L1

User design intent, stated 2026-08-05: *"When querying, shouldn't it search
L4 → L3 → L2 → L1 → source in that order? Part of why I split L1–L4 in the first
place was that searching L1 every time would be enormously expensive.
Zettelkasten works that way too."*

**Measured against the code (`retrieval/evidence.py:364-447`), the descent is
implemented in only two of four routes:**

| Route | Evidence assembly | Descends? |
|---|---|---|
| `global` | L4 `_synthesis_items` → L3 `_report_items` → search only if both empty | yes |
| `explore` | memory paths + L4 synthesis primer + L3 report primer + entities | yes |
| `source-section` | every span of one source | n/a by design |
| **`local`** | **entities + their spans + `_add_search_hits`** | **no** |

`local` (`evidence.py:440-447`) never consults `synthesis_nodes` or
`community_reports` at all. It resolves query entities, attaches their L1 spans,
and appends flat search hits. A formula query in this vault routed `local`,
which is why it returned 9 bare entity names and 17 L1 spans (mostly
bibliography lines and headings) with one LaTeX-bearing item.

This matches SYSTEM_BEHAVIOR §17's own wording for `local` ("resolve query
entities… expand to related claims/concepts/spans"), so **the code conforms to
the spec and the SPEC diverges from the stated design intent** — the same shape
as the v0.43.0 corroboration finding.

**Two consequences:**

1. **Cost.** The layering was meant to avoid scanning L1 for every query, but
   `local` searches the full index where L1 spans are 11,052 of 12,435
   documents (89%). The distilled layers carry no retrieval-cost benefit on the
   route most factual questions take.
2. **Quality.** Descending from L4/L3 would surface distilled statements
   (which retain formulas in their claim text) ahead of raw spans, instead of
   letting bibliography lines outrank equations on lexical overlap.

**Caveat before acting:** `global` already degrades to flat search when there
are no synthesis/report rows — exactly this vault's state today (3 synthesis,
6 reports). So the descent cannot be evaluated fairly until the v0.43.0
corroboration fix has repopulated L3/L4. **Sequence: merge PR #116 → `wiki
build` → re-measure → then decide whether `local` should descend.**

Open design question for the user: should `local` consult L4/L3 first and fall
through to L1 only when the distilled layers do not answer, or should the
router send more questions to `global`? The first changes a route's contract;
the second changes routing policy only.

### 2026-08-05 — [P1/DESIGN] Formula-bearing claims almost never serve: the prose gate overrides an exact formula match

User report: formulas in L1–L4 are not deductively analyzed, so sidechat/MCP
cannot cite them.

**Measured** (`13ed51f8b06cb88e/state.sqlite`, read-only). Of 1,055 live
formula-bearing knowledge units, **only 86 (8%) are `verified`** — i.e. served:

| formula_status | support_status | count |
|---|---|---|
| `preserved_in_text` | **failed** | **490** |
| `uncertain` | unchecked | 309 |
| `preserved_in_text` | verified | 86 |
| `missing` | failed | 85 |
| `preserved_in_text` | unchecked | 85 |

Every one of the 575 `claim_supports` failures carries the **same** reason:
`"the cited span does not minimally support the claim (no salient term
overlap)"`. And **all 237 `formula`-role supports are `unchecked`** — not one
was ever validated.

**Cause 1 — the formula carve-out is unreachable in practice.**
`pipeline/claim_support.py:361` grants `verified` on an exact ordered formula
match only when `not claim_terms` — the claim must contain NO salient prose at
all. An LLM-extracted claim about an equation nearly always carries prose
("The rendering equation integrates radiance…, $L_o = …$"), so it has both
prose and a formula and falls through to `:371`, where `max_cov <
_SUPPORT_FAIL` (0.25) fails it outright. The `formula_status` written on that
same branch is `preserved_in_text` when `formula_ok` — so the system records
*"the formula IS exactly present in the cited span"* and fails the claim anyway.
That is precisely the 490-unit bucket.

SYSTEM_BEHAVIOR §26.1 does sanction the combination ("an F6 textual-grounding
failure may still carry `formula_status='preserved_in_text'`"), so the code
conforms. **The contract is what needs revisiting**: an exact ordered formula
match is strong evidence, yet it currently counts for nothing unless the claim
happens to be prose-free. Proposed direction — treat an exact formula match as
support in its own right when the claim also carries prose, e.g. lower the
prose bar (or waive it) for `formula_ok` claims instead of requiring the
degenerate prose-free shape.

**Cause 2 — nothing adjudicates `uncertain`.** `claim_support.py:304` states
that with no `client` an `uncertain` unit "stays `unchecked` (never promoted)".
The machine-local config has `provider: ollama` with `model: None`, so no
calibrated validator is available and the 309 `uncertain` + 928 `unchecked`
units are stranded permanently. They are stored and audited but never served.

**Cause 3 (smaller) — equation spans are scarce.** Only 105 of 11,052
`source_spans` are `span_type='equation'` (0.95%) in a vault of math-heavy
papers. Worth checking whether display math is being recognized at L1 at all.

**CORRECTION 2026-08-05 — the support gate is NOT the binding constraint.**

The user reframed the requirement in outcome terms: *"when I ask a question, if
a related formula exists in the knowledge system, it just needs to be usable as
prior knowledge for the answer."* Measured against that, the diagnosis above is
misleading and the proposed fix would not have delivered it.

**All 11,052 L1 `source_spans` are in `search_documents`, including all 105
`span_type='equation'` spans — indexed regardless of `support_status`.** The
claim-support gate governs which L2 `knowledge_units` are served (628 of 2,131);
it never removed the formulas from retrieval. So loosening it would not, by
itself, put more formulas into an answer.

What actually happens, measured with a real query
(`wiki plugin context fetch --query "Gaussian splatting covariance"`, a
formula-dense topic): **27 evidence items returned, exactly 1 containing any
LaTeX.** The rest are 9 bare entity names plus L1 spans that are mostly
bibliography lines ("2019. Differentiable surface splatting… ACM", five times)
and section headings ("D ADDITIONAL RESULTS" x3, "📖 참고 자료", "심층 분석 완료").

DB-level duplication is not the cause: only 98 of 11,052 spans share a preview
(0%). The cause is **retrieval ranking** — lexical matching scores a paper title
in a reference list as highly as the equation that answers the question, and
headings/boilerplate spans (`---`, `{% persist %}` template residue) are indexed
as ordinary content.

**Revised priority.** To satisfy the stated requirement, work the retrieval
side, not the support gate:
1. Rank or filter out non-content spans (bibliography blocks, bare headings,
   template residue like `{% persist %}` / `---`) at materialization or ranking
   time.
2. Give `span_type='equation'` spans (and spans containing LaTeX — 391 of them)
   a retrieval affordance so a formula-seeking query can actually reach them.
3. Only then revisit the L2 support gate, which affects distilled-layer quality
   and cross-source synthesis rather than basic formula availability.

The original Cause 1/2/3 analysis stands as an accurate description of the L2
gate, but it answers a different question than the one the user asked.

### 2026-08-09 — [P1] Equation 29 is a discarded image, and the answer could not say so

User asked about the 3D Line Mapping Revisited paper (source 37, Reference Mode)
and got: *"수식 29의 텍스트를 가져올 수 없어, 해당 수식에 대한 직접적인 유도
과정은 설명해 드리기 어렵습니다"* — then a fallback to equation (3). The user's
reaction: is this telling me to use it or not.

**Measured, and the answer's hedge was true but useless.** Equation 29 sits at
`SPAN-5a4b5830` and its stored text is, in full:

```
**==> picture [185 x 12] intentionally omitted <==**
```

The surrounding document order shows exactly what the reader lost:

| rowid | span | stored text |
|---|---|---|
| 10739 | `SPAN-a0abfeb1` | "Then inserting into (28) we get" |
| **10740** | **`SPAN-5a4b5830`** | **`picture [185 x 12] intentionally omitted`** ← equation 29 |
| 10741 | `SPAN-21f8f2bc` | "which is a rational function in _µ_ …" (this one cites "(29)") |
| 10742 | `SPAN-8cabd326` | "11" (a page number stored as its own span) |

`SPAN-21f8f2bc` carries `section_title = "B.2 . M1. Triangulation with Multiple
Points"` — the Supplementary Section B the answer guessed at. So retrieval
reached the right neighbourhood; the equation itself was never ingested.

**The new finding: v0.49.0 visibility does not cover the existing corpus.**
Vault-wide there are **132 placeholder spans and only 2 carry the `loss`
metadata** — both on source 37, both `classified_at 2026-08-08T15:18`.

```
placeholders  loss_tagged
132           2
```

The cause is that `classify_span_loss` (`pipeline/source_spans.py:47`) is called
only from the span *builder* (`:123`, `:134`, `:163`). It runs at span-creation
time and never backfills. Every span ingested before v0.49.0 therefore carries
no loss record, which is why the assistant could not say *"equation 29 is an
image I could not read"* — for that span, no such record exists. The feature
works; it has simply never run on 130 of the 132 regions it was built for.

Also measured on source 37: `span_type='equation'` count is **0** across 645
spans, and `MAX(page_number)` is 23 on a 27-page PDF (page_number is a section
index, confirming ROADMAP item 1's third blocker).

**Cheap and worth doing, separate from recovery.** A backfill needs no LLM call,
no re-ingest, and no schema change: `classify_span_loss` is a pure function of
text, and the placeholder text is already stored in `source_spans.text_preview`.
Running it over existing rows would take the answer from "I cannot get the text"
to "that region is a 185×12 image the parser discarded — snip it, or set
`llm.vision_model` and re-add." That is a different, much smaller job than
ROADMAP item 1 (recovery), which stays blocked on its three prerequisites.
