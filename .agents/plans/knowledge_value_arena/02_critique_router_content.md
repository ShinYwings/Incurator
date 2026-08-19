# Critique: `router_and_layers` + `content_quality` proposals

Red-teamer pass. Read-only throughout — DB via `file:<path>?mode=ro` (sqlite3
CLI and one-off read-only Python scripts against the live cache DB at
`.cache/vaults/13ed51f8b06cb88e/state.sqlite`, the same file both proposals
used, cross-checked against `wiki status`'s live counts). One additional
read-path call was made beyond the two proposals' own sanctioned calls: a
fresh `wiki plugin context fetch --query <Q1 text>` run from
`/Users/shin/shinywings/second_brain` to test the embedder/reranker confound,
and one direct `ContextService.context_fetch(mode="global")` call re-running
the router proposal's own Q3 forced-route test. Both write only the same
`query_traces` instrumentation row the briefing already sanctions for
`wiki plugin context fetch`-class calls. Two scratch files
(`out.json`/`err.log`) were briefly written under the vault root by the first
call and deleted before this file was written — the vault contains no
extraneous files as a result of this review.

---

## 1. CONTENT F2 — "ranking failure, not thin content" (Q1 duplicate-KU claim)

**Verdict: CONFIRMED (severity P1 unchanged) — but the root-cause diagnosis is
WRONG. Two of the proposal's own supporting sub-claims are REFUTED by direct
evidence. This is the most important correction in this critique because it
changes the fix from "improve ranking" to "wire up an already-built,
already-tested, dead pipeline stage."**

### 1a. The core empirical claim — independently re-verified, holds

I queried the four KU ids directly:

```
KNU-e9ec6538, KNU-013768ee, KNU-3702df54, KNU-279bc9a6
  unit_type=equation, confidence=1.0, source_id=34, retired_at=NULL (all live)
  statement (all four, near-identical): "A dual quadric Q* is parametrized as
    Q* = Z Q̆* Z^T where Q̆* is an ellipsoid centred at the origin and Z is a
    homogeneous transformation accounting for rotation and translation."
  source_span_ids: ["SPAN-6259d5a6","SPAN-be04bc31"] (all four)
```

`grep -c` on `q1.json` for all four KU ids and both span ids: **0** — confirmed
absent from the pack, independently reproduced. This part of the finding
survives.

### 1b. REFUTED sub-claim — "fully indexed and embedded"

The proposal states these four KUs are "fully indexed and embedded" and calls
this "not an indexing gap." I checked `search_documents` directly:

```sql
SELECT doc_id FROM search_documents
WHERE record_id IN ('KNU-e9ec6538','KNU-013768ee','KNU-3702df54','KNU-279bc9a6');
-- 0 rows
```

**Zero rows.** These four KUs have no `search_documents` row, hence no
`search_chunks` row, hence no `search_embeddings` row. They are not indexed
and not embedded. `search_embeddings` having 5,635 rows (true, and I
confirmed it independently) says nothing about *these four rows specifically*
— it is a vault-wide count, not evidence about this KU family.

**Root cause, traced to the exact SQL gate.** `materialize_search_documents()`
(`backend/src/curator/retrieval/materializer.py:231-241`) builds the
`knowledge_unit` search corpus from:

```sql
SELECT ku.* FROM knowledge_units ku
JOIN compiler_generations g ON g.id = ku.generation_id
JOIN sources s ON s.id = ku.source_id AND s.id = g.source_id
WHERE ku.retired_at IS NULL AND ku.support_status = 'verified'
AND g.status = 'authoritative'
ORDER BY ku.source_id, ku.id
```

All four KUs have `support_status = 'unchecked'` (verified directly). They
fail this WHERE clause and are never materialized into `search_documents` —
structurally, at the indexing layer, before any ranking ever runs. No
`graph_entity` links to them either (`knowledge_unit_ids LIKE '%<id>%'` → 0
rows, independently reconfirmed), so the entity-evidence path can't surface
them either. **These four KUs are unreachable by every retrieval path in the
system, unconditionally, regardless of ranking quality** — a stronger and more
precise claim than "ranking chose 39 other items instead," which implies they
were candidates that lost a competition. They were never candidates.

**Why `support_status='unchecked'` — this is not a fluke, it's the designed
verdict for a whole class of PDF-sourced formula claims.**
`validate_claim_support()` (`backend/src/curator/pipeline/claim_support.py:290-429`)
requires a claim's LaTeX formula to be a structural token-subsequence of some
`$...$`/`$$...$$`-delimited formula *in the cited span text*
(`SYSTEM_BEHAVIOR.md:2160-2169`, the deterministic "formula structural rule").
I read the actual span text:

```
SPAN-6259d5a6: "where **Q**[˘] _[∗]_ is an ellipsoid centred at the origin, ..."
SPAN-be04bc31: "... error Q∗= Z ˘Q∗ZT where ˘Q∗is an ellipsoid centred ..."
```

This is raw PDF-extracted prose with mangled Unicode math glyphs (`Q∗`, `˘Q∗`)
and **no `$`/`$$` delimiters at all**. `_extract_latex()` finds zero formulas
in either span, so `span_formulas` is empty, so `formula_ok` is `False` for a
claim that has a formula — which routes the verdict to exactly
`"uncertain"` / `"central formula not structurally present in the cited span
(possible parse loss or alteration)"` (`claim_support.py:379-384`). Confirmed
directly: all four KUs have `formula_status='uncertain'`,
`support_status='unchecked'`, `support_reason=''` (empty — never even escalated
to the "ambiguous... escalate to calibrated model" branch's reason string,
consistent with `client=None` at both call sites, see below).

**The system already has a designed fix for exactly this case, and it is dead
code in production.** `SYSTEM_BEHAVIOR.md §26.2` ("Formula Lifecycle And
Selective Recovery", lines ~2203-2250) describes "P5 selective recovery":
re-render the source page, VLM-extract the formula, append it to
`source_spans.metadata.formula_recovery` as a properly delimited `$...$`
string, then re-validate. This is fully implemented —
`classify_formula_loss()` (`formula_recovery.py:36`) and `recover_formula()`
(`formula_recovery.py:73`) — and exercised only by
`test_plan_b_formula_recovery.py`. I grepped every production call site:

```
$ grep -rn "recover_formula(" backend/src/curator --include="*.py"
formula_recovery.py:73:def recover_formula(       # the definition itself
```

**No other file calls it.** `compile.py` imports and re-exports both
functions (`compile.py:44-56`, in `__all__`) but never invokes them.
`claim_support.py:251` references `recover_formula` only in a docstring. There
is no CLI command, no MCP tool, no pipeline stage, no job-queue entry that
calls it. It is reachable only from tests. Confirmed the span metadata is
empty (`SELECT metadata FROM source_spans WHERE id IN (...)` → both blank),
consistent with recovery never having run.

This is not a one-off: vault-wide, **480 knowledge units** carry
`formula_status='uncertain' AND support_status='unchecked'` — the exact
signature of "formula present in claim, absent-as-delimited-LaTeX in span,
recovery never ran." Of 2,799 live (non-retired) knowledge units, only 1,098
(39%) are `support_status='verified'` and therefore searchable at all; 1,701
(61%) are permanently invisible to every retrieval path regardless of
embedder/reranker/ranking quality, because they never clear the materializer's
WHERE clause.

**Corrected framing:** this is not "ranking chose worse candidates." It is
"the indexing pipeline's claim-verification gate is doing its job exactly as
designed — reject formula claims it cannot structurally confirm — but the
recovery mechanism that exists specifically to promote correct-but-unconfirmed
PDF-formula claims out of that state was built, tested, and never wired into
any production entry point." The user-facing symptom (0/39 items) is real and
P1; the mechanism the proposal names is not.

### 1c. The CRITICAL CONFOUND — tested directly, resolves one way, but doesn't rescue F2's framing

I re-ran the exact Q1 query live: `cd /Users/shin/shinywings/second_brain &&
wiki plugin context fetch --query "ellipsoid 형태의 quadric 은 어떻게
매트릭스로 표현되나?"`. Result: `warnings: []`, `coverage.sufficiency:
"sufficient"` (not `"partial"`), and the 8 `search_hit` items now carry real
reranked scores (0.80–0.94) instead of the stale pack's RRF-tail 0.015–0.025.

**So yes — the stale `q1.json`–`q4.json` packs' "vector_unavailable: no
embedder configured (FTS5-only)" / "no reranker configured" warnings are a
snapshot-time artifact, not a structural property of `wiki plugin context
fetch`.** `wiki status` confirms the vault's actual live config: `Embedding
llama-cpp::qwen3-embedding-0.6b`, `Reranking on`. `search.query()`
(`search.py:224-242`) always calls `providers.build_embedder()` /
`build_reranker()` fresh per call from the machine-local global config
(`.cache/config/config.yml`, which has both model paths set and both GGUF
files present on disk, ~639MB each) — there is no separate degraded code path
for `wiki plugin context fetch` specifically. **This means
`content_quality`'s Finding 3 ("`sufficient` is structurally unreachable...
until the session wires up an embedder and a reranker") is REFUTED by a live
counter-example** — the session already has both wired up; the stale packs
just predate or otherwise don't reflect that live state, and this file does
not determine why (transient state at generation time, not a code defect).

**But — this is the crux the task asked me to settle — running the fully
configured engine did NOT surface the Q1 formula either.** I re-checked the
fresh pack for all four KU ids and both span ids: **0 hits, identical to the
stale pack.** This proves conclusively that the embedder/reranker confound is
a red herring *for F2 specifically*: fixing it changes item scores and flips
`sufficiency` from `partial` to `sufficient`, but does not and cannot surface
content that was never indexed in the first place (§1b). The two proposals'
warnings about a config gap and the actual unreachability of this specific
fact are two independent problems that happen to co-occur in the same stale
packs; conflating them (as `content_quality`'s "not an indexing gap" framing
does) obscures the real, fixable defect.

**Verdict: CONFIRMED, P1, but retitle the finding "verified formula claims
never reach the search corpus because the claim-verification/formula-recovery
pipeline stage that would promote them was never wired into production" —
not "ranking failure." Fix direction: invoke `recover_formula`/
`classify_formula_loss` from the compile pipeline (or a `wiki` maintenance
command) for `formula_status='uncertain'` units, not from `local`'s
scoring/ranking code, which was never the broken part.**

---

## 2. ROUTER "(c) weighted to (b)": give `local` a bounded L3/L4 primer

**Verdict: DOWNGRADED. The recommendation is real and directionally sound for
genuinely broad/synthesis-shaped questions, but the proposal overclaims it
"fixes Q1, Q2, Q3, and Q4 simultaneously." For Q1 specifically — the
proposal's own flagship counter-example, shared with `content_quality`'s F2 —
I can show directly that an L3/L4 primer would NOT have surfaced the answer,
because the fact isn't in L3/L4 either, for the identical upstream reason
(§1b). The recommendation needs to be split by question type, not applied as
one uniform fix.**

### 2a. Counter-case for Q1/Q2: would the L3/L4 layer even have had the answer?

I searched `community_reports` for anything covering the specific "dual
quadric parametrized as Q* = Z Q̆* Z^T" fact. Thirteen quadric-related reports
exist. The single most topically adjacent one is:

```
REP-de8f745f "Constrained Dual Quadrics and Spheres in SLAM"
"This community focuses on constrained dual quadrics used for modeling object
landmarks in SLAM applications. These quadrics are mathematically constrained
to represent closed 3D surfaces such as spheres and ellipsoids. The available
evidence for this community is thin, consisting of a single direct relation
between dual quadrics and sphere landmarks."
```

It names the right topic (constrained dual quadrics, ellipsoids, SLAM
landmarks) and explicitly flags itself as evidence-thin — it does not contain
the formula. I grepped every report's `summary` for the formula's
distinguishing phrase (`"centred at the origin"`) and for `"homogeneous
transformation"`: **zero matches across all 233 live reports.** This is the
same root cause as §1b: `KNU-e9ec6538`'s family is never entity-linked, so it
can never enter a community — reports are built over
entities/relations/communities, and this claim was excluded from that graph
before reports were ever generated. **A bounded 3-report primer, however
chosen, cannot contain a fact that exists in zero of the 233 candidate
reports.** Fixing routing, fixing `local`'s contract, or adding a primer are
all no-ops for Q1. Only fixing the upstream verification/graph-linkage gap
(§1b) fixes Q1.

This generalizes beyond this one example: entity/fact questions
(Q1: "how is X expressed as a matrix", Q2: "what are Kruppa's constraints")
by nature ask for a specific number, formula, or named difference — exactly
the granularity community reports (thematic, multi-entity summaries) are
least likely to preserve verbatim, and exactly the granularity that gets
lost when a precise claim fails claim-support verification and never reaches
the graph. Broad "why"/synthesis questions are the opposite case (§2b).

### 2b. Counter-case for Q3: does the L3/L4 layer already have a good answer?

Unlike Q1, I checked and it does. `SYN-95144d37` ("Surface Resampling and
Prior Constraints for Accurate Geometry and Relighting in Radiance Fields") —
one of only 4 live synthesis nodes, and one of the items the router
proposal's own forced-route test actually returned for Q3 (§3 below) — reads:

```
"Transitioning from 3D volume rendering paradigms to 2D surface resampling
and incorporating explicit depth/normal priors bridge the gap between
photo-realistic radiance field synthesis and accurate surface mesh
extraction."
```

This is a genuine, on-topic, already-synthesized answer to "why is 2D GS
better than 3D for surface reconstruction" — not the specific
covariance-matrix-vs-transformation-matrix mechanistic detail
`content_quality`'s Finding 2 separately flags as missing, but a real,
citable "why" a competent agent could ground an answer in. **For Q3, an
L3/L4 primer (or routing to `global`) would have materially helped** — this
part of the router proposal's recommendation holds.

### 2c. Does vector+reranking alone (no primer, no routing change) find Q1's answer via plain `local`?

Tested directly per the task's request (§1c): yes, I ran `local` with a fully
configured embedder+reranker (the live vault state) and it still returned 0
hits for the formula, because the fact was never indexed (§1b), independent
of route or ranking quality. **So the counter-case the task asked me to
argue — "would enabling vector search alone have found it anyway, making the
contract change unnecessary" — resolves to: neither vector search alone
NOR a primer/route change would have found it; only a fix at the
claim-verification layer does.** This means Router's Finding 3 correctly
diagnoses that fixing the language gate alone (Test A) doesn't help Q1/Q2,
but incorrectly concludes the fix therefore must be "(b) give local a
primer" — the correct conclusion for Q1/Q2 is "the primer wouldn't help
either; the defect is upstream of both routing and evidence composition."

**Revised recommendation:** split the fix by question shape, matching what
was actually measured:
- Q1/Q2-class (entity/fact, specific-value questions): the fix is §1b
  (wire up formula recovery / claim verification), not routing or evidence
  composition. No router or evidence-composition change reaches a fact that
  was never verified into the graph.
- Q3/Q4-class (broad "why"/cross-source synthesis questions): the router
  proposal's Test B (regex too narrow even in translated English) and the
  `local`-primer recommendation are both well-supported and independently
  reproduced (§3). Keep this half of the recommendation.

---

## 3. Forced-route experiment (Q3, `mode="global"`) — re-run independently

**Verdict: CONFIRMED, reproduced exactly.**

```python
req = QueryRequest(
    question="2D GS가 3D보다 표면 재구성에 유리한 이유를 여러 논문을 종합해서 설명해줘",
    workspace_path="", mode="global",
)
ContextService(paths, client=None).context_fetch(req)
```
Result (my run, `.venv` python, live vault):
```
route: global | explicit --mode
coverage: {'sufficiency': 'partial', 'omitted_counts': {'global_reports': 223}}
num items: 14
community_report_ids count: 10
synthesis_node_ids count: 4
warnings: []
kinds: {'synthesis': 4, 'community_report': 10}
```
Matches the proposal's reported numbers exactly (10/233 reports capped by
`_MAX_GLOBAL_REPORTS`, 4/4 synthesis nodes, `223` omitted = `233-10`, zero
warnings). `global`'s evidence assembly is confirmed working correctly on
live data; this part of the proposal is solid and unchanged.

---

## 4. "SYSTEM_BEHAVIOR claims language detection is deterministic and that is false for routing" + "`seed_terms()`/`_report_score()` are ASCII-only"

**Verdict: CONFIRMED on every sub-claim I checked. No changes.**

**Spec quotes, verified verbatim against the file:**
- `SYSTEM_BEHAVIOR.md:876`: *"Input-language detection is a deterministic,
  logic-level step, not merely a prompt instruction."* — confirmed present,
  exact wording.
- `SYSTEM_BEHAVIOR.md:1706-1707`: *"The v0.2.2 language bridge (§11
  inherited) is unchanged: detect latest-input language, reason in English,
  answer in the detected language..."* — confirmed present, exact wording.
- `SYSTEM_BEHAVIOR.md:1644-1645`: *"Routing is deterministic-first; an LLM
  router (`curator.query_router`) is used only when deterministic signals are
  ambiguous."* — confirmed present (bonus check, supports the proposal's
  separate Finding 6, not directly asked for here but corroborates the
  "spec describes machinery the code doesn't have" pattern).

