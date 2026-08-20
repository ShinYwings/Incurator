# Critique on "persist each batch as it lands"

Date: 2026-08-21 | Agent Persona: red_teamer

## 1. Vulnerabilities & Flaws

### F1 — CRITICAL. The proposal breaks a documented contract and calls it a Con

§2 admits it "weakens all-or-nothing from a property of the database to a
property of the publish gate", then does not check what depends on the property
it is weakening.

`extract_knowledge_units`' own docstring states the current guarantee: *"a
failed extraction writes no partial artifact."* That sentence is not decoration
— the module docstring repeats it, and v0.52.0 removed a mechanism specifically
because partial state was dangerous here. The proposal proposes to make partial
state normal.

**Required:** enumerate every reader of `knowledge_units` and show which filter
on `generation_id`. Not "the proposal has not audited those readers" — audit
them. `materializer.materialize_search_documents`, the claim-support validator,
`db.list_generation_units`, the graph builder, and whatever the plugin reads are
all candidates. One that does not filter turns a half-extracted book into
search results.

### F2 — 277 writes is the headline number and it is unmeasured

"Unmeasured. If each costs what `job_events` costs…" is a guess wearing a
number's clothes. `_persist_units` writes units *and* claim supports and does it
inside `db.connect()`, which re-runs `executescript(SCHEMA_SQL)` per call — the
same helper this project measured at 1.31 ms of pure ceremony in v0.61.0.

Worse, this is the *ingest* path competing with `job_events` writes and progress
updates on the same SQLite file, where a contended write was measured at
**5.23 s** before v0.61.0 moved the event writer off `connect()`.

**Required:** time `_persist_units` for one batch, on a real source, before the
design is accepted. If it is 2 ms this is free; if it is 200 ms, 277 of them is
a minute of added wall clock on the path whose budget is the entire problem.

### F3 — `_config_key` is admitted to be a guess, and a wrong guess corrupts silently

§2's last bullet lists the inputs it is unsure about, then ships the design
anyway. If the span builder or section splitter changes, batch keys change too —
so a stale partial simply fails to match and is ignored. Fine. But if
*temperature* or a prompt template changes without changing the batch text, the
keys still match and the resumed run mixes units extracted under two different
prompts into one generation.

That is not a crash. It is a source whose knowledge units came from two
different systems, published as one, with nothing recording it.

**Required:** either derive `_config_key` from something that provably covers
the prompt (the contract's own version string plus a hash of the rendered
template), or state that mixing is acceptable and why.

### F4 — The conditional discard is the whole feature and gets one line

§1.4 says so itself: "that single line is where resumption is won or lost, and
it is the line most likely to be reverted by someone tidying up." A design that
identifies its own most fragile point and then does nothing about it has not
finished.

**Required:** a test that fails if the discard becomes unconditional again.
Not a comment.

### F5 — No expiry means the failure mode is silent growth

§2 admits partials are never cleaned up unless a config change invalidates them.
Hartley is 1,673 loss regions and 13,200 spans; a few abandoned partial
extractions of sources that size are not free, and nothing surfaces them.

**Required:** either an expiry, or `wiki status` reporting partial extractions
so they are visible. Preferably the latter — this project has repeatedly been
bitten by state that nothing reports.

### F6 — The proposal never states what happens on a re-run of a CHANGED source

`compile_source_l2` already handles content changes via `content_hash`. If a
source is edited between attempts, its spans change, so batch keys change, so
the partial is ignored — probably correct. But "probably" is doing work here,
and the interaction with `_recover_published_source` and the
post-publish-projection-pending path is not mentioned at all.

**Required:** say what happens, and pin it.

## 2. Suggested Alternatives

- Keep the shape. Persisting per batch is right, and it answers both v0.52.0
  hazards more convincingly than a checkpoint table would.
- **Measure F2 before anything else.** It is one timing and it decides whether
  the design is cheap or costly.
- Audit F1's readers and publish the list in the plan.
- Make `_config_key` provably cover the prompt (F3).
- Test the conditional discard (F4) and surface partials (F5).
