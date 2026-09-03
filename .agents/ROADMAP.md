# Incurator Roadmap

Single queue, ordered by **stability**, not by age or by size of payoff.

The ordering rule the user set on 2026-08-23: *"기능을 추가하기보다는 시스템
안정이 우선"* — stability before features. The phases below encode that. Within a
phase, order is free; across phases it is not.

| phase | what it buys | risk it carries |
|---|---|---|
| **A** | the system stops lying about its own state | none — no schema, no contract |
| **B** | growth stops before it forces emergency work | none — bounded, no contract |
| **C** | the pipeline actually produces all four layers | moderate |
| **D** | the structurally risky changes, **one per release** | high — schema and contract |
| **E** | result quality, once the pipeline is real | low |
| **F** | features | — |

**Consolidated 2026-08-23** from three Arena audits and two umbrella plans that
had been running in parallel with overlapping numbering. Every item was
re-checked against the code at `v0.63.0`; status lines say what was *verified*,
not what was assumed.

| audit | verdict |
|---|---|
| `system_defect_audit_arena` (code vs spec, 4 domains, ~29 findings) | shipped as B1–B7 across v0.42.2 → v0.50.2, and its **last survivor closed in v0.64.0** (#172). |
| `curator_state_arena` (storage and state) | **phase B** — several open, and two are *growing*. |
| `knowledge_value_arena` (does it deliver what it promises?) | **never triaged until now** — its four P1s are A1, A3, D2; its two P2s are E1–E2. |

`01_system_stability_overhaul.md`'s remaining workstreams are A5, F3, F4 and F5.
`03_system_integrity_consolidation.md`'s P8 closure — "delete 01, 02 and 03" — is
what this consolidation executed.

## Two rules that keep version-up stable

These are not items; they are constraints on how every item ships.

**1. At most ONE contract or schema change per release.** v0.63.0 broke this: it
bumped `SCHEMA_VERSION` **and** changed the prompt contract (the span-block
narrowing) in one release. It worked, but had resume failed, splitting the cause
between the schema and the prompt would have cost a day. A release that must
carry two should be two releases.

**3. Characterise before extracting.** Two similar-looking blocks are not
drift until you know why they differ. A5's one concrete item — three MCP tools
whose index-refresh policies looked like textbook drift — was implemented as a
shared helper and **both** pinned policies broke: registration is cheap and
re-runnable so an unexpected error should surface, while a build has just spent
minutes of provider time and must not lose it. Priced on what the failure costs
the user, not on symmetry.

The counter-case is equally real and equally checkable. `test_mcp_tools` pinned
`english_query == "failed question"` and that WAS drift: `git log -S` showed the
value appearing as an **added** line in a refactor about something else, with the
test written in the same commit. One test, no rationale, same commit as the code
it asserts → frozen accident. Two tests, different files, cost-based rationale →
a decision. Check before you touch it.

**2. A live run is a release gate, not a nice-to-have.** v0.63.0's unit tests all
passed against a prompt that was **eight times its own budget**; only running it
against the real vault found that. Any release touching the ingest or retrieval
path states its live check up front — and, as v0.63.0's P0 did, writes its stop
condition *before* the code and verifies it by measurement.

## Phase A — Make failure visible — **COMPLETE**

Shipped v0.66.0 → v0.69.0. Nothing here fixed a pipeline; together they made
every later measurement trustworthy.

| item | shipped | what it turned out to be |
|---|---|---|
| A6 | v0.66.0 | a prompt contract registered and promised in two specs for five months, **never called once** — deleted, not implemented |
| A7 | v0.67.0 | nothing recorded whether a search-query derivation ran, which is why one sample was mistaken for a property twice |
| A8 | v0.68.0 + v0.69.0 | a dead provider could report itself as a working derivation and silence the warning built to catch it; and non-English questions could not reach a synthesis answer **on four of five surfaces** |
| A5 | — | its one concrete item was investigated and closed as a non-issue; the discipline it carried is now rule 3 below |

## Phase B — Stop the growth

Bounded, no contract change. These degrade **monotonically**: every week of delay
makes the fix bigger and moves the failure closer to a moment you did not choose.
It is the user's disk and Syncthing bandwidth today; it becomes an outage later.

### B1. `.curator` state audit — the remainder

**Two closed in v0.69.1**: `wiki sync` now rebuilds all four files it always
claimed, and every document that placed `state.sqlite` inside the vault is
corrected with a test that fails if one does it again. The rest:


- **Closed in v0.69.2** — losing `.cache/`, opening the vault on a second
  device, and renaming or moving the vault all mint a brand-new empty database
  (the cache key is `sha256(resolved_root)[:16]`), and `wiki status` reported
  zeros exactly like a never-ingested vault. It now says so, in text and in
  `--json`, naming the sync journal and the `wiki db import` that restores it.

  The minting itself stays — the database is machine-local by design, so
  Syncthing never reconciles two devices writing one SQLite file. What was wrong
  was the silence, not the re-keying.

- `sessions.json` — **mostly closed in v0.69.4.** Re-measuring the audit's "81%
  re-embedded context" gave **93.9%**, and the cause was three unrelated things
  rather than one: payload nothing reads, six full rewrites per message, and a
  session cap that never capped.

  | | before | after |
  |---|---|---|
  | file | **17.31 MB** | **7.25 MB** |
  | full-file writes per message | **6** | **1** |
  | I/O per message | **~104 MB** | **~7 MB** |

  **What remains is not waste — it is a user-visible trade, and it belongs to
  B2.** `imageBase64` on auto refs is **4.07 MB**, and the transcript renders it
  as an inline chip thumbnail. Dropping it removes something the user can see, so
  it is a retention choice, not a cleanup. Five distinct values across nine
  copies, largest 1.33 MB.

  Also for B2: **`deletedSessionIds` is unbounded** — 59 tombstones against 11
  live sessions, unioned on every merge, pruned nowhere.

  Recorded for whoever touches the file next: **it syncs across devices**, so a
  schema change here is cross-device transport (v0.69.3 fixed a comment claiming
  otherwise), and `mergeSessionData` is **whole-session last-write-wins** — two
  devices editing one session lose a whole message list, not a message.

- Sync journals never compact — **now 88 MB, up from the audited 24 MB**;
  `compress=True` exists unused with gzip measured at 9.86×; a stale peer is
  skipped silently while `autosync` reports success.

  **Re-measured 2026-08-23, and the shape is not what the audit assumed.** Each
  journal carries exactly **one** header, so it is a full snapshot rewritten on
  every export, not an accumulating log — deleting one frees nothing, because
  the next auto-sync writes it again. There is no garbage to sweep here; the
  only fix is to make the snapshot smaller.

  Two levers, both measured:

  | | |
  |---|---|
  | this device's export | **74 MB**, 109,349 rows |
  | of which `deleted_records` | **46,637 rows — 43%** |
  | `compress=True` (unused) | gzip measured at **9.86×** |

  And the tombstones are **not** stale records that an expiry policy would sweep:
  every one of the 46,637 is from **2026-08**, none older than 30 days. They are
  **retry churn** — 33,506 `claim_supports` and 9,920 `source_spans` deleted and
  recreated by failed and re-run compiles. With C1 leaving 36 sources retrying
  L3, this grows for as long as C1 is open. Expiry alone would not have helped;
  **C1 is upstream of half this file's size.**
- Arena record: `.agents/plans/curator_state_arena/`

### B2. There is no retention policy — for anything, backend or plugin

**Filed 2026-08-23 on the user's concern**: *"계속 버전업하면서 부산물들이
생겨나는데 + 채팅 기록도 늘어나는데 쌓여가는거 어떻게 삭제할지 규칙이 없어서."*
They are right, and the gap is not one leak — it is the **absence of a rule**.
B1 lists individual symptoms; this item is the policy they are all missing.

**Measured 2026-08-23 on the reference vault.** Tables that gain a row per
operation and have **no `DELETE` anywhere in the codebase**:

| table | rows | grows per | delete sites |
|---|---|---|---|
| `deleted_records` | **46,637** | every deletion, incl. retry churn | 0 |
| `prompt_runs` | 3,826 | **every LLM call** | 0 |
| `query_traces` | 96 | every query | 0 |
| `compiler_generations` | 112 | every compile | 0 |
| `job_events` | 5,110 | every job phase | 1 |

Outside the DB, on the vault and the repo cache:

| | size | note |
|---|---|---|
| `.curator/sync/*.jsonl` | **88 MB** | full snapshot, rewritten each export; 43% tombstones |
| `.curator/sessions.json` | **17 MB** | the plugin's chat history — B1 measures 81% re-embedded context, one note stored 52×, a 1.39 MB base64 image, and a 30-session cap that is a provable no-op |
| `.curator/Collections/` | 15 MB | derived, regenerable |
| `.cache/vaults/` | 27 dirs | **25 are dead** — one per ephemeral path ever seen, never swept |
| `.cache/` (before this sweep) | 2.0 GB | held a **516 MB** temp venv from a script that no longer exists, leaked 2026-07-30 |

**What is actually missing.** Every one of these has a *reason* to exist and no
statement of *how long*. The deliverable is one policy, applied in both places:

- **backend** — a retention window per growing table, a `wiki` command that
  enforces it, and a line in `wiki status` when something is over budget (A3/A4
  built the reporting shape to extend);
- **plugin** — session/chat retention, image handling, and what `data.json`
  keeps, with the same window expressed once rather than per-surface;
- **the repo cache** — a sweep for dead vault caches and leaked temp dirs, since
  nothing has ever swept either.

### The shape, decided by the user 2026-08-23

*"도움되는거는 최대한 오래 있어도 좋지. 이외의 것들은 다른데서 보통 어떻게 규칙을
정하는지 보고 그거 따라해 … 가비지컬렉터같은거 만들거면 backend에서 하게하고
dashboard에다가 GC 탭 만들어서 … radiobutton 같은걸로 삭제 주기 사용자에게
선택지 줘서 선택하면 backend에 그대로 적용되게 (다른애들처럼 명령어 만들고
명령어 실행하는구조로)."*

So: **a backend garbage collector with user-chosen windows, driven by a CLI
command, surfaced as a Dashboard GC tab** — the same command-underneath shape
every other dashboard control already uses. Not a new mechanism; a new policy on
the existing one.

**Windows follow prevailing convention rather than invention**, per the same
directive. What the industry actually does: operational logs **30–90 days**;
[ChatGPT](https://help.openai.com/en/articles/8983778-chat-and-file-retention-policies-in-chatgpt)
retains API inputs/outputs 30 days for abuse monitoring and purges deleted chats
within 30 days; [ChatGPT Business/Enterprise](https://blog.stackaware.com/p/chatgpt-team-data-retention-security-compliance)
allows custom windows in 30-day increments with a 90-day floor;
[Google Chat](https://support.google.com/vault/answer/7657597?hl=en) keeps
messages 30 days past a deletion policy. **30 / 90 / keep** is the offer to
mirror.

Proposed classification — the Arena should challenge it, not inherit it:

| item | class | proposed default | why |
|---|---|---|---|
| `prompt_runs` | **diagnostic, valuable** | keep (or 1 year) | this table *is* how v0.63.0 was explained — the 44-call/24-batch evidence came out of it. The user's *"도움되는거는 최대한 오래"* points here. |
| `query_traces` | diagnostic | 90 days | same family, far lower value per row |
| `job_events` | operational log | 30 days | textbook 30-day case |
| `compiler_generations` | history | prune `discarded`, keep `authoritative` | status, not age, is the right axis |
| `sessions.json` (chat) | **the user's own writing** | user-chosen, default keep | not a log. Deleting someone's notes on a timer needs their explicit choice, which is exactly what the GC tab is for. |
| `deleted_records` | **correctness-bearing** | see the trap below | |
| dead `.cache/vaults/` dirs | garbage | sweep, no window | the path no longer exists; nothing to date |
| leaked `.cache` temp dirs | garbage | sweep >7 days | a 516 MB venv sat there for 3 weeks |
| `Collections/` | derived | never a GC target | regenerate, do not expire |

### v0.70.0 shipped the first half — and reshaped what the rest can be

`wiki gc` exists: `plan` reports, `run` deletes, and chat retention is
configurable (`gc.sessions_retention_days`, default keep) with the CLI stating
that removal reaches every synced device before it acts.

**The finding that reshaped this item.** `prompt_runs`, `query_traces`,
`compiler_generations` and `deleted_records` are all in `SYNC_TABLES` and exports
are full snapshots, so deleting a row either propagates to every device (with a
tombstone) or is undone by the next import (without one). **There is no
quietly-local delete**, which means every remaining DB target is a fleet-wide
deletion and therefore the user's decision, not a policy the agent can set.

The user chose the non-synced scope for v1. What is deliberately still open:

| target | why it is still open |
|---|---|
| `prompt_runs` cap | fleet-wide deletion; also must exempt the 1,354 referenced runs or v0.69.5's L3 resume silently un-resumes |
| `query_traces` | fleet-wide; also resolves live context packs |
| `compiler_generations` | fleet-wide; discarded rows are the safest subset |
| `deleted_records` (48,896) | **cannot be safely expired at all** — nothing records whether every peer has seen a tombstone |
| `job_events` (5,578) | genuinely local and safe, but an age rule erases the `wiki jobs` history the table exists for |

**Two corrections to this item's own framing**, both worth keeping:

- The repo cache is **not** 1.5 GB of garbage. It is 1.2 GB of downloaded models
  plus the 288 MB live vault database, both of which must stay; the actual debris
  was **6.4 MB across 11 directories**. I had been quoting the 1.5 GB as though a
  GC would address it.
- The `.cache` sweep's obvious rule is unsafe. "The vault path no longer exists"
  is a **mount test, not a liveness test** — an unmounted drive hashes to the same
  directory and reads as missing, and that directory holds `state.sqlite`. The
  shipped sweep requires a temp prefix and zero sources as well.

### The two escalations are RESOLVED (user, 2026-08-24)

Asked, because the roadmap said these two were the user's to settle:

- **`prompt_runs` — the agent decides, and a capacity cap is explicitly allowed.**
  *"prompt run은 너가 정해. 상한 용량을 정할수도 있고."* The age distribution
  argues for a cap rather than a window: 88 rows from July against 4,318 from
  August, so a 30/90-day window deletes nothing today and everything later, at a
  moment nobody chose.
- **`sessions.json` — the user picks the window.** *"sessions.json은 시간을
  선택할수 있게 하면 좋을거같아."* Their own writing, so the GC tab offers the
  choice rather than assuming one.

### Re-measured 2026-08-24, after the Phase A–C releases

| table | roadmap | now |
|---|---|---|
| `deleted_records` | 46,637 | **48,896** (still growing) |
| `prompt_runs` | 3,826 | **4,406** |
| `job_events` | 5,110 | **5,578** |
| `compiler_generations` | 112 | **122** |
| `query_traces` | 96 | 96 |

On disk: `.curator/sync` **86 MB**, `sessions.json` **15.6 MB** (v0.69.4's fix
applies on the plugin's next save), `.cache/` **1.5 GB** with **31 vault-cache
dirs of which 25 are dead**.

### A SECOND correctness floor, found while scoping (2026-08-24)

The tombstone trap below is not the only one. **`prompt_runs` is referenced**:
`prompt_run_id` appears in **seven tables** (`db/schema.py` ~415, 470, 492, 549,
678, 694, 726) plus `query_traces.prompt_trace_ids`, and **238 runs are
referenced by live `community_reports`**.

Those 238 are exactly what v0.69.5's L3 resume reads — `generate_report_prose`
compares the referenced run's `input_hash` to decide whether to skip. Purging a
referenced run silently un-resumes L3 and re-spends 238 provider calls (one per
live report carrying prose and a run),
with no error anywhere. **Any cap must keep referenced runs regardless of age or
count.**

### The trap this plan must not walk into

**Tombstone retention is a correctness constraint, not a preference.** A
`deleted_records` row is what tells a peer "this was deleted, do not resurrect
it". Expire it before a peer has synced, and that peer's next import **brings the
deleted row back** — silently, and looking exactly like a legitimate insert. So
the window for this table is bounded below by *how long a device may stay
offline*, not by taste, and it cannot be a free radio-button choice like the
others without a floor and a warning.

A GC written from the table list alone would get this wrong, which is why it
gets an Arena rather than a patch.

**Still an escalation, but a narrower one.** The user has now set the shape and
the convention; what remains for them is confirming the per-item windows above
once the Arena has argued them — especially `prompt_runs` (diagnostic value vs
disk) and `sessions.json` (their own writing).

**Sequencing.** C1 is upstream of the largest single number here: 43% of the
88 MB export is tombstones, and all 46,637 are this month's retry churn from the
36 sources stuck at L3. Fixing C1 shrinks this before any policy is written.

## Phase C — Complete the pipeline

Moderate risk. A four-layer system whose top two layers do not run is not
unstable so much as **partially built**. This is where "stable" and "the product
works" stop being different goals.

### C1. L3 prose had no resume — **CLOSED v0.69.5**

All 36 non-skipped sources sat at `l3_status='error'` because L3 is a global
pass: one capacity refusal fails every source at once, and the retry re-sent
every report the provider had already written.

The roadmap's premise was that the v0.63.0 shape would need "its own design"
because L3's unit of work is a cluster rather than a batch. It did not — it
needed **no new table at all**. The report already stores `prompt_run_id`, and
that run's `input_hash` is the same digest-of-the-rendered-prompt v0.62.0 and
v0.63.0 use as their key. All 238 prose-bearing reports joined cleanly.

Live gate, at zero provider calls: of 417 reports, **185 now skip**, 53 had
genuinely changed grounding and are correctly rewritten, and 179 were never
written. A retry spends its budget on 232 instead of 417.

**Watch what this does to B1's sync journal.** The journal is 43% tombstones,
and every one was retry churn from these stuck sources. That number should fall
on its own now; re-measure before designing any compression.

### C2. L4 had never produced anything — **CLOSED v0.69.6**

Diagnosed before designing, as the item required, and the diagnosis changed the
design. The cause was **one gate**: synthesis ran only when zero community
reports had failed, and that list takes one entry per failed report prose. Across
417 reports with a provider refusing on capacity it was never empty, so one
failure in 417 suppressed the whole layer.

The gate was **inherited, not decided** — `git log -S` puts its current form in
f663a0a, a commit about status truthfulness that split a shared error list and
carried the condition over. And it contradicted what it guarded:
`generate_synthesis` hashes its corpus and skips when unchanged, i.e. it is built
to be re-run as the corpus fills.

L4 now synthesises over the reports that have prose and re-runs when more gain
it, so a partial L3 yields a partial-but-honest L4 that completes itself.
`l4_status` also stopped inheriting `l3_errors`.

**Not yet observed on the real vault.** The fix is unit- and pipeline-tested, but
the reference vault still has 0 `synthesis_nodes` because L3 there is mid-repair
(C1). The first real `wiki build` that gets past capacity is the live gate for
this item — check `synthesis_nodes` and `SYN-*` before treating it as proven in
production.

### C3. Parser drift — **PREMISE FALSIFIED; honesty half shipped v0.69.7**

The item claimed a shipped parser fix never reaches existing sources, measured as
*"source 37: 646 spans stored, 2,050 computed from the same PDF today"*. An Arena
agent ran the **production parse path** (`compile._section_dicts` →
`source_spans.spans_from_sections`, no LLM, no writes) and the measurement did
not survive:

| claim | measured |
|---|---|
| 2,050 spans today vs 646 stored → the parser now finds more | 2,050 **emitted**, **646 distinct hashes** |
| the extra spans are content the old parser missed | **0 new hashes, 0 hashes that disappeared** |
| sources are never re-parsed | `parsers.parse()` runs **before** the hash comparison, so every `wiki add` re-parses every file |

The 646↔2,050 gap is emission multiplicity collapsed by
`UNIQUE(source_id, content_hash)` — one span is emitted 77×, mean 3.17×.
Source 37 was recompiled 2026-08-22 (`GEN-cb7e5d2a`, authoritative) and **zero**
spans were inserted. `force_pending` is already a full parser re-derivation.

**A claim I made during this item was also wrong.** I said reference-mode sources
never re-parse their target, reasoning from the 446-byte stub that `add_file`
hashes. Source 37 is reference-mode and has three generations (08-08, 08-18,
08-22): L2 re-parses the *resolved external file*, not the stub. I inferred a
path from one file instead of reading the generation history.

**So the 22.5-hour re-derivation this item implied was never needed** — the
corpus is not stale. The user chose the honesty half, and it shipped as v0.69.7:
`last_ingested` is stamped when an authoritative generation is published, and the
ledger no longer reports "never" over 1,098 atoms.

**The remainder is CLOSED too, by looking rather than building.**
`upsert_source_span` never updates metadata on a hash match, so a span's `loss`
label cannot be repaired by re-parsing: 1,254 placeholder-bearing spans, 1,135
labelled, **119 unlabelled**. I started a release to make `wiki lint` report that
count, on the reasoning that a repairable gap nothing surfaces is the same defect
as the rest of Phase A.

**It is already surfaced.** `lint.check_extraction_loss` reads `text_preview` as
well as `metadata`, so it reports these regions whether or not a `loss` record
exists — one issue per source, silent when clean, and pointing at
`llm.vision_model`, which is more actionable than the count I was about to add.
`backfill_span_loss`'s own docstring says so: *"leave it for `wiki lint`, which
detects loss from text regardless."* The work was reverted unshipped.

So the 119 are an internal data-completeness gap, not a visibility one, and
`wiki lint --fix` repairs them deterministically whenever the user wants. Nothing
to build. **Anyone reopening this should run `wiki lint` first and read what it
already says.**

### C4. Community hierarchy is flat — **SURFACED v0.69.8**

Measured, and worse than this item recorded: the largest community holds **567**
memberships (30%), **293 of 417** are bare pairs, every report is `level = 0`, and
`parent_community_key` has never been set.

§27.4 permits the degraded connected-components path on one condition — that it
be *"recorded in `config_hash` and surfaced by the audit, not hidden"*. It was
hidden: `config_hash` is a 16-character digest, irreversible where it is read,
and `graph_audit` returns relation-level violations only. `wiki lint` now names
the algorithm and reports the partition's shape.

Three decisions, each ruling out a worse version: **INFO not violation** (§27.4
permits this path; a permanent violation trains the reader to skip the audit);
**no giant-component threshold** (§27.4 defers it to a benchmark freeze that has
never run, and inventing the constant repeats the `PROMPT_CONTRACT_VERSION`
failure — edited once while its prompt took twelve commits); **self-retiring**
(a hash comparison, so it vanishes when an approved algorithm ships).

**What is NOT done, and is deliberately not scoped here:** real hierarchy levels.
§27.4 requires the algorithm be chosen by the frozen multi-metric benchmark, not
assumed — *"Modularity alone is insufficient"* — and adopted only if it improves
the approved gates with no homonym, provenance, report-support or stability
regression. That is a Phase-E-sized project with a benchmark to build first, and
it now has an honest baseline to be measured against.

## Phase D — Structural risk, ONE per release

High risk: schema and contract changes. Each of these gets its own release, its
own migration rehearsal, and its own rollback drill. Never two in a batch — see
rule 1 above.

### D1. Converged entity/span ids orphaned their children — **SHIPPED v0.72.0**

The entry below described the remedy as "a transport identity for both tables
plus the id-remap plumbing — a schema change touching every referencing column."
**That was wrong, and measuring it is what showed why.** Both tables already
carry their natural key as a UNIQUE index, so unlike `sources` — which needed a
separate `sync_key` because `relpath` alone was insufficient — no new column was
required. The only missing piece was translating a peer's ids to ours at import.

What shipped: a post-pass in `import_knowledge` that records the id this device
already uses for each converged row and rewrites every reference, scalar columns
and JSON arrays alike. No schema change, no `SCHEMA_VERSION` bump, export format
unchanged, so old and new devices still interoperate.

The bug was real and had already fired: the reference vault's peer export carried
691 entities and `MipNeRF360` already existed here under a different id. Nothing
broke that time only because that export happened to contain no relation touching
it.

Two alternative designs were rejected on evidence, recorded in the Arena and in
the CHANGELOG: deriving the id from the natural key turns a delete into a
permanent fleet-wide block on that key, and adding a `sync_key` column requires
resurrecting the `ALTER TABLE` mechanism v0.33.0 deleted.

### D1b. Tombstones matched the wrong device's ids — **SHIPPED v0.73.0**

The entry below said this "changes a transport field, so it needs a
`SCHEMA_VERSION` bump and the existing hard version gate — its own release."
**It did not.** A portable token turned out not to be constructible:
`claim_supports`'s key also contains `knowledge_unit_id`, and `knowledge_units`
has no natural-key UNIQUE index, so half the key has no portable form. What
shipped instead translates the ids that genuinely converge, which are exactly the
ones that differ between devices — no token-format change, no version bump, no
fleet gate.

Scoping it also turned up the mirror failure the original entry missed, and the
worse one: `_row_is_blocked_by_tombstone` builds an incoming row's token from the
peer's ids, so a row this device deleted walked back in past its own tombstone.

**Second release running where the roadmap's remedy was larger than the defect
required** (D1 was the first). Both times the difference showed up by measuring,
not by reading the entry. Treat a Phase D item's stated remedy as a hypothesis.

### D1c. Relations converge on their natural key — **SHIPPED v0.74.0**

The roadmap called the key a modelling question. The data answered it:
`(source_entity_id, target_entity_id, relation_type)` is already unique across
all 2,787 relations on the reference vault, while `(source, target)` collides in
125 groups; `assertion_source` and `description` add nothing, and `description`
is LLM prose that differs between devices for the same assertion.

No UNIQUE index: `db.connect` re-applies `SCHEMA_SQL` every open, so adding one
would brick any vault already holding a duplicate. Convergence happens at import,
where duplicates are created. Existing ones are left alone — no migration, no
deletion.

### D1d. Source-id arrays carried the peer's numbering — **SHIPPED v0.73.1**

`prompt_runs.source_ids` is a JSON array of `sources.id` integers, which the
column-level remap cannot reach. Reproduced with two devices that registered the
same files in a different order: the array arrived naming a different source than
it meant. 2,984 rows carry one on the reference vault. Ids with no local
counterpart are dropped rather than kept, because a kept id names the wrong
source while a shorter array is merely incomplete.

### D2. The curation lens and the vault persona reach the chat surface — **SHIPPED v0.75.0**

Both halves landed: `context_service` puts `policy.applied_filters` and
`persona` into the pack, and `providerContextFormat.ts` renders both INTO the
prompt. That second half is the one that matters — the formatter is the only
thing the model ever sees, so a persona that stops at the pack shapes nothing.
Confirmed 2026-08-31: `providerContextLens.test.ts` passes 5/5, asserting the
persona line appears when set and is absent when not.

The original entry follows, as the finding it closed.

**From `knowledge_value_arena` [P1]. Not re-verified in this pass — carry the
audit's finding forward and confirm before planning.**

`curate.yml`'s KRS and the vault persona are the mechanism by which curation is
supposed to be "a dynamic lens applied at retrieval time" (the locked
architecture decision). The audit found neither reaches chat, which would make
the lens inert for the surface the user actually uses.

Adjacent to the context pack's `policy` block: once it emits
`policy.applied_filters`, an inert lens becomes *visible* as an empty filter set
rather than something that has to be inferred.

### D3. Backend `agy` spawn is contained — **SHIPPED v0.76.0**

The backend now wraps the spawn in the same OS sandbox the plugin has used since
v0.23.0, and no longer sets `*_TRUST_WORKSPACE`. Verified by running the real
profile: writes inside the vault succeed, writes to `$HOME` and `/tmp` are
refused, reads still work, the refusal survives three levels of nested shells,
and the CLI's own `~/.gemini` stays writable. An unsupported platform raises
rather than running uncontained.

**It is a write sandbox and does NOT close the v0.56.1 read grant** — that was
the entry's own warning and it still stands. Reads were never restricted on
either path.

One correction to the entry below: it described the exposure as bounded by
"exactly `read_file(*)` and `command(wiki)`". v0.71.0 added `mcp(*)`, because
scoped `mcp(...)` rules grant nothing and every MCP tool was otherwise
auto-denied. The bound is now those three.

Scoping this also broke the guard that keeps the test suite off the user's
provider account — wrapping the spawn moved `agy` off `argv[0]`, where the guard
was looking. Fixed in the same release; the guard scans the whole argv now.

## Phase E — Result quality, once the pipeline is real

Low risk, and deliberately after C: judging answer quality against a DAG whose
top layers are empty measures the wrong thing.

### E1. Entity descriptions are frequently circular — **PREMISE FALSIFIED 2026-08-31**

Measured against the live DB, all 2,481 non-redirected entities: **16 are
circular (0.6%)** and 77 more are empty (3.1%). "Frequently" is not what the data
says. Examples of the real ones: `'meshing' -> 'Meshing process.'`,
`'relighting' -> 'Relighting method.'` — a real defect, at a rate that does not
justify a release of its own. Fold it into E3-era prompt work if that happens;
do not schedule it alone.

The original entry follows.

**From `knowledge_value_arena` [P2]. Not re-verified — confirm before planning.**
The audit found graph entity descriptions that restate the entity name rather
than saying what it is or does, which is what the extraction contract requires.

### E2. Span segmentation isolates fragments — **PREMISE REPLACED; the real cause SHIPPED v0.79.0**

The chunker was never involved: `chunk_text` defaults to `target_tokens=256` and
never fires, because every record handed to it is already smaller than one chunk.
Atoms are one claim by design.

The cause was the INDEX. `materializer.py` used `text_preview` — the first 200
characters — as a span's searchable body. 4,865 of 11,774 spans (41.3%) sat at
that cap. Fixed in v0.79.0: on the 42 of 49 documents this machine can read,
truncated bodies went 564 -> 3, and a term past char 240 went from 1-of-6
findable to 65-of-65. The other 7 are blocked by macOS TCC — see E5.

Two options were considered and REJECTED on measurement, and both stay available:

- **Re-segmentation** (merge short spans). Span identity is
  `(source_id, content_hash)`, so merging mints new ids across 46 of 49 sources
  and risks an LLM re-extraction cascade. Hand-classifying 40 genuinely-short
  spans found only 20% truncated mid-thought; 37.5% complete by design, 42.5%
  PDF placeholders and page furniture. It would spend a cascade on a fifth of the
  smaller half.
- **Retrieval-time neighbour expansion.** Well argued, but its ordering is a
  proxy: `start_char`/`end_char` are 100% NULL and the available columns collapse
  11,774 spans into 1,176 groups, one holding 289 ties. Reconsider after E5, when
  the corpus is fully hydratable and the numbers can be re-taken.

The original entry follows.

### E2 (original) — CONFIRMED AND QUANTIFIED 2026-08-31

Measured over all 25,394 retrieval chunks in the live DB: median **181 chars**,
p10 71, p90 265. **21% are under 100 chars and 56% under 200.** For comparison,
retrieval chunks are normally 500–1,500. At this size a claim's supporting
sentence lands in a neighbouring chunk as a matter of course, which is exactly
what the audit described.

**This one needs the user before it can ship.** Changing chunk size means
re-embedding the corpus — a reindex of the user's vault, which CLAUDE.md makes a
stop-and-ask, not an agent decision. Plan it, then ask.

The original entry follows.

**From `knowledge_value_arena` [P2]. Not re-verified — confirm before planning.**
Segmentation produces spans small enough that a claim's supporting context lands
in a neighbouring span, which weakens both retrieval and claim support.

### E3. Formula RECOVERY — BLOCKED ON LOCATING THE REGION, and on C3

**Arena concluded 2026-08-20 with no build.** `.agents/plans/formula_recovery_arena/`
(`00_problem_v2.md` … `04_conclusion.md`). Five measurements removed every
premise the plan would have been written against, so the output is this
corrected item rather than a phase list.

`pipeline/formula_recovery.py` exists, exports `recover_formula`,
`classify_formula_loss`, `invalidate_formula_recoveries`, and has 6 passing
tests. `pipeline/compile.py` imports all three **only to re-export them**.
`recover_formula(` has **0 production call sites**.

**Wiring it today recovers 0 regions**, and not for the reasons this item used
to give. It cannot locate one:

- **0 of 2,121** loss regions carry page coordinates. All carry
  `{width, height}` and nothing else.
- The coordinates are not discarded — the parser never has them.
  `pymupdf4llm` emits `**==> picture [185 x 12] intentionally omitted <==**`
  and `source_spans.py:72` parses the size out of that string.
- They cannot be re-associated afterwards. Size join: **6 of 1,135**. Per-page
  positional join (k-th marker ↔ k-th image): **3 of 158**.
  `get_image_info` reports vector drawings too, so one page carries 5 markers
  against 36 image objects — the two lists describe different populations.

**Corrected numbers.** This item said "130 regions across 4 sources"; the vault
stores 1,135 across **3**, and the *current* parser finds **2,121** (437 + 11 +
1,673). The original Arena's "~48 regions", against which it estimated 0–2
recoveries, was low by a factor of forty.

**Corrected blocker order.** Blocker 3 is not a prerequisite alongside the other
two — it is the milestone, and it lives in parsing rather than in recovery code:

1. **Acceptance gate.** `formula_recovery.py:135` uses tuple equality where
   `validate_claim_support` uses subsequence. Measured on 8 faithful
   transcriptions: equality accepts 2, subsequence accepts **5**. The three that
   still fail differ in tokens, not span — `^\top` vs `^{T}`, `\boldsymbol` vs
   `\mathbf`, `\left…\right` sizing — so swapping the comparison is only half
   of it and notation normalisation is a contract question.
2. **`validator_trace_id` has no producer.** Every occurrence is a parameter, a
   pass-through, or a column read; the only non-`None` values in the repo are
   test fixtures. `reviewed` is unreachable. (This item's header previously
   claimed the producer existed at `:226`, contradicting this line. Corrected
   2026-08-20.)
3. **The region cannot be located.** See above. This is the gate.

**What would reopen it**: one cheap experiment — does `pymupdf4llm` expose the
association between an omitted-picture marker and the image object it stands
for? Yes → blocker 3 becomes tractable. No → the question is whether the
pipeline should stop using its markers and walk the page with `fitz`, which
needs its own briefing.

**Also blocked on C3**: every number above that comes from `source_spans`
describes an older parse.

### E4. agy shells out during graph extraction — Hartley PUBLISHED anyway (v0.63.0)

**NEW, found by the v0.62.0 live run (2026-08-21).** The staged compile now
fails in `curator.entity_relation_extract@v2`: 2 of 5 calls returned

> `permission check failed for command "python3 -c '… transcript_full.jsonl …'"`

The model tried to read the CLI's own transcript log to recover its prompt input.
This is the v0.60.0 class (model computes instead of answering), but **neither of
that release's causes applies**: the contract's schema flattens cleanly and IS
sent, and graph extraction is already batched by `client_optimal_chunk_chars`.
What remains is the agy model electing to run shell commands under a structured-
output contract, where one denied command fails the whole compile.

**This is a hard blocker for any large source, not an intermittent annoyance.**
Graph extraction batches by `optimal_chunk_chars` and **every batch must
succeed** for the generation to publish. Source 45 needs **~87 batches**
(1,551,159 prompt chars at 18,000 each). The observed agy success rate is
**57%** (4 ok / 3 failed across today's attempts), so the chance of a clean run
is about **7×10⁻²²**. Retrying cannot work. Any source past roughly a dozen graph
batches is effectively unpublishable until this is fixed — and the whole vault's
large references are in that class.

Fix directions, none investigated yet: grant the agy sandbox a scratch execution
allowance; route `entity_relation_extract` to a provider that does not shell out;
or make a denied shell command a retryable per-batch failure instead of a fatal
compile error. Belongs with D3.

**Related to D3 (the agy sandbox)** but not the same: D3 is about what the
spawned CLI is *permitted* to read; this item is about the model electing to
shell out at all. A sandbox changes which denials happen; it does not stop the
model from trying.


### E9. A git-history tool the model can call on purpose

**From the v0.80.1 hotfix (2026-09-03).** The prose router was removed because it
guessed intent from substrings. The user's stated need is the other direction:
*"너가 깃 히스토리 보면서 어떤 부분이 바뀌었는지 보는 경우가 있을거같긴해"* — the
MODEL wanting history while it works, not the human asking for it in prose.

**Constraint that decides the shape.** `surfaceToolReality` says everything
except ollama and deepseek routes through a CLI subprocess, which receives **no
plugin-injected tools** and loads its own MCP registry. So this has to be a
backend MCP tool (`curator_*`) to reach the providers actually in use; a
plugin-injected tool would be invisible on the CLI path — the v0.77.0 mistake.

Scope: read-only history. Push and commit stay out of the model's reach.

### E5. The backend never asks for folder permission — **SHIPPED v0.80.0**

Shipped as `wiki plugin access`, the Dashboard **Access** tab, and a grant
button whose result is re-probed against the backend. The root-cause fix was
the four call sites that asked "can I read this?" with `exists()`/`os.access`,
which both succeed on a file macOS will refuse to open; a source-tree test now
fails on a new one. Driving the tab in real Obsidian found three defects
fixtures could not — see CHANGELOG 0.80.0.

### E5 (original)

**Triaged in from `USER_REPORT.md` 2026-08-23.** macOS TCC denies `open()` on a
granted-looking path, so a directory the user never authorised reads as a corrupt
file rather than as a permission problem.

**Measured 2026-09-01, while shipping E2 — this is live, not hypothetical.**
Hydrating span text for the search index failed on 10,176 of 11,774 spans. The
cause was not code: 7 of 49 documents raise `ParserAccessDenied` because their
PDFs sit in `~/Library/Mobile Documents` (iCloud) and the process may not read
it. One of them, a book, accounts for 8,692 spans — 85% of the failure.

Those sources were ingested successfully in July and August, so access existed
then and does not now. The vault holds a 496-byte stub `.md`; the real text lives
only in the cloud PDF. This is exactly the user's scenario: **the PDF store moved
to the cloud after ingest, and nothing told anyone.**

**The backend already knows the answer and no one shows it.** `file_access.probe`
classifies OK/DENIED/MISSING, and `file_access.grant_root` walks upward to return
the SHALLOWEST folder the user must grant — verified on this machine, it returns
`~/Library/Mobile Documents` exactly. `ParserAccessDenied` carries it. Grepping
`plugin/src` for any of this returns **zero** hits: the计算 is done and the user
never sees it.

Scope, decided with the user 2026-09-01:

1. **A first-touch prompt.** On `ParserAccessDenied`, the plugin offers a button
   that opens a native folder picker at `grant_root(path)`. macOS grants access to
   a folder the user selects in an open panel, so choosing it IS the grant — no
   trip to System Settings, no instructions to follow.

2. **A Dashboard tab for granted folders.** The reader should be able to see which
   roots Incurator can read and which it cannot, without hitting an error first.
   Same place the other diagnostics live (`incuratorDashboardModal.ts`). List each
   configured root and each source root with its `probe` verdict, and offer the
   same grant button per denied row.

**Start with a measurement, not the UI.** The backend is a SEPARATE process that
Obsidian spawns. TCC attribution normally follows the responsible process, so a
grant to Obsidian ought to reach the spawned Python — but this repo has been
wrong about TCC repeatedly, and `grant_root`'s own docstring is a record of one
such correction. Phase 1 is: grant a folder through an Electron picker in
Obsidian, then check whether the spawned backend can read it. If it cannot, the
design changes (read inside the Obsidian process, or pass a security-scoped
bookmark) and the UI would have been built on a false premise.

Also note Zotero has TWO directories — the data dir and the attachment dir — and
they are granted separately. A UI that shows one and calls it done is the same
mistake in a new place.

### E6. The same file registers twice, differing only by Unicode normalisation — **SHIPPED v0.78.0**

Prevention and the merge both landed. Live vault: 50 → 49 sources, NFD 18 → 0,
collisions 1 → 0. Bigger than this entry said — `db_sync` reconciles peers BY
RELPATH, so it was a cross-device duplication mechanism, not a local annoyance.

The original entry follows.

### E6 (original) — CONFIRMED IN THE LIVE VAULT 2026-08-31

Not hypothetical. Of 50 registered sources, **18 (36%) have relpaths stored in
NFD**, and **one pair already collides**: `04_Resources/References/Camera Pose
Estimation from Lines us…` is registered twice, the two rows differing only by
normalisation form.

Splits cleanly, and the split matters:

- **Prevention** — normalise at registration so this stops happening. No
  migration, agent ships it.
- **The pair that already exists** — merging two `sources` rows and their
  downstream knowledge rewrites the user's data. That is a stop-and-ask, and it
  is the reason this entry is not simply "fix it". Detect and report first; merge
  only on the user's word.

The original entry follows.

**Triaged in from `USER_REPORT.md` 2026-08-23.** macOS filesystems hand back NFD
where most tooling produces NFC, so one file becomes two `sources` rows and its
knowledge is split across both.

### E7. The provider key travels as a CLI argument

**Triaged from `USER_REPORT.md` 2026-09-01; raised by code review 2026-08-29.**
Confirmed still open: `incuratorClient.ts:917` calls
`["plugin","secret","set","--name",name,"--value",value]`, and argv is visible in
`ps`. macOS restricts `kern.procargs2` to the same uid, which is why the v0.71.0
review scored it LOW, but "only every process you run" is not nothing.

The fix needs the value on stdin, and that path —
`main.ts runBackendJsonCommand` → `runBackendCommand` — is the spawn EVERY
backend call shares. Changing a shared signature mid-release for a LOW is what
the stability tiebreaker exists to prevent, which is why it is its own item.

To do: add an optional stdin channel to `runBackendCommand`, teach
`wiki plugin secret set` to read `--value -`, and move only `setSecret` across.
The existing `--value` path stays for the backend's own use.

### E8. `is_knowledge_question` gates nothing in the funnel — **SHIPPED v0.81.0**

The roadmap's framing was itself a workaround: gating `build_evidence` on the
flag would have fired only on the path that already classifies. The root cause
was that the flag is a byproduct of the TRANSLATION step, gated on "is the
question already English" — a condition chosen for cost, not for
classification need — and that its `bool = True` default asserted a verdict
for messages nobody judged. Field is now tri-state, the funnel refuses only on
an explicit `False`, and a fallback guess is never adopted as a verdict.

**Still open**: the English case on `wiki query` / MCP / `plugin query`. See
the Known gap in CHANGELOG 0.81.0.

### E8 (original)

**Triaged from `USER_REPORT.md` 2026-09-01; raised by code review 2026-08-29.**
Confirmed still open: `context_service` derives the value and carries it into the
request and the query trace, but the `build_evidence` call at line 777 is
unconditional. So a non-English "이 문단 번역해줘: <본문>" leaves `search_query`
empty, `working_query` falls back to the pasted body, and **BM25 runs over the
text the user asked to have translated.**

`plugin_api/context.py:64` already returns an empty pack on the same judgement,
so the two paths disagree about what the flag means. v0.71.0 only made the
docstring honest about it.

Gating the funnel skips retrieval outright — a control-flow change, so not a
trivial nit. Check what `QueryOrchestrator` answers with an empty pack before
committing to it: replying "정보가 없습니다" to a translation request is the wrong
answer, not a safe one.

## Phase F — Features

Everything here adds capability rather than repairing it. None of it is
unimportant; all of it is after A–E by the user's own rule.

### F1. Vault coverage — 44 sources registered against a ~101 target

**Plan 05 (`05_pdf_reading_assistant.md`) phase P5, still open.** Duty 2 ("remind
me what I wrote") is only as true as the corpus behind it, and less than half the
intended files are registered.

| | |
|---|---|
| sources registered | **44** |
| plan 05's target | **~101** |

Verified 2026-08-23. The plan's other phases are done: P0/P1 shipped (v0.54.0
#153, v0.56.0 #156), P2 region routing and P3 citation resolution exist
(`pdfReferenceContext.ts` resolves a bibliography entry and fetches the page),
P4's provenance block is assembled from resolution results, and P6's duty-2
acceptance was re-verified at the retrieval layer on 2026-08-23. **P5 is the
remainder**, which is why that plan is not deleted.

### F2. Workspace notes are invisible to duty 2

**NEW, measured 2026-08-22 during the P6 duty-2 re-verification.** The user
expected `01_Workspaces/COLMAP free GS/Research Notes/…` to come back when asking
"what else have I written about this?". It cannot: `01_Workspaces/` holds **0
ingested sources**. `ingest_raw.py` discovers files in `02_Wiki`, `03_Notes`,
`04_Resources`, `06_Archives` — the workspace tree is the Artist Space and is
deliberately not a source dir.

So duty 2 covers reference and note space but **not the place the user actually
drafts thinking**, which is where a "didn't I already work this out?" question
most often points. 12 vault files mention Plücker; 6 of them live under
`01_Workspaces/` and none are reachable.

**DECIDED 2026-08-22 (user): shape A — spans without projection.** The user's
scope is narrower than "ingest workspace notes": they want the agent to *cite*
workspace content when answering, with **no DAG promotion, not even L1**.

Measured to settle the design:

- Everything searchable lives in `search_documents`, built by
  `materialize_search_documents` SELECTing from DAG tables. "Searchable" today
  means "projected from a DAG record", so workspace text must land in some
  table the materializer reads.
- A CTX page is emitted **per source, not per span** (54 pages against 11,461
  spans), and `reemit_projections` is a separate function from
  `store_source_spans`. So span storage and L1 projection are separable.
- `source_span` is 11,461 of ~17,000 search documents — the dominant corpus.

**Shape A**: store workspace text as `source_spans` under an index-only source
flag, stop before the LLM, **emit no CTX page** and stay out of `index.md`. The
whole FTS5 + vector + RRF + rerank stack is reused unchanged, and the existing
`WHERE l2_status = 'done'` gate (`ingest_llm.py:251`) already makes the climb to
L2/L3/L4 unreachable.

**Shape B** (rejected): a parallel document store — new table, materializer
branch, retrieval route, embedding path. Literally not L1, but it pays heavy
engineering to move the same bytes to a different table and then has to re-solve
ranking fusion across two corpora. The boundary the user cares about is enforced
by the L2 gate and by skipping projection, not by which table holds the text.

**Two guardrails, non-negotiable in any implementation:**

1. **Exclude `01_Workspaces/**/.agents/` and `curate.yml`.** 13 of the 89
   workspace markdown files are agent bookkeeping and their content is
   *instructions* (e.g. `linear_algebra_verifier/SKILL.md`). Retrieved text
   enters the model's context, so indexing instruction files creates a
   prompt-injection surface inside the knowledge base.
2. **Label draft-tier evidence.** A workspace note is where the user writes down
   what they were *trying*, including things they later rejected. Answers must be
   able to distinguish it from a verified `03_Notes/` conclusion. The relpath is
   already carried; only the label is missing.

Volume: 76 markdown files, 512 KB — roughly doubles the current corpus, which is
the point, but it will move search results noticeably.

**Deferred, and to be planned via a MULTI-AGENT Arena debate when it comes up
(user directive, 2026-08-22).** Priority is below ROADMAP 5c.

### F3. Prompt architecture v2

**From the `01_system_stability_overhaul.md` umbrella.** Establish golden
fixtures and a cross-provider output-shape metric; version prompt profiles and
normalise provider output at contract boundaries **without** merging the sidechat
and popover tool policies.

### F4. Measured performance

**From the `01` umbrella.** Benchmark fixed RAG/DAG fixtures *before*
optimising; accept a change only with a measured speedup and no quality
regression. Nothing here has been benchmarked, so there is no baseline to
regress against.

### F5. Existing-surface UX

**From the `01` umbrella.** Confirmed friction in chat, popover, diff and
dashboard surfaces, validated against real plugin behaviour rather than unit
tests alone.

## Blocked / Icebox

### I1. Retrieval and projection leftovers

- Span segmentation isolates single-word fragments
  (`pipeline/source_spans.py` splits on blank lines with no minimum length).
- One stale CTX file survives re-ingest (bounded — the index carries no CTX
  projection, so it cannot be retrieved).
- Retro-repair for vaults carrying a dead source row from a pre-v0.46.0 move;
  `wiki lint` reports them but nothing fixes them.

### I2. PDF whole-document search — PLANNED, awaiting approval

`pdfFullDocumentIndex` ("Background page indexing") has **0 consumers** — the
toggle writes a value nothing reads, so `search_pdf_anchor` can only find
content on pages already rendered. The chat can read any page it can *name*
(`fetch_pdf_page`) but cannot *locate* one.

Arena concluded: `.agents/plans/pdf_background_index_arena/`
Master plan: `.agents/plans/04_pdf_background_index.md` (v0.54.0)

Two defects the Arena verified, both of which must be fixed before any walk:
- `upsertPage` is **quadratic** — 226,801 tokenize calls for 673 pages (337x).
- A naive `notifyContextChanged()` progress tick cascades into an unconditional
  main-thread BM25 search + chip rebuild, ~27 times per book open.

### I3. Drafts not yet planned

- Vault Storage Governance & Quota Visibility —
  `.agents/drafts/vault_storage_governance.md`
- Native PDF Annotation & Asset System —
  `.agents/drafts/pdf_annotation_system.md`
- Web Search Integration — no current plan; re-plan from current provider,
  privacy, and cost constraints.
- What the popover and the sidechat are each FOR —
  `.agents/drafts/surface_roles_brainstorm.md`. A brainstorm, nothing decided.
  The user asked for it on 2026-08-22 and placed it below the stability work; it
  carries the measured provider-capability matrix (which CLIs can search the web,
  which can read a 21 MB PDF), so it is worth keeping even if the role split is
  never acted on.

**Two drafts were deleted on 2026-08-23 as already answered**, not deferred:

| draft | why |
|---|---|
| `11_popover_chat_grounding.md` | shipped in **v0.54.0** — its complaint ("a question it could have answered came back as a report on what it had not received") is that release's own changelog line |
| `chat_context_compaction.md` | superseded by **B1**, which says so explicitly and carries the measured numbers the draft lacked |

### I4. Three audits' Arena records, now closed out

`system_defect_audit_arena/`, `curator_state_arena/` and `knowledge_value_arena/`
were walked item by item on 2026-08-23 and everything still open was folded into
the queue above. Those three folders were then deleted, along with
`01_system_stability_overhaul.md`, `03_system_integrity_consolidation.md` and
their evidence ledgers; `git log -- .agents/plans/` has them in full.

**What deliberately stayed**, because a live item still points at it:

| kept | why |
|---|---|
| `formula_recovery_arena/` | E3 is its conclusion and cites it |
| `agy_shell_out_arena/` | E4 |
| `04_pdf_background_index.md` + arena | I2 — planned, awaiting approval, never implemented |
| `05_pdf_reading_assistant.md` + arena | F1 — phase P5 is still open |

**Walked again 2026-09-01.** `route_intent_arena/` and `07_route_empty_derivation.md`
were deleted: both shipped (v0.47.0, v0.65.0) and nothing in this file pointed at
them any more. The four rows above were re-checked against their live items —
E3, E4, I2 and F1 P5 are all still open — so all four stay. `git log --
.agents/plans/` has the deleted pair in full.

`.agents/drafts/headless_permission_automation.md` went too. It was marked
"IMPLEMENTED — needs Executor review", and that review happened: the fetch MCP
auto-injection it describes is in `LLMClient.ts`, and its permission half is
recorded in the v0.71.0 CHANGELOG entry — `mcp(incurator_fetch)` and
`mcp(fetch_url)` were both auto-denied, and only the `mcp(*)` wildcard let the
call through. A draft whose review is done is not a briefing.

The ordering matters and is the thing that went wrong before: the folders were
once deleted as "finished" and had to be restored, because nobody had walked them
first. Walk, fold, then delete.
