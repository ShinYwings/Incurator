# Defense: F1 audited, and it changes the proposal

Date: 2026-08-21 | Agent Persona: lead_architect (responding), with schema_guardian

## 1. F1 — the readers, enumerated as demanded

27 reads of `knowledge_units` across the backend. **15 do not filter on
`generation_id`.** Most are harmless; three are not, and the distinction is what
the proposal missed.

**Safe — scoped by primary key.** `claim_support.py:201`, `:560`,
`_entities.py:372` and friends read `WHERE id = ?`. A caller holding a unit id
already knows what it has; an unpublished row cannot wander in.

**Safe — joined to a generation.** `materializer.py:269` joins
`compiler_generations` on `ku.generation_id`, so a NULL simply does not match.
The search corpus cannot see a partial. That is the reader that mattered most
and it is already correct.

**Not safe — table-wide scans keyed only on `retired_at IS NULL`:**

| site | what it does | effect of a partial |
|---|---|---|
| `claim_support.py:490` | `run_compiler_audit` scans every `source_supported` unit and reports "dangling" ones | a half-extracted book reports as audit findings |
| `claim_support.py:520` | groups by `semantic_hash` to find duplicates | units from an abandoned partial become duplicate pairs against the published ones |
| `claim_support.py:645` | per-source scan of statements and hashes | mixes a partial into whatever it is validating |
| `synthesis_audit.py:155`, `:159` | inspection over units | reports on work that was never published |

None of these corrupts stored data. All of them make an in-progress or abandoned
extraction **visible as if it were knowledge**, which is precisely the class of
defect this project has spent four releases removing.

**F1 is upheld.** The proposal said partial rows "would be seen by anything that
does not filter" and left it there; the audit shows five specific surfaces that
would report them.

## 2. What that does to the design

The proposal's premise — reuse `generation_id IS NULL` because it already means
"extracted, not authoritative" — is **wrong in practice.** It means that to five
readers and nothing to five others, because nothing ever forced them to agree:
until now a NULL row existed only inside a single function's transaction and was
gone before anyone could observe it.

Making that state durable makes the disagreement observable. So the design has
to choose:

**Option A — fix the readers.** Add `generation_id IS NOT NULL` to the five
scans. Small diffs, but it puts the correctness of the ingest path in the hands
of every future query anyone writes, with nothing enforcing it.

**Option B — keep partials out of `knowledge_units` entirely.** A separate
staging table, written per batch, drained into `knowledge_units` at publish.
No existing reader can see it because it does not exist to them. But this is
close to what v0.52.0 removed, and its hazards have to be re-answered rather
than assumed away.

**A is smaller; B is safer.** The measured audit is what makes that a real
choice rather than a preference, and it is the decision the Arena now has to
make. I do not think the proposal as written can proceed on A without also
adding something that keeps future readers honest — a helper that is the only
sanctioned way to read published units, or a test that scans for table-wide
reads lacking the filter.

## 3. Still outstanding

F2 (the cost of 277 writes) is unmeasured and blocks acceptance either way.
F3 (`_config_key` not provably covering the prompt), F4 (test the conditional
discard), F5 (no expiry, nothing surfaces partials) and F6 (changed source) are
conceded and unaddressed. They are cheaper than F1 and none of them changes the
shape the way F1 does.
