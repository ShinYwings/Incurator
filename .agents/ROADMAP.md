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
| `system_defect_audit_arena` (code vs spec, 4 domains, ~29 findings) | shipped as B1–B7 across v0.42.2 → v0.50.2. **One survivor: A2.** |
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

**2. A live run is a release gate, not a nice-to-have.** v0.63.0's unit tests all
passed against a prompt that was **eight times its own budget**; only running it
against the real vault found that. Any release touching the ingest or retrieval
path states its live check up front — and, as v0.63.0's P0 did, writes its stop
condition *before* the code and verifies it by measurement.

## Phase A — Make failure visible

No schema change, no contract change. Nothing here fixes a pipeline; together
they make every later measurement trustworthy. **You cannot stabilise what you
cannot see**, and this project has repeatedly lost time to state it never
measured.

### A1. The route signal is destroyed at the boundary, not at the regex

**Corrected 2026-08-23 by measuring the real path.** `knowledge_value_arena`
filed this as "route selection is English-only"; that reading is wrong, and so
was the first correction of it.

`router.py:20` documents the English-only regex as **deliberate**: internals are
English by contract, `QueryRequest.english_query` exists for exactly this, and
v0.47.0 already reverted an attempt to make the regex multilingual — *"that fixed
the symptom by making the INTERNALS multilingual, which is the opposite of the
contract"*. The boundary fix it shipped instead **works**: `english_query` is
populated at `plugin_api/context.py:60`.

**The defect is what the boundary produces.** Measured end to end against the
live vault:

| Korean question | derived `english_query` | route |
|---|---|---|
| `2D GS가 3D보다 나은 점을 **여러 논문을 종합해서** 설명해줘` | `advantages of 2D GS over 3D` | **local** |
| `내 볼트 **전체의 주제를 정리**해줘` | *(empty string)* | **local** |

`derive_search_query` extracts **what to search for** and discards **what kind of
question it is**. "여러 논문을 종합해서" — synthesise across several papers — does
not survive into the English query, so `_GLOBAL_SIGNALS` has nothing to match.
The second case returned an empty string, and `working_query`'s
`(english_query or question)` fallback then silently handed the router the raw
Korean.

**Adding Korean to the regex would not fix this**, which is why the v0.47.0
revert was right. An English question routed through the same extractor loses its
intent the same way — the extractor is doing its job, and routing is reading a
signal that no longer exists by the time it looks.

Two candidate shapes, neither chosen:

1. `derive_search_query` already returns `(search_query, is_knowledge, reason)`
   and has understood the message. Have it return the **intent** too, so routing
   reads a derived signal rather than re-deriving one from surface keywords.
2. Use the `curator.query_router` LLM contract, which `router.py`'s own docstring
   says "exists for the ambiguous case" — currently unused on this path.

Shape 1 is cheaper and keeps routing deterministic. Shape 2 costs a round trip
per query. **Also fix the empty-string case regardless**: an extractor returning
nothing should be an explicit outcome, not a silent fallback to the untranslated
question.

**Phase A caveat:** option 1 changes what `derive_search_query` returns, which is
an internal contract. It is still phase A — no schema, no stored contract, no
cross-device effect — but it is the largest item in the phase.

### A2. Query expansion fails silently — the one survivor of the defect audit

**Verified open 2026-08-23**, the only unshipped item of ~29 in
`system_defect_audit_arena`.

Three sites swallow every exception with no logging at all:

| site | swallow |
|---|---|
| `retrieval/query_expander.py:152` | `except Exception: return {}` — the expander LLM call |
| `retrieval/query_expander.py:157` | `except Exception: return {}` — parsing its output |
| `retrieval/expansion.py:98` | `except Exception: extra = {}` — the expander as a whole |

**Why it survived is worth keeping.** The audit classified it as `RC-5(a)`, the
same class as `CAND-01` and `CAND-02`, and the synthesis said to *"expect a
duplicate and merge rather than fix twice"*. Batch B4 then fixed CAND-01
(`lint.py`, now warns with the failure reason) and CAND-02 (`llm_identity.py`,
now warns with a documented reason) — and dropped the third. **"Merge rather than
fix twice" was executed as "fix two of three."**

