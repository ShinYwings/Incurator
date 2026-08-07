# Schema Guardian Proposal: The Loss Record Belongs To The Span, And The Existing Recovery-Metadata Write Path Is Not Sync-Safe

Date: 2026-08-08 | Agent Persona: Schema Guardian

## 1. Core Logic & Implementation

### 1.0 Headline finding — `source_spans.metadata` writes are invisible to cross-device sync, today, before any Arena change

Before ruling on Route A/B/C I traced how `recover_formula()` and
`invalidate_formula_recoveries()` (both already shipped, `pipeline/formula_recovery.py:161-176`,
`:240-284`) actually persist. Both do:

```python
conn.execute("UPDATE source_spans SET metadata = ? WHERE id = ?", (...))
```

`source_spans` has no `updated_at` column. Cross-device merge
(`db_sync.py:87`) uses `created_at` as this table's LWW clock:

```python
_UPDATED_AT_COL: dict[str, str] = {
    ...
    "source_spans": "created_at",
    ...
}
```

`created_at` is written exactly once, at INSERT
(`db/_entities.py:159`, inside `upsert_source_span`), and `upsert_source_span`
is create-or-return-existing — it **never** updates an existing row, not even
to apply a `metadata` argument passed on re-parse (`db/_entities.py:130-136`).
So on a table where `metadata` is the *only* column any code path mutates
post-insert, the sync system is watching a clock that is structurally
incapable of ticking for that mutation. Two independent, measured
consequences follow from `_lw_upsert` (`db_sync.py:1362-1371`):

1. **Import silently drops the change.** `existing["created_at"]` and the
   incoming row's `created_at` are the same immutable value on both peers (the
   span was created once, by whichever device parsed it first). The compare is
   `_timestamp_key(remote_ts) > _timestamp_key(local_ts)` — strict `>`. Equal
   timestamps return `"skipped"`. A device that has already seen this span
   (i.e. every device except the one that originally parsed it) will **never**
   accept a peer's `formula_recovery` write for that span, no matter how many
   recovery attempts happen or how much later they occur.
2. **The writing device may not even know it has something to export.**
   `local_has_unexported_changes` → `_local_max_ts` (`db_sync.py:1636-1655,
   1658-1672`) takes `MAX(created_at)` per table. A `recover_formula` call that
   only updates an existing row's `metadata` does not move that MAX. If no
   other synced table changed in the same operation, `maybe_auto_export`
   (`db_sync.py:1675-1687`) — the "default-on export hook for non-CLI mutation
   paths" — will not fire.

I confirmed this is not theoretical: `metadata` is **0/2363** non-null across
every `source_spans` row in the live vault
(`.cache/vaults/13ed51f8b06cb88e/state.sqlite`, 2026-08-08). No production
`recover_formula` call has happened yet, so the defect has never been
observed — but it is already shipped (v0.8.0, Plan B) and any Arena route that
starts writing real data into `metadata.formula_recovery` inherits it
immediately, on day one, silently. **This must be fixed before any proposal
in this Arena persists production data through this column**, independent of
which of Route A/B/C is chosen — §1.6 below gives the exact fix.