**Code, verified against current source:**
- `detectLanguage()` (`plugin/src/context/languageBridge.ts:31-38`) is a real,
  deterministic Unicode-script-range classifier. Confirmed by reading it.
- `inferQueryLanguageMetadata()` (`languageBridge.ts:40-58`) — the function
  whose own docstring says the backend computes `english_query` — grepped for
  every import/call site in `plugin/src`: **zero**, outside its own test
  file. Dead in production, confirmed.
- `detectLanguage`'s only production call site is
  `ChatSidebarView.ts:1574`, feeding
  `wrapLatestUserMessageForLanguageBridge()`
  (`plugin/src/context/systemPrompt.ts:79-94`), which I read in full: it
  builds a natural-language instruction string ("Reason, search, and build
  MCP/tool arguments internally in English...") for the sidechat's own LLM —
  exactly the "merely a prompt instruction" the spec explicitly disclaims.
  Confirmed.
- Backend: `translate_to_english()` (`backend/src/curator/query.py:160-186`)
  has exactly one caller, confirmed by grep:
  `backend/src/curator/mcp/server.py:1935`, inside `curator_search`, which
  calls `search.query()` directly and never calls `choose_route` — confirmed
  by reading the surrounding function; it bypasses routing entirely.
- `choose_route()` (`retrieval/router.py:48`) has exactly one production
  caller, confirmed by grep: `context_service.py:559`.
- Every routing-relevant `QueryRequest` construction site leaves
  `english_query` unset or hardcodes it — confirmed by reading each:
  - `plugin_api/context.py:36-40`: `QueryRequest(question=query_text,
    workspace_path=workspace_path, mode="auto")` — no `english_query`.
  - `mcp/server.py:3241` (`curator_fetch_context`): `QueryRequest(question=query,
    workspace_path=workspace_path, mode="auto")` — no `english_query`.
  - `mcp/server.py:2015-2019` (`curator_query`): hardcodes
    `input_language="English", english_query=question,
    final_output_language="English"` **unconditionally**, regardless of the
    question's actual script. Confirmed by reading the call.
  - `QueryRequest.working_query` (`retrieval/models.py:35-36`): `(self.english_query
    or self.question).strip()` — confirmed; with `english_query` always empty
    on these paths, `choose_route` reads the raw original-language text.
- Live-tested `seed_terms()` myself (recreated the exact regex from
  `evidence.py:187-195`, `r"[A-Za-z][A-Za-z0-9+\-]*"`):
  ```
  seed_terms('이 개념의 핵심이 뭐야?') == []
  seed_terms('ellipsoid 형태의 quadric 은 어떻게 매트릭스로 표현되나?')
    == ['ellipsoid', 'quadric']
  ```
  Matches the proposal's reported output exactly.
- `_report_score()`'s regex (`evidence.py:292`,
  `r"[a-z][a-z0-9+\-]*"` applied to `target.lower()`) is likewise
  Latin-only — confirmed by reading the line; a pure-Korean report title/summary
  contributes zero tokens to `target_tokens`, so `overlap` is always 0 and the
  score degrades to `rank * 0.01`, confirmed by reading the formula.