Consequence: when the local expansion model is unavailable or its output does not
parse, search silently runs unexpanded. Recall drops and nothing anywhere says
so.

### A3. Some knowledge units still never enter the search index

**From `knowledge_value_arena` [P1]. Re-measured 2026-08-23 — much improved, not closed.**

| | audit (v0.46.0) | now (v0.63.0) |
|---|---|---|
| live `knowledge_units` | 2,799 | 8,994 |
| indexed | 1,098 | 8,017 |
| **never indexed** | **1,701 (61%)** | **977 (11%)** |

Whatever shipped between those versions fixed most of it. 977 units the vault
believes it holds are still unreachable by search, and nothing reports the gap —
`wiki status` counts units, not indexed units. The remaining 11% has never been
characterised: it may be one cause or several.

### A4. The system reports healthy with an empty L4 and 36 errored L3s

`wiki status` counts sources, units and pages. It does not report that
`synthesis_nodes` is empty, that every non-skipped source sits at
`l3_status='error'`, or that 977 units never reached the index. All three were
found by hand-querying the DB, which is not a thing a user does.

**Nothing here fixes a pipeline — it makes the pipeline's state legible**, which
is the precondition for every item in phases B–E. A layer that is empty should
say so, loudly, in the command whose whole job is to answer "how is my vault
doing".

Cheap by construction: the counts already exist as queries used elsewhere.

### A5. Safe decomposition and exception hardening

**From the `01` umbrella.** Characterise behaviour before extracting any
remaining god-file ownership domain. Replace silent broad catches only where a
typed boundary outcome is defined and regression-tested — A2 is the last
known instance of the untyped kind.

**Concrete item recovered from the stash stack, 2026-08-23.** Four entries sat
there; three were shipped or superseded and were dropped, and the fourth
(`post-pr73 mcp helper follow-up edits`) had **shipped in substance but not in
shape**. Its behaviour — catching `(OSError, sqlite3.Error,
search.SearchBackendError)` around `search.update_index` and returning
`"Search index refresh skipped: …"` as a tool warning, rather than failing a
write that had already succeeded — is in `mcp/server.py` verbatim. What never
landed is the **shared helper** it extracted, so that try/except now sits at
**four** sites (`mcp/server.py:1521`, `:1616`, `:3096`, `:3146`) and two of them
have widened to a bare `except Exception`.

Not a bug — the behaviour is right at every site. It is precisely this item's
subject: one typed boundary outcome defined once, instead of four copies that
have already begun to drift. The original patch is archived locally at
`.cache/stash-archive-2026-08-23/stash-0.patch`.

## Phase B — Stop the growth

Bounded, no contract change. These degrade **monotonically**: every week of delay
makes the fix bigger and moves the failure closer to a moment you did not choose.
It is the user's disk and Syncthing bandwidth today; it becomes an outage later.

### B1. `.curator` state audit — the remainder

- Losing `.cache/` reports a healthy **empty** vault: `connect()` self-heals a
  schema into any empty DB and `get_stats` returns zeros. Recovery exists (the
  in-vault sync journal + `wiki db import`) but is silent and undocumented.
- Vault rename/move silently mints a new empty DB (cache key is
  `sha256(resolved_root)[:16]`); also hits `VAULT_ROOT=testbed` from two
  directories.
- `sessions.json` 15 MB, **81% re-embedded context** — one note stored 52×, a
  1.39 MB base64 image, ~1.1 s per send. The 30-session cap is a provable no-op.
  Supersedes the old "Chat Session Context Compaction" draft.
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
- `wiki sync` claims to rebuild `ledger.md`/`overview.md` and calls neither.
- `SYSTEM_BEHAVIOR.md` contradicts itself on where `state.sqlite` lives.
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

### C1. L3 global clustering has no resume — 36 sources are stuck

**Found 2026-08-23 while diagnosing source 45.** Every one of the vault's
**36** non-skipped sources reports `l3_status='error'`, and the recorded reason
is the same for all of them:

```
L3 global clustering encountered errors:
  Antigravity capacity exhausted (429). Model tried: 'gemini-3.5-flash'.
```

L3 is a **global** pass, not a per-source one, so a single capacity refusal
fails every source at once. And L3 has none of the resumability now built into
the layers below it: v0.62.0 made L2 extraction resumable, v0.63.0 did the same
for graph extraction, and **L3 was never touched**. The identical defect, one
layer up.

The v0.63.0 shape is known to work and is directly transferable — stage each
completed unit of work keyed on `prompt_runs.input_hash`, release rather than
delete on failure, replay at publish. What differs is that L3's unit of work is a
*cluster* over the whole corpus rather than a batch within one source, so the key
and the staging granularity need their own design rather than a copy.

### C2. L4 has never produced anything — diagnose before designing

**Found 2026-08-23 while sequencing this roadmap.** Not "L4 failed recently" —
L4 has never once succeeded, across the whole vault's history:

| | |
|---|---|
| `synthesis_nodes` rows | **0** |
| `SYN-*` files in `.curator/Collections/04_Synthesis/` | **0** |
| sources at `l4_status='done'` | **0** |

Meanwhile `retrieval/materializer.py`, `retrieval/evidence.py` and
`context_service.py` all read `synthesis_nodes` — three code paths that have
never had a row to read.

This is different from item C1. L3 demonstrably works: it produced **514**
`community_reports`, the newest dated 2026-08-22, and its current
`l3_status='error'` is a capacity failure on top of a working layer. L4 has no
such history to point at.

**Diagnose first, design second.** Whether this is a gate that never opens, a
dependency on L3 completing cleanly, a contract that never validates, or a step
nothing ever calls, is unknown — and a plan written before knowing would be a
plan for the wrong problem. The architecture calls L4 "shared stored synthesis";
the vault has none.

**Consequence for the DAG's honesty:** the system advertises four layers and the
top one is empty, while `wiki status` reports no gap. A4 is the visibility half
of this; C2 is the cause.

### C3. A source whose parse improved is never re-derived

`l2_status='done'` means a source is never re-parsed, so **a shipped parser fix
reaches only sources ingested after it**.

Measured on source 37: **646 spans stored, 2,050 computed from the same PDF
today**, and **4** loss records stored against **437** the current parser finds.
It was added 2026-08-04; v0.49.0 taught the parser to report unreadable regions
on 08-08. It has never seen that improvement and never will.

Consequences beyond one source:

- Every stored measurement is a claim about whatever parser ran when that source
  was last ingested, and nothing says so at the point of reading. This is how
  ROADMAP 1 came to be scoped against a count that was wrong by 40×.
- A parser improvement silently splits the corpus into sources that have it and
  sources that do not, with no surface reporting the split.

Not designed. The obvious approach — record the parser/contract version on the
source and re-derive when it moves — is a schema and cost question
(re-parsing the 673-page book takes 79 s; the whole vault is unmeasured), so it
needs a plan rather than a patch.

**This is upstream of E3** and should be settled first.

### C4. Community hierarchy is flat by construction

`_entities.py` hardcodes `level = 0`; one community holds 176 of 965 entities
while 152 of 233 are single-relation pairs. §27.4 permits the degraded
connected-components fallback but requires it be "surfaced by the audit" —
`config_hash` records it only as an opaque digest and `graph_audit` returns
violations only.

## Phase D — Structural risk, ONE per release

High risk: schema and contract changes. Each of these gets its own release, its
own migration rehearsal, and its own rollback drill. Never two in a batch — see
rule 1 above.

### D1. `graph_entities` / `source_spans` transport on a surrogate id

Both carry a natural identity — `UNIQUE(canonical_name, entity_type)` and
`UNIQUE(source_id, content_hash)` — but sync transports them on the surrogate
`id`, so two devices that independently extract the same thing mint different
ids. The key lookup misses, the insert collides on content, and convergence has
to be classified after the fact (v0.50.0 does this via `PRAGMA index_list`).
`sources` solved the same problem properly with a `sync_key` transport identity,
so the primary lookup finds converging rows directly and children remap to the
local id.