Contrast with `knowledge_units`: every mutator (`set_unit_formula_status`,
`set_unit_support_status`, `db/_entities.py:542-580`) explicitly sets
`updated_at = _now_iso()` on every UPDATE, and that table's sync column is
`updated_at` (`db_sync.py:88`) — this table is sync-safe. `compiler_generations`
goes further: it has an actual auto-touch trigger
(`compiler_generations_touch_updated_at`, `schema.py:858-873`) that stamps a
monotonically-increasing `updated_at` on every UPDATE regardless of whether
the caller remembered to set it, using the exact
`julianday(...) + (1.0/86400000.0)` idiom SCHEMA §20.3 requires ("every valid
revision observed... strictly newer"). `source_spans` has no such trigger.
This is the established, working pattern in this codebase for "a row that
gets mutated after insert needs a protected clock" — I am not inventing a
new mechanism in §1.6, I am applying the one already proven for
`compiler_generations` to the one table that was missed.

### 1.1 What exists today — DDL read directly, spec-vs-DDL divergence report

Read from `backend/src/curator/db/schema.py`, not inferred from SCHEMA.md:

```sql
-- schema.py:308-326
CREATE TABLE IF NOT EXISTS source_spans (
    id TEXT PRIMARY KEY, source_id INTEGER NOT NULL, relpath TEXT NOT NULL,
    span_type TEXT NOT NULL, page_number INTEGER, section_title TEXT,
    toc_id TEXT, start_char INTEGER, end_char INTEGER,
    content_hash TEXT NOT NULL, text_preview TEXT NOT NULL DEFAULT '',
    metadata TEXT, created_at TEXT NOT NULL,
    FOREIGN KEY (source_id) REFERENCES sources(id) ON DELETE CASCADE
);
-- schema.py:329-351
CREATE TABLE IF NOT EXISTS knowledge_units (
    id TEXT PRIMARY KEY, unit_type TEXT NOT NULL, canonical_name TEXT NOT NULL,
    statement TEXT NOT NULL, source_span_ids TEXT NOT NULL, source_id INTEGER,
    confidence REAL NOT NULL DEFAULT 0.0,
    truth_status TEXT NOT NULL DEFAULT 'source_supported',
    atom_node_id TEXT, prompt_run_id TEXT, created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    semantic_hash TEXT, support_status TEXT NOT NULL DEFAULT 'unchecked',
    support_reason TEXT NOT NULL DEFAULT '',
    formula_status TEXT NOT NULL DEFAULT 'not_applicable',
    retired_at TEXT, generation_id TEXT
);
```

This matches SCHEMA §20.1/§11.1 in every column name, type, and default. **No
divergence in column shape.** But three things the spec does not surface, all
verified against the live vault and the code:

1. **No CHECK constraints anywhere except `deleted_records.table_name`**
   (`schema.py:729`, `grep CHECK` across the whole file returns exactly one
   hit). `formula_status`, `support_status`, `unit_type`, `truth_status` are
   comment-documented enums, enforced only by Python-side frozensets
   (`FORMULA_STATUSES`, `SUPPORT_STATUSES`, `db/_entities.py:472-473`) inside
   the specific setter functions. A raw `UPDATE` or a migration script that
   bypasses those setters can write an invalid enum value with zero DB-level
   resistance. Any migration I specify below validates values in Python
   before touching SQL for this reason.
2. **No FOREIGN KEY on `claim_supports`, `knowledge_units`, or
   `compiler_generations`.** `PRAGMA foreign_key_list` returns empty for all
   three (measured on the live DB). Only `source_spans.source_id →
   sources(id) ON DELETE CASCADE` is a real FK. This is the established
   convention for the newer Plan-B/C tables — integrity is enforced at the
   application layer (the compiler audit, `claim_support.py:468-544`) rather
   than by SQLite constraints, presumably because JSONL-based sync/tombstone
   reconciliation needs to insert rows out of dependency order across a
   replica boundary that a live FK would reject mid-import. **I am not
   proposing to add FKs to any table this Arena touches — doing so would be
   inconsistent with every sibling table SCHEMA §20 already shipped**, and is
   listed under §1.7 "must not change."
3. **No runtime `ALTER TABLE` migration path exists at all**, for any table,
   as of this commit. `grep -rn "ALTER TABLE"` across
   `backend/src/curator/` returns zero hits. `init_db`/`connect`
   (`schema.py:906-921, 925-944`) both simply run
   `conn.executescript(SCHEMA_SQL)` — which is all `CREATE TABLE
   IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS` and is a **silent no-op
   against a table that already exists**, column additions included. This is
   not an oversight; commit `f8b40be` ("remove v12 migration backward
   compatibility and schema fallback") deliberately deleted the last ALTER-based
   upgrade shim, and CLAUDE.md §"Development Commands" / the SCHEMA.md v0.33.0
   note ("Runtime pre-v12 migration/backfill shims are removed; unsupported
   legacy DBs must be rebuilt or regenerated from a current export") makes
   this the intended policy. **Any new column proposed in this Arena — mine
   included — does not reach the live `second_brain` vault by editing
   `SCHEMA_SQL` alone.** §1.6 addresses this directly: it is the load-bearing
   fact that decides what "migration" can mean here without violating briefing
   constraint 5 (no forced re-ingest).

Measured live values, reproduced independently of the briefing and the RAG
analyst's proposal (`.cache/vaults/13ed51f8b06cb88e/state.sqlite`,
2026-08-08): `formula_status` — `not_applicable` 1564, `preserved_in_text`
669, `uncertain` 480, `missing` 86 (2799 units total). Placeholder spans 130.
Units citing any placeholder span: **0**. `source_spans.metadata` non-null
rows: **0/2363**. `source_spans` has no `updated_at` column and no FK beyond
`source_id`. SQLite build in use: 3.40.1 (server) / 3.53.2 (client bindings)
— both support `ALTER TABLE ... ADD COLUMN` (available since 3.1.3) and
`DROP COLUMN` (available since 3.35.0), which matters for §1.6's reversibility.

### 1.2 Is `formula_status` the right axis for image-only loss? No — it is a claim-level column and the loss is a span-level fact

`formula_status` (§20.1) is defined entirely in terms of a claim's
`statement`: *"the central formula appears intact in `statement`"*,
*"`statement` references an exact formula evidence record"*, *"a central
formula could not be preserved or linked."* Every one of its six frozen
values (`not_applicable | preserved_in_text | linked_evidence |
omitted_incidental | missing | uncertain`) presupposes a `knowledge_units`
row exists to hold the status. For the 130 placeholder spans, no such row
exists — `classify_formula_loss`'s own docstring is explicit that "recovery
is never scheduled from an expected formula alone," and Phase A correctly
declines to fabricate a claim from 51 characters of parser apology
(`knowledge_units.py:49-54`, contract quoted in the peer RAG proposal §1.1:
*"No span, no unit. Never invent a span id that is not in the allowed
list"* — the inverse also holds by construction: no claim without content).

So the honest question is not "which `formula_status` value fits an
image-only region" — none of the six do, because the axis measures a
statement's fidelity and there is no statement. The honest question is
**"what predicate is true of the *span*, independent of whether any claim
ever cites it."** That predicate — "this region's content was not extracted
by the parser" — is exactly what SCHEMA §20.4 already scoped to
`source_spans.metadata`, just not yet populated with a *classification*, only
with a *recovery attempt log* (`formula_recovery[]`, which presupposes a
`knowledge_unit_id` per candidate, `formula_recovery.py:146`). The gap is one
layer up: nothing currently records the span-level fact "this region is
image-only" independent of any recovery attempt or any citing unit.

**Yes, a span-level loss record is needed, and it is a strict prerequisite
for every route in the briefing, not an alternative to any of them:**
Route A needs it to know which spans are recovery targets at all (today
nothing distinguishes an image-only paragraph span from a genuinely-empty
one). Route B needs it to decide which pages are worth an opt-in VLM pass.
Route C needs it verbatim — "record and report that N equations on M pages
are images" **is** a span-level loss record, stated in prose.

**Exact specification, addressing the four things asked (column vs metadata
key, values, index, migration):**

- **Location: `source_spans.metadata`, new reserved key `loss` — not a new
  column, not a new table.** This is consistent with SCHEMA §20.4's own
  stated bar for *this* table: "recovery candidates are NOT normalized into a
  new table unless Plan B measurements prove a multiple-attempt lifecycle or
  indexed audit need." A loss classification is the opposite of a
  multiple-attempt lifecycle — it is written once, from the placeholder's own
  text, and never revised (the placeholder's dimensions do not change
  between reads). §1.6 explains why the *recovery attempts* sub-key (already
  frozen as `formula_recovery`) has a real multi-write lifecycle and needs the
  clock fix, while `loss` does not need one at all.
- **Shape:**
  ```json
  {
    "loss": {
      "verdict": "image_only",              // image_only | fragmented | parser_omitted — reuse LOSS_VERDICTS (formula_recovery.py:25), do not invent a fourth
      "region": {"width": 221, "height": 18, "kind": "equation_band"},  // kind: equation_band | figure | glyph
      "classified_at": "2026-08-08T00:00:00Z"
    }
  }
  ```
  `verdict` reuses the exact `LOSS_VERDICTS` frozenset already frozen in
  `formula_recovery.py:25` and referenced by SCHEMA §20.4 — this is
  deliberate: it means `recover_formula(loss_verdict=...)` can read
  `span.metadata.loss.verdict` directly as its `loss_verdict` argument with no
  translation layer, for any span that becomes recoverable. `region.kind` is
  the RAG analyst's dimension-band triage (`pipeline/source_spans.py`
  proposal, §1.5 P0) — I agree with keeping it deterministic and provider-free,
  and note it is naturally namespaced under `loss.region` rather than a
  competing top-level `omitted_region` key, since it is one field of the loss
  classification, not a separate fact.
- **Values:** `verdict` is a closed enum (3 values, matches `LOSS_VERDICTS`).
  `region.kind` is a closed enum (3 values). Validate both in Python before
  writing, exactly like `FORMULA_STATUSES`/`SUPPORT_STATUSES` are validated —
  per §1.1 finding 1, nothing at the DB layer will catch a typo.
- **Index: none, by measurement.** 2363 total spans, 130 with a placeholder
  body. A `json_extract` predicate in `wiki lint`'s new check
  (`check_image_only_regions`) is a full scan of ≤2363 rows — sub-millisecond,
  not worth a covering index at this corpus size. If a future vault's scale
  makes this measurably slow, the additive, zero-migration-cost option is a
  partial expression index:
  ```sql
  CREATE INDEX IF NOT EXISTS idx_source_spans_loss_verdict
  ON source_spans(json_extract(metadata, '$.loss.verdict'))
  WHERE json_extract(metadata, '$.loss.verdict') IS NOT NULL;
  ```
  I am not shipping this now — SCHEMA §20.4's "unless measurements prove...
  indexed audit need" bar is not met at 130 rows, and an unused index is
  exactly the kind of speculative addition CLAUDE.md's Simplicity First rule
  forbids.
- **Write path for new spans (no migration, no sync exposure):** compute
  `loss` once, inside the same call that builds `SpanRecord`, and pass it into
  the *single* `upsert_source_span` INSERT (`db/_entities.py:112-162`) that
  already runs for every new span. Because this is write-once-at-birth, it
  rides `created_at` exactly the way every other span field already does —
  **no new UPDATE call site, no new sync exposure, no clock problem.** This is
  the common case for every future ingest and it needs nothing from §1.6.
- **Write path for the 130 existing spans: a genuine post-hoc UPDATE**,
  because `upsert_source_span` never updates an existing row
  (`db/_entities.py:130-136`, confirmed above) — this is exactly the case
  §1.6's clock fix exists for, and the backfill in §1.6 sets both the `loss`
  key and the new clock column atomically, in the same UPDATE, so it is
  sync-correct from the moment it lands.

### 1.3 Rejected: synthesizing a `knowledge_units` row for a placeholder span so `recover_formula` has a `unit_id`

The briefing's Route A, read literally ("make image-only loss produce the
`uncertain` unit the pipeline needs"), means minting a `knowledge_units` row
whose only citation is a placeholder span. Walking every consequence:

1. **`statement` has no honest content.** There is no claim in "picture [221 x
   18] intentionally omitted." A synthetic statement is necessarily either (a)
   empty/boilerplate ("this region is an unrecovered image formula") — which
   is not a claim the source asserts, violating the spirit of §18's "no span
   is ever created from derived insight" even though it technically cites a
   real span — or (b) a guess at the equation's content before any recovery
   has run, which is fabrication presented as source-supported truth. Neither
   is acceptable at `truth_status='source_supported'`.
2. **`semantic_hash` collision risk across unrelated sources.** §20.1: "a
   matching `semantic_hash` never auto-merges two claims whose statement...
   differs materially," but reconciliation candidates ARE proposed on a
   match (`run_compiler_audit`'s `duplicate_candidates`,
   `claim_support.py:516-524`, and `_reuse_verified_candidate`). A boilerplate
   synthetic statement ("image-only region, content not extracted") would be
   byte-identical (after whitespace normalization) across many of the 130
   spans, across 4 different sources. Every one of them becomes a
   reconciliation-candidate cluster with every other one — noise injected
   directly into the audit's duplicate-detection signal for something that
   has nothing to do with genuine claim deduplication.
3. **Generation/eligibility violation.** §20.1's eligibility rule requires
   `generation_id` to reference "the same `source_id`" and be
   "authoritative." A unit inserted outside `extract_knowledge_units`
   (Phase A) has no real `compiler_generations` row backing it unless one is
   fabricated too — and fabricating a `compiler_generations` row breaks
   §20.3's audit contract in the other direction: `audit_json` is supposed to
   contain "the exact sorted `authored_relation_ids` owned by the
   generation," and unchanged-rebuild idempotency (§20.3) requires that
   recompiling the source reproduces "the existing authoritative generation's
   claim ids, hashes, dependency closure, and counts" — a synthetic unit was
   never produced by that reproducible process, so every future rebuild's
   idempotency check has a permanent, unexplained discrepancy it can never
   resolve by re-running the compiler.
4. **`reconcile_source` turns it into a permanent zombie, not a fixable
   row.** Read `pipeline/claim_support.py:606-634`: "A prior unit whose span
   basis is UNCHANGED and which no candidate cites (an LLM omission, not an
   edit) is carried forward... so it keeps its id and survives the publish
   gate." A synthetic unit is indistinguishable, to this logic, from a
   legitimate claim the LLM silently stopped extracting on a later pass — it
   is UNCHANGED-span, uncited-by-any-fresh-candidate, so it is carried
   forward **forever**, on every future `wiki add`/rebuild of that source,
   with no code path that ever retires it. This is the opposite of the
   tombstone-style audit trail §20.1 designs for legitimately-retired rows —
   it is a row the system can never distinguish from real content again.
5. **Search/embedding pollution.** If the synthetic unit is ever promoted to
   `support_status='verified'` (required for it to reach an ATM page or the
   search index at all, per the eligibility rule), its boilerplate statement
   gets embedded and indexed exactly like a real claim
   (`retrieval/materializer.py`), competing for ranking slots on unrelated
   queries about "image" or "formula" — the same "index pollution" the RAG
   analyst's proposal correctly flags for the *span* documents (§1.4 of their
   proposal) is reproduced at the *unit* layer, except now duplicated across
   every placeholder-bearing source, worse because units are supposed to be
   the trustworthy, LLM-vetted layer.