- Live-tested the natural English translation of Q3 against `_GLOBAL_SIGNALS`
  (`router.py:25-29`, recreated verbatim): still `False`. Confirmed — even a
  flawless translation would not have routed Q3 to `global`.

**One correction to a claim adjacent to this section (§2 of the router
proposal, not explicitly asked about but bears on how far the "L3/L4 is
unreachable from `local`" claim should be trusted — see next item):**

---

## 5. Correction not explicitly requested but load-bearing: `local`'s search-hit fallback is NOT structurally excluded from L3/L4 — the router proposal's "two-layer exclusion" claim is half wrong

Flagging this because it's directly upstream of the "(c) weighted to (b)"
recommendation this task asked me to red-team, and because it changes what
"give local a primer" is actually buying.

The proposal states (§2, "Layer 2"): *"even `local`'s generic keyword-search
fallback is incapable of surfacing L3/L4 content by any query, not merely
unconfigured to look there — the corpus it searches doesn't contain L3/L4
rows... This is a hard, two-layer exclusion."* This is **factually wrong**,
proven by reading the same materializer the proposal didn't check:

- `materialize_search_documents()` (`materializer.py:429-451` for
  `community_report`, `:453-472` for `synthesis_node`) explicitly builds
  `search_documents` rows for both record types, unconditionally (no
  `support_status`-style gate — reports/synthesis don't carry that column).
- Confirmed live: `search_documents` has exactly 233 `community_report` rows
  and 4 `synthesis_node` rows — matching the full live count of each table.
- `local`'s `_add_search_hits()` → `_search_hits()`
  (`evidence.py:199-225`) calls `search.query(..., mode="hybrid", ...)`
  with **no `families` argument**, so `families=None` all the way down
  through `HybridEngine.search()` (`engine.py:216-260`) into both
  `lexical_search()` (`lexical.py:157,193-194`: `if families:` — falsy means
  no filter) and `vector.vector_search()` (`engine.py:131-134`, same
  `families=families` passthrough). **Nothing filters community_report or
  synthesis_node out of `local`'s search candidates.**
- The proposal's own grep ("`search.py` and `search_index.py`... zero hits
  for `community_reports`/`synthesis_nodes`") checked the wrong files — the
  materialization lives in `retrieval/materializer.py`, not `search.py`.

**Empirically**, I confirmed neither the four stale packs nor my fresh,
fully-configured Q1 rerun ever surfaced a `community_report/*` or
`synthesis_node/*` search hit (`grep -c` = 0 in all five JSON payloads I
checked) — so the *practical* outcome the proposal observed (0/39, 0/39,
0/35, 0/58 L3/L4 items via `local`) is real. But the proposal's own causal
claim for *why* — "structural," "the corpus doesn't contain L3/L4 rows" — is
disproved by the code and the DB. The correct statement is: **`local`'s
search-hit fallback CAN reach L3/L4 opportunistically via ranking; it simply
never ranked one into the top-8 for these four questions.** This is a ranking
outcome, not a structural wall — ironically, exactly the framing
`content_quality`'s F2 uses for its (also-wrong-for-different-reasons, see
§1) Q1 claim.

**Practical consequence for the recommendation:** an L3/L4 "primer" bolted
onto `local` would change this from probabilistic/opportunistic inclusion to
guaranteed inclusion — a legitimate reliability improvement — but it is not
the only conceivable fix, and the proposal's framing that no other fix is
even structurally possible is wrong. A cheaper alternative worth weighing
against a schema/contract change: boost `community_report`/`synthesis_node`
record types in `local`'s existing search-hit ranking (e.g. a small score
bonus) rather than adding a second, separately-selected evidence block. This
doesn't require the `SYSTEM_BEHAVIOR.md`/`USER_GUIDE.md` contract rewrite the
proposal says is mandatory before `evidence.py:441-448` can be touched — it's
a ranking-weight change inside the existing, already-specified `local`
contract ("expand to related claims/concepts/spans" already covers a report
edge case loosely). Only pursue the proposal's heavier primer/contract-change
route if boosting existing ranking is tried first and shown insufficient.