Nothing remaps `graph_relations.source_entity_id`/`target_entity_id` when an
entity converges, so the classifier makes the symptom quiet without closing the
gap. The real fix is a transport identity for both tables plus the id-remap
plumbing — a schema change touching every referencing column, which is why it
was left out of v0.50.0 rather than smuggled in.

### D2. The curation lens and the vault persona never reach the chat surface

**From `knowledge_value_arena` [P1]. Not re-verified in this pass — carry the
audit's finding forward and confirm before planning.**

`curate.yml`'s KRS and the vault persona are the mechanism by which curation is
supposed to be "a dynamic lens applied at retrieval time" (the locked
architecture decision). The audit found neither reaches chat, which would make
the lens inert for the surface the user actually uses.

Adjacent to the context pack's `policy` block: once it emits
`policy.applied_filters`, an inert lens becomes *visible* as an empty filter set
rather than something that has to be inferred.

### D3. Backend `agy` spawn has no OS sandbox (opened by v0.56.1)

`AntigravityCliClient._run` (`backend/src/curator/llm.py`, the Antigravity
client) spawns `agy` with plain `subprocess.run` — no sandbox wrapper, unlike
`CodexCliClient`, which passes `--sandbox read-only`. It also sets
`ANTIGRAVITY_TRUST_WORKSPACE` / `AGY_TRUST_WORKSPACE`.

This was latent while the read permission was broken. v0.56.1 fixed that
permission (it had to — the vision path was dead without it), so the backend
now spawns an unsandboxed CLI that can read any file the user can, on the code
path that processes **ingested, untrusted source material**. The trade was
taken deliberately and is recorded in PLUGIN_SCHEMA §13.5 and in both plugin
guides.

**Be clear about what fixing this buys.** The existing sandbox
(`sandboxWrapper.ts`) is a *write* sandbox: macOS Seatbelt is `(allow default)`
+ `(deny file-write*)`, and Linux bwrap read-only-binds the whole filesystem.
Applying it to the backend aligns the two spawn paths and adds write and
process containment — it does **not** close the read exposure, because reads
were never restricted on either path (`sandboxWrapper.ts:19`: "Reads are
intentionally still allowed (denying reads breaks the CLI's…)").

So this item is worth doing as hardening, and MUST NOT be filed as "the fix for
the v0.56.1 read grant". Closing that would need a read-restricted profile with
an allowlist of everything agy needs — designable, but it breaks on every agy
release, which is why it was not attempted here.

The exposure is bounded by what else is granted: exactly `read_file(*)` and
`command(wiki)`, with unapproved tools auto-denied in headless mode. No write
tool, no arbitrary shell, no network tool. Realistic worst case is a secret
read into the user's own vault, not remote exfiltration.

Eliminating it entirely is a configuration choice, not a code change: a vision
model reached over an API takes image bytes directly and needs no filesystem
grant. Recommended in both guides.

## Phase E — Result quality, once the pipeline is real

Low risk, and deliberately after C: judging answer quality against a DAG whose
top layers are empty measures the wrong thing.

### E1. Entity descriptions are frequently circular

**From `knowledge_value_arena` [P2]. Not re-verified — confirm before planning.**
The audit found graph entity descriptions that restate the entity name rather
than saying what it is or does, which is what the extraction contract requires.

### E2. Span segmentation isolates fragments

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

### E5. The backend never asks for folder permission — it guesses paths it may not open

**Triaged in from `USER_REPORT.md` 2026-08-23.** macOS TCC denies `open()` on a
granted-looking path, so a directory the user never authorised reads as a corrupt
file rather than as a permission problem.

### E6. The same file registers twice, differing only by Unicode normalisation

**Triaged in from `USER_REPORT.md` 2026-08-23.** macOS filesystems hand back NFD
where most tooling produces NFC, so one file becomes two `sources` rows and its
knowledge is split across both.

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

The ordering matters and is the thing that went wrong before: the folders were
once deleted as "finished" and had to be restored, because nobody had walked them
first. Walk, fold, then delete.