6. **`wiki lint` orphan detection gets worse, not better.** `check_orphan_pages`
   (`lint.py:419-450`) flags any ATM/CON/SYN page nothing links to. A
   synthetic unit's ATM page has no organic reason for Phase B to group it
   into any CON- concept (it shares no theme with real content), so it very
   likely surfaces as a *new* orphan-page lint failure. The briefing's §2.4
   complaint — "nothing tells the user" — would be answered by converting 158
   silent losses into 158 *noisy, indistinguishable-from-a-real-defect* lint
   failures, which is a regression in signal quality, not a fix.
7. **DAG edge tables** (`dag_edges`) connect CTX/ATM/CON/SYN pages; nothing
   naturally produces an edge into a synthetic ATM page, so it is also an
   orphan in the literal DAG sense, independent of the lint check.

**Verdict: reject synthesizing a `knowledge_units` row outright, for any
route.** This is not a schema tweak that could make it safe — the row would
be lying about what kind of thing it is (a claim vs. a note about a parsing
failure) at every layer that reads `knowledge_units`, and §20's entire
contract (generation eligibility, reconciliation, semantic-hash dedup, audit
idempotency) is built on the assumption that every row in this table is
real, LLM-extracted content. The RAG analyst's proposal reaches the same
conclusion independently (their §1.3, "Rejected") — I confirm it from the
integrity side with the five additional consequences above (2, 3, 4, 6, 7)
their RAG-pipeline framing did not need to trace.