---

## 6. CONTENT F1 — tautological entity descriptions, 12/34 (35%) pack-level / 102/965 (10.6%) DB-wide

**Verdict: CONFIRMED. The criterion is defensible, not loose, and independently
reproducible — spot-checked by hand and by an independent automated proxy.**

**Prompt claim verified verbatim.** Read
`backend/src/curator/prompting/families/entities.py` in full.
`ExtractedEntity` (`:31-35`) declares `description: str = ""` with no field
description. The system prompt's seven "Hard rules" (`:57-69`) govern
`relation_type`, `assertion_source`, `confidence`, and span-id citation
discipline — **none constrain what `description` should say.** The one
worked example (`:74-75`) literally uses `"description": "..."` as a
placeholder. Confirmed exactly as claimed: there is no positive content
contract for this field.

**Manual re-tally, independent pass over all 34 pack entities (I did not
consult the proposal's per-item verdicts before classifying).** Applying
their own stated criterion ("after removing scaffolding words and every word
in the entity's own name, zero or one genuinely new content word remains"):
q1 — 0/6 tautological (my count matches: all six add real distinguishing
content, e.g. "rank 3 homogeneous symmetric matrix", "Fovis"). q2 — 0/2
(matches). q3 — my independent count landed at 2-3 clearly tautological of 8
(their claim: 4/8) — same order of magnitude, same two unambiguous examples
(`"2D Gaussian Splatting (2DGS)" → "A method using 2D Gaussian Splatting"`;
the paper-title-as-description entity). q4 — my independent count landed at
7-9 of 18 depending on two borderline calls (their claim: 8/18) — matches
within their own stated margin. Total independent estimate: ~10-12 of 34,
consistent with their 12/34.

**DB-wide automated proxy, reproduced independently with my own (smaller,
differently-tuned) scaffolding-word list against all 965 live
`graph_entities` rows:** 94/965 = 9.7% flagged, versus their reported
102/965 = 10.6%. Same order of magnitude, same conclusion ("at least ~10% of
all entity descriptions are pure restatement, DB-wide, as a conservative
lower bound"). The criterion is reproducible by an independent implementation,
not an artifact of one particular word list.

**No changes to this finding's severity (P2) or fix direction** (add a
positive content contract + a bad/good contrastive example to the extraction
prompt's `SYSTEM_TEMPLATE`). One additive note for triage, not a downgrade:
the "6 duplicate near-identical 2D Gaussian Splatting entity records" side
observation is a real, separate entity-resolution/dedup issue the proposal
correctly declines to double-count — worth keeping distinct in any write-up
that acts on this finding, since fixing description quality alone won't fix
duplication.

---

## Summary verdict table

| # | Finding | Verdict | New severity | Key evidence |
|---|---|---|---|---|
| CONTENT F2 | "Ranking failure, not thin content" for Q1's duplicate KUs | **CONFIRMED, but root cause WRONG** | P1 (unchanged, arguably reinforced) | 0 rows in `search_documents` for all 4 KU ids (not "fully indexed"); gated by `materializer.py:237` `support_status='verified'` filter; these 4 sit at `unchecked`/`uncertain` because span text has no `$...$` delimiters (`claim_support.py:379-384`); the designed remedy `recover_formula()`/`classify_formula_loss()` (`formula_recovery.py:36,73`) is never called from any production path — dead code, tests-only. 480 KUs vault-wide share this exact signature; 1,701/2,799 (61%) of all live KUs are unindexed for this class of reason. |
| — confound test | Is F2 an artifact of degraded FTS5-only invocation? | **RESOLVED: no** | — | Live re-run of the same Q1 query returns `warnings: []`, `sufficiency: "sufficient"`, real rerank scores (0.80-0.94) — the vault's actual config has embedder+reranker wired (confirms `content_quality`'s Finding 3 is itself REFUTED by this live counter-example). But the missing formula is *still* 0/39 in the fully-configured rerun — proves the config gap and the F2 defect are independent; fixing one doesn't fix the other. |
| ROUTER "(c) weighted to (b)" | Give `local` a bounded L3/L4 primer; "fixes Q1, Q2, Q3, and Q4 simultaneously" | **DOWNGRADED** | Split: keep for Q3/Q4-class, drop for Q1/Q2-class | The most relevant of 233 community reports for Q1 (`REP-de8f745f`) explicitly self-reports "thin" evidence and lacks the formula; 0/233 reports contain the distinguishing phrase. A primer, however chosen, cannot surface a fact absent from every candidate. Confirmed a fully-configured plain `local` (no primer, no route change) also fails to find it — the defect is upstream of both routing and evidence composition (§1). For Q3, by contrast, `SYN-95144d37` is a genuine, on-topic synthesized answer already in L4 — the primer/route-change recommendation is well-supported there. |
| ROUTER forced-route Q3 test | `mode="global"` → 10/233 reports + 4/4 synthesis | **CONFIRMED** | Confirms scope (unchanged) | Re-ran independently, byte-for-byte matching numbers: `route=global`, 10 `community_report_ids`, 4 `synthesis_node_ids`, 14 items, `warnings=[]`, `omitted_counts.global_reports=223`. |
| ROUTER language-bridge claims | SYSTEM_BEHAVIOR's "deterministic, not merely a prompt instruction" is false for the routing-relevant query path; `seed_terms()`/`_report_score()` are ASCII-only | **CONFIRMED** | P1 / P2 (unchanged) | Every quote verified verbatim against `SYSTEM_BEHAVIOR.md`. Every code citation verified verbatim: `inferQueryLanguageMetadata` dead outside tests; `detectLanguage`'s only production use feeds a soft LLM prompt string; `translate_to_english`'s only caller bypasses `choose_route`; every routing-relevant `QueryRequest` construction leaves `english_query` empty or hardcodes `"English"` unconditionally; `seed_terms`/`_report_score` regexes are `[A-Za-z]...`/`[a-z]...` — reproduced their exact live-test outputs. |
| (bonus, load-bearing for the router item above) | "`local`'s search fallback is structurally incapable of reaching L3/L4 — the corpus doesn't contain those rows" | **REFUTED** | — | `materializer.py:429-472` builds `community_report`/`synthesis_node` search docs unconditionally; confirmed 233+4 such rows live in `search_documents`; `local`'s `_add_search_hits` passes `families=None`, which both `lexical_search` and `vector_search` treat as "no filter" — L3/L4 IS in `local`'s candidate pool. The 0/39 outcome across all 4 packs is a ranking outcome (none scored into the top 8), not a structural exclusion. Weakens the case that a schema/contract change is the *only* fix; a ranking-weight boost inside the existing `local` contract is a cheaper alternative worth trying first. |
| CONTENT F1 | 12/34 (35%) pack entities tautological; 102/965 (10.6%) DB-wide; prompt has no description guidance | **CONFIRMED** | P2 (unchanged) | Prompt read in full — verified no content contract, verified placeholder example. Independent manual re-tally of all 34 pack entities lands in the same range (~10-12/34) using their own stated criterion. Independent automated DB-wide proxy (different, smaller scaffolding-word list) gives 94/965 = 9.7%, same order of magnitude as their 102/965 = 10.6%. |

---

## What I did NOT do

- Did not modify `router.py`, `evidence.py`, `materializer.py`,
  `claim_support.py`, `formula_recovery.py`, any prompt file, any spec, or
  any doc.
- Did not touch `.curator/state.sqlite` (still the stale 0-byte file per both
  proposals' prior observation — not used by the app, not touched here
  either).
- Ran two additional read-path retrieval calls beyond what the two proposals
  already ran: one `wiki plugin context fetch` (Q1, to test the
  embedder/reranker confound) and one direct `ContextService.context_fetch(mode="global")`
  call (Q3, re-running the router proposal's own forced-route test for
  independent verification). Each writes exactly one `query_traces` row, the
  same sanctioned instrumentation side effect. Two incidental scratch files
  written into the vault root by the first call (`out.json`, `err.log`) were
  deleted before this file was written; the vault root is unchanged from
  before this review.
- Did not re-run Q2 or Q4 forced to alternate routes — the task scoped this
  review to Q1 (CONTENT F2) and Q3 (the router's own forced-route test); I
  additionally checked Q3's L3/L4 content quality (§2b) using only the
  existing `q3.json`/DB data, no new query.