### 1.4 Ruling on the peer proposal's alternative: amending an existing unit's `source_span_ids` in place

The RAG analyst's `01_proposal_rag_analyst.md` avoids §1.3's fiction by a
different route: for the ~33% of `uncertain` units adjacent to a placeholder
span (159/480 vault-wide, measured independently and confirmed by me against
the same DB), add the placeholder span to that *existing, real* unit's
`source_span_ids`, then call `recover_formula` unmodified. Their own Con #3
flags this as unresolved and explicitly asks schema_guardian to rule on it.
Ruling:

**The monotone-safety proof (their §1.3, citing `claim_support.py:334-354`'s
`max()`/`union()` structure) is correct as far as it goes — it proves a
single amendment cannot flip `verified→failed`.** But it does not address
*durability across re-ingestion*, which is the actual integrity question for
a mutation applied "outside a new `compiler_generation`" (their own words).

Trace what happens on the **next** `wiki add`/`wiki sync` of that source, per
`reconcile_source` (`claim_support.py:606-634`, quoted in §1.3.4 above): Phase
A re-extracts fresh candidates independently of whatever citations a prior
row currently holds. A fresh candidate whose statement matches the existing
unit's statement (same claim, re-extracted) is treated as either (a) a
semantic-hash match reused onto the stable id — and per the docstring "the
candidate's data — incl. generation — is copied onto the stable id" — **the
candidate's own `source_span_ids` overwrite the stable row's**, silently
reverting the hand-added placeholder citation back to just the original prose
span, because Phase A never re-derives the adjacency pairing on its own; or
(b) treated as an unchanged-span "LLM omission" carry-forward, which
preserves the *existing* stored `source_span_ids` (including the manual
addition) only because reconciliation happens to not touch it — a
coincidence of the current code path, not a guarantee, and the peer
proposal's own P1.5 P2 code does not integrate with `reconcile_source` at all
to make this reliable either way.

**This is a real, unresolved durability gap, not a hypothetical.** My ruling:
citation-surface mutation on a published, potentially-multi-generation unit
must not be treated as a one-time hand-edit. Either:

- (a) it is re-derived and re-applied **idempotently after every
  reconcile/publish** of that source (the locator function they already
  specify, `locate_image_only_loss`, is pure and deterministic — it can
  safely be re-run and re-applied as a fixed post-publish step inside the
  same transaction as `reconcile_source`, so it self-heals every rebuild
  instead of surviving by accident), or
- (b) the citation amendment is dropped as a *requirement* and treated as a
  ranking/labelling enhancement only — because, per §1.2's write path above,
  the span itself is independently searchable (RAG analyst's own Fact 1: "the
  span layer IS indexed, with no admission gate," `materializer.py:221-228`)
  the moment `metadata.loss` exists on it. Tier-1 honesty and even much of
  Tier-2 semantic answerability do not require touching `knowledge_units` at
  all — only calling `recover_formula()`'s specific `unit_id`-keyed API does.

**I recommend (b) as the schema-integrity-preferred default and (a) only if
the Arena decides `recover_formula`'s exact existing signature must be
reachable for the adjacent-claim population.** The span stays the single
source of truth for "is this region lossy" and "was it recovered"; the unit
citation becomes an optional, re-derivable enrichment rather than a load-
bearing one-time mutation. This keeps the durability surface to exactly one
table (`source_spans`, whose clock §1.6 now fixes) instead of two.

### 1.5 Recommended schema shape, restated as one artifact

```json
// source_spans.metadata — additive, both keys optional, never removes
// text_preview/content_hash (raw parser text stays immutable per §20.4)
{
  "loss": {                                    // NEW — write-once classification
    "verdict": "image_only",
    "region": {"width": 221, "height": 18, "kind": "equation_band"},
    "classified_at": "2026-08-08T00:00:00Z"
  },
  "formula_recovery": [ /* unchanged shape, SCHEMA §20.4 */ ]
}
```

`loss` and `formula_recovery` are independent, both under `metadata`, neither
touches the other. A span can carry `loss` with an empty
`formula_recovery: []` (classified, not yet attempted) — this is in fact the
state all 130 existing spans should be in immediately after the §1.6
backfill, before any recovery driver runs.

### 1.6 Exact migration — SQL, behavior on existing rows, reversibility

Per §1.1 finding 3, `SCHEMA_SQL`'s `CREATE TABLE IF NOT EXISTS` cannot deliver
a new column to the live vault's already-existing `source_spans` table. Given
briefing constraint 5 (no plan may silently imply a full re-ingest — and
`wiki reset` is exactly that: every source's Phase A/B/C reruns, not just the
4 sources with placeholder spans), I am proposing a **narrow, explicit
reintroduction of exactly one guarded `ALTER TABLE`**, scoped to one column
on one table, following the same idempotent self-check idiom the codebase
already uses for trigger refresh (`_triggers_need_refresh`/
`_refresh_current_triggers`, `schema.py:825-904`, called from both `init_db`
and every `connect()`). This is a deliberate, narrow exception to the policy
`f8b40be` set, not a reversal of it — the alternative is forcing every
existing vault through a full rebuild for a one-column addition, which is
strictly worse than the "shim" the policy removed.

**Step 1 — add the column to `SCHEMA_SQL` (fresh installs get it for free)
and the guarded ALTER for existing installs:**

```sql
-- schema.py: add to the existing source_spans CREATE TABLE block
    metadata        TEXT,                    -- JSON
    metadata_updated_at TEXT,                -- NEW: LWW clock for metadata mutations
    created_at      TEXT NOT NULL,
```

```python
# schema.py — new helper, called from both init_db() and connect(),
# same place _refresh_current_triggers() already runs.
def _ensure_source_spans_metadata_clock(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(source_spans)")}
    if "metadata_updated_at" in cols:
        return
    conn.execute("ALTER TABLE source_spans ADD COLUMN metadata_updated_at TEXT")
    # Baseline: rows with no post-insert metadata mutation are, by definition,
    # in sync with their own creation moment. This does not fabricate history —
    # metadata is 0/2363 non-null on the live vault (measured), so every
    # existing row genuinely has never been touched after insert.
    conn.execute(
        "UPDATE source_spans SET metadata_updated_at = created_at "
        "WHERE metadata_updated_at IS NULL"
    )
```

**Step 2 — auto-touch trigger, mirroring `compiler_generations_touch_updated_at`
verbatim (`schema.py:858-873`) so existing call sites in `formula_recovery.py`
need ZERO changes:**

```sql
DROP TRIGGER IF EXISTS source_spans_touch_metadata_updated_at;
CREATE TRIGGER source_spans_touch_metadata_updated_at
AFTER UPDATE OF metadata ON source_spans
FOR EACH ROW
WHEN NEW.metadata IS NOT OLD.metadata
BEGIN
    UPDATE source_spans
    SET metadata_updated_at = CASE
        WHEN strftime('%Y-%m-%dT%H:%M:%fZ', 'now') > COALESCE(OLD.metadata_updated_at, OLD.created_at)
        THEN strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
        ELSE strftime(
            '%Y-%m-%dT%H:%M:%fZ',
            julianday(COALESCE(OLD.metadata_updated_at, OLD.created_at)) + (1.0 / 86400000.0)
        )
    END
    WHERE id = NEW.id;
END;
```

Registered in `_refresh_current_triggers`/`_triggers_need_refresh` alongside
the two existing triggers, same file, same pattern.

**Step 3 — `db_sync.py`, one line:**

```python
_UPDATED_AT_COL["source_spans"] = "metadata_updated_at"   # was "created_at"
```

**Step 4 — `SCHEMA_VERSION` 13 → 14**, per the precedent §20.3.1 already set
for v13: "mixed-version peers must upgrade and re-export rather than
partially applying a snapshot." State the same sentence for v14 in SCHEMA.md
§20.4's revision. A peer still on v13 exports `source_spans` rows without
`metadata_updated_at` at all (its `SELECT *` never had the column); importing
that into a v14 DB hits `_lw_upsert`'s `updated_col` branch with
`row.get(updated_col)` → `None` → `_timestamp_key(None)` → `datetime.min` —
which always loses to any real local timestamp, so a stale v13 peer's export
can never clobber a v14 peer's recovery data. This is the correct fail-safe
direction and needs no special-case code.

**Step 5 — one-shot backfill of the 130 existing placeholder spans,
`loss` key + real clock together, atomically per row (Python, not raw SQL —
dimension parsing from `text_preview` is not portably expressible in SQLite
string functions):**

```python
# one-shot, run once from a migration entry point (e.g. `wiki db migrate`
# or folded into the same call site that runs step 1/2), NOT on every connect()
_PICTURE_OMITTED = re.compile(
    r"picture\s*\[(\d+)\s*x\s*(\d+)\]\s*intentionally omitted", re.IGNORECASE
)

def backfill_span_loss_classification(db_path: Path) -> int:
    now = _now_iso()
    updated = 0
    with db.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, text_preview, metadata FROM source_spans "
            "WHERE text_preview LIKE '%intentionally omitted%'"
        ).fetchall()
        for row in rows:
            meta = json.loads(row["metadata"] or "{}")
            if "loss" in meta:
                continue  # idempotent: already classified
            m = _PICTURE_OMITTED.search(row["text_preview"])
            if not m:
                continue
            w, h = int(m.group(1)), int(m.group(2))
            kind = "glyph" if w * h < 2000 else ("equation_band" if w >= 3 * h else "figure")
            meta["loss"] = {
                "verdict": "image_only",
                "region": {"width": w, "height": h, "kind": kind},
                "classified_at": now,
            }
            conn.execute(
                "UPDATE source_spans SET metadata = ?, metadata_updated_at = ? WHERE id = ?",
                (json.dumps(meta, ensure_ascii=False, sort_keys=True), now, row["id"]),
            )
            updated += 1
    return updated
```

`metadata_updated_at = now` here (not `created_at`) is deliberate and the
opposite of Step 1's baseline: Step 1 backdates rows that have genuinely never
changed; Step 5 is a real, present-tense metadata mutation, so it must stamp
the real moment it happens, or the very first legitimate write into this
column would itself be sync-invisible — repeating §1.0's bug on migration
day one.

**Behavior on a vault with existing rows:** no span id changes (content
untouched, `content_hash` untouched — `hydrate_span_text`'s hash
verification, `compile.py:221-225`, is unaffected). No `knowledge_units` row
is touched. No re-parse, no file access, no Zotero resolution, no LLM call,
no Phase A/B/C rerun — same cost profile the RAG analyst measured for their
P0b (their §1.5). This directly answers briefing §5's "what happens to the
130 already-ingested placeholder spans": they gain a `loss` classification
and a working sync clock, in one pass, in milliseconds, with zero re-ingest
cost — constraint 5 is satisfied by construction, not by argument.

**Reversibility:**

- The `loss` key: strictly additive per span; remove with
  `UPDATE source_spans SET metadata = json_remove(metadata, '$.loss') WHERE json_extract(metadata,'$.loss') IS NOT NULL;`
- The column and trigger: `DROP TRIGGER IF EXISTS
  source_spans_touch_metadata_updated_at; ALTER TABLE source_spans DROP
  COLUMN metadata_updated_at;` — supported on the deployed SQLite (3.35+
  required; measured 3.40.1/3.53.2 on this machine, both sufficient). Revert
  `_UPDATED_AT_COL["source_spans"]` to `"created_at"` and `SCHEMA_VERSION` to
  13.
- **One-way-door caveat, stated honestly:** rollback is clean only *before*
  any cross-device export/import has exchanged `source_spans` rows keyed by
  the new clock. Once a peer has merged data using `metadata_updated_at`,
  reverting the column on one device reintroduces exactly the §1.0 defect for
  that device's future writes while peers move on with the new clock — so
  this is safe to roll back in local development or before the first release
  that ships it, and is a one-way decision after that, same as any other
  `SCHEMA_VERSION` bump in this project's stated no-shim policy.

### 1.7 What MUST NOT change

- **`formula_status`'s six-value frozen enum stays exactly as SCHEMA §20.1
  defines it.** No seventh value for "no claim exists." It remains
  exclusively a claim-level column; the span-level fact lives in
  `metadata.loss`, a different axis entirely, per §1.2.
- **No `knowledge_units` row is ever synthesized from a placeholder span.**
  §1.3's rejection is unconditional, independent of which route the Arena
  picks.
- **`content_hash` and `text_preview` remain immutable.** Neither the `loss`
  classification nor any recovery candidate ever rewrites raw span text —
  SCHEMA §20.4's existing invariant, reaffirmed, not relaxed.
- **`recover_formula()`'s and `invalidate_formula_recoveries()`'s existing
  signatures, preconditions, and acceptance contract (0.80 threshold,
  validator trace, exact token match, `page_hash` invalidation) are
  unmodified.** §1.6's fix is entirely underneath them — every existing call
  site keeps compiling and behaving identically; only the sync clock they
  silently depend on gets corrected.
- **No FOREIGN KEY constraints added to `claim_supports`,
  `compiler_generations`, or `knowledge_units`.** Per §1.1 finding 2, this
  would be inconsistent with every sibling Plan-B/C table and is out of scope
  for a formula-recovery fix.
- **`source_spans.created_at` keeps its existing meaning** (row-arrival
  ordering, first-seen time) and is never repurposed as a mutation clock —
  `metadata_updated_at` is a new, separate column precisely so `created_at`'s
  existing readers (e.g. the revision-watermark computation in
  `db/sources.py:246-263`) are not disturbed.
- **No dedicated index ships with this migration** (§1.2) — not proven
  necessary at 2363 rows.
- **The `loss` backfill never touches `formula_status`, `support_status`, or
  any `knowledge_units` column.** It is a pure, single-table,
  `source_spans`-scoped write.

## 2. Pros & Cons

### Pros

1. **Fixes a real, already-shipped defect that every route in this Arena
   would otherwise inherit silently.** §1.0 is not a consequence of any
   Arena decision — it exists in `formula_recovery.py` today, unexercised
   only because production has zero recovery attempts yet. Any plan that
   starts writing to `metadata.formula_recovery` without this fix ships a
   fourth silent failure: recovery would work locally and vanish on the next
   sync, which is strictly worse than the current honest "cannot retrieve"
   answer, because it would look successful on the writing device.
2. **Resolves the "is `formula_status` the right axis" question with a
   concrete, minimal-footprint answer**: no, and the fix does not touch that
   enum or that table — it adds one small, independent JSON key to a column
   that already exists, with a write-once path for all future ingests and a
   cheap, one-shot, zero-re-ingest backfill for the 130 legacy spans.
3. **The migration is real, tested against actual DDL and actual policy**,
   not assumed: I found and worked around the fact that this codebase has no
   live `ALTER TABLE` path at all (`f8b40be`), which every prior schema
   change since v12 has quietly depended on vaults being rebuilt through.
   Missing this would have produced a plan that "works" against a fresh test
   vault and silently no-ops against `second_brain`.
4. **Independently confirms the RAG analyst's Route-A rejection of a
   synthetic unit, and adds a ruling on their alternative** (in-place
   citation amendment) that they explicitly left open — the durability gap in
   `reconcile_source` is real and needs either idempotent re-application or,
   my preferred default, no requirement to touch `knowledge_units.source_span_ids`
   at all.
5. **All changes are additive and reversible** within a stated, honest
   caveat window, consistent with SCHEMA §20.4's "raw parser/source span text
   is immutable" and the project's stated Git-history-over-archived-shims
   philosophy.

### Cons & Limitations

1. **Reopens a deliberately closed door.** `f8b40be` removed runtime
   migration shims as a matter of policy; §1.6 reintroduces one, narrowly. If
   the Arena or the user considers that door permanently closed rather than
   "closed pending a case that justifies reopening it," the only remaining
   option is folding this into a `wiki reset`-class rebuild, which directly
   collides with briefing constraint 5's re-ingest-cost prohibition. This
   tension is not fully resolvable by schema design alone — it is a policy
   call the master plan must make explicitly, not silently.
2. **The clock fix does not, by itself, make anything queryable or
   answerable.** It only makes future `metadata` writes sync-correct. It does
   nothing for the retrieval-side gap the RAG analyst's §1.3/§1.4 trace in
   detail (recovered LaTeX not reaching `search_documents.body`) — that work
   is unchanged by this proposal and still required for either Tier of the
   briefing's definition of done.
3. **`region.kind`'s pixel-dimension triage is inherited, not independently
   re-derived, from the RAG analyst's proposal** — I did not re-verify their
   48/54/28 equation-band/figure/glyph split independently; I only confirmed
   the column/key placement and clock safety around it. A red-teamer should
   still attack the triage heuristic itself, which is unchanged by anything
   here.
4. **The trigger-based auto-touch (`WHEN NEW.metadata IS NOT OLD.metadata`)
   fires on *any* metadata UPDATE, including ones that should arguably not
   count as "new information" — e.g., a future idempotent re-write of an
   already-identical `loss` block.** This mirrors `compiler_generations`'s
   existing trigger exactly (same risk already accepted there), but it means
   a careless caller that re-UPDATEs unchanged JSON still burns a clock tick
   and a sync-export cycle. Cheap, but worth naming.
5. **Does not resolve the `rowid`-as-document-order fragility** the RAG
   analyst flags in their own Con #1 (needed for the adjacency locator, not
   for anything in this proposal) — out of scope for schema_guardian, noted
   only so the master plan does not assume it is covered here.
