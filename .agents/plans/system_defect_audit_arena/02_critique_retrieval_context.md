# Critique on `01_proposal_retrieval_context.md` (retrieval_context inspector)
Date: 2026-08-04 | Agent Persona: Red-Team Retrieval Contract Critic

## Method

Every cited `file:line` was re-read at the current working tree. Every cited spec
range was re-read verbatim from `docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`
(3105–3300, 3395–3412) and `docs/specs/search_engine/SEARCH_ENGINE_SCHEMA.md`
(310–325). Every cited test was re-read, plus three the inspector never opened.

Two things this pass added that the inspector explicitly could not do:

1. **An executed reproduction.** The inspector was analysis-only and asked a
   red-teamer to confirm `retrieval_context-1` and `-2` by running them. I did,
   in the session scratchpad, against a throwaway vault built by the repo's own
   `backend/tests/test_plan_f_context_service_contract.py::_seed_budget_vault`
   helper. No repository file, no `testbed/`, no vault, no `.cache/` state was
   touched; the only file I wrote inside the repo is this critique.
2. **The normative fixture directory.**
   `docs/specs/system_behavior/context_service_fixtures/*.json` lives **inside
   `docs/specs/`** and is loaded by that same test file at lines 20–21. It is
   spec surface, not test scaffolding, and it settles three of the five findings
   in machine-readable form — and it *corrects* the inspector's fix direction on
   two of them.

**Reproduction transcript** (`.venv-dev/bin/python`, `_seed_budget_vault`,
`context_fetch(question="context budget evidence", mode="local", limit_tokens=100)`):

```
budget: {'limit_tokens': 100, 'used_tokens': 75, 'reserved_tokens': 25,
         'omitted_items': 5, 'estimation_mode': 'conservative'}
selected: 5   next: 5
EXPAND @ same L(=100)  ok=True  items=0
  refused=[{"handle":"EXP-e04d1ab2058f","reason":"budget_exhausted",
            "item_id":"SPAN-0cacd700","snapshot_id":"SNAP-8522d38ca52a",
            "retry":"increase_limit_tokens_or_refetch"}]
snapshot keys: ['db_schema_version','policy_hash','snapshot_id',
                'source_epoch_hash','tokenizer']       # has created_at: False
trace 'policy' key present: False
item kind/layer: entity / entity
snapshot moved after corpus mutation: SNAP-8522d38ca52a -> SNAP-3571bdcb8c1e
EXPAND after corpus mutation  ok=True  error_type=None  items=1
VERIFY after corpus mutation  ok=True  deps=[]  contradictions=[]
```

## Verdict summary

| Finding | Inspector | Verdict | Final |
|---|---|---|---|
| `retrieval_context-1` — expand/verify never recompute the snapshot | P1 | **downgraded** | **P2** |
| `retrieval_context-2` — expansion reserve double-subtracted | P2 | **confirmed** (spec grounding corrected, worse than stated) | P2 |
| `retrieval_context-3` — snapshot closure incomplete | P2 | **confirmed** (strengthened by fixture) | P2 |
| `retrieval_context-4` — `policy`/§31.5 fields missing, `layer` == `kind` | P2 | **confirmed** (two evidence errors corrected) | P2 |
| `retrieval_context-5` — expander failure swallowed, trace claims it ran | P2 | **confirmed** (framing trimmed) | P2 |

Nothing was fully refuted. One severity is inflated. Two findings are *worse*
than the inspector argued. Two contain supporting reasoning that, if carried
into the Master Plan unchanged, would produce a wrong fix.

---

## 1. Vulnerabilities & Flaws

### 1.1 `retrieval_context-1` — **DOWNGRADED P1 → P2**

**Refutation attempts, all failed on the defect itself.**

*(a) Is `_snapshot` reached on the expand path through a helper?* No.
`grep -n "_snapshot("` over `context_service.py` returns exactly `:542`
(`context_fetch`) and `:696` (`context_manifest`). `context_expand:744-750` and
`context_verify:866-872` read `context["snapshot"]["snapshot_id"]` out of the
persisted blob, and `_find_context_pack_by_pack_id:1053-1063` is one
`db.get_query_trace_by_context_pack` read plus a dict lookup — no live table is
touched. `context_feedback` does the same at `:952-953`.

*(b) Does an upstream caller guard it?* The opposite — the shipped caller makes
the tautology total. `plugin/src/ui/chat/ChatSidebarView.ts:3080,3091` pass
`expectedSnapshotId: detail.snapshot_id`, where `detail` is the `next[]` entry
that `context_service.py:642-650` stamped with the pack's own
`snapshot["snapshot_id"]`. The compared strings are two copies of one value.

*(c) Does "immutable snapshot" semantics make stored-vs-stored correct?* No.
§31.3's operative sentence is *"If any snapshot component changed, the service
returns a typed conflict with `current_snapshot_id` and does not mix epochs
silently."* A component "changing" is only observable against live state, and
`_conflict_response`'s own vocabulary — `current_snapshot_id`, `"resolution":
"refetch_or_rebase"` — is live-world vocabulary. The normative fixture
`context_service_fixtures/snapshot_conflict.json` seals it: a `context_expand`
with `expected_snapshot_id: "SNAP-old"` answered by `current_snapshot_id:
"SNAP-new"`. Under today's code `current_snapshot_id` is *always* the id the
pack was minted with, so a strictly newer `SNAP-new` is a response the
implementation cannot produce.

**Reachability executed, not assumed.** After a single
`db.upsert_source_span(...)` against the seeded vault, a fresh `context_fetch`
returned `SNAP-3571bdcb8c1e` while the stored pack still said
`SNAP-8522d38ca52a`. `context_expand(expected_snapshot_id="SNAP-8522d38ca52a")`
then returned `ok=True, error_type=None` and **served the item**.
`context_verify` likewise returned `ok=True`. The defect is executable, not
analytic. **Confirmed as a defect.**

**Why P1 is inflated.** The rubric reserves P1 for "user-visible breakage with
**no workaround**"; P2 is "contract violation, silent degradation". Three facts
put it in P2:

1. **Nothing breaks.** The operation succeeds and returns well-formed data. The
   harm is an absent signal — the definition of silent degradation.
2. **A workaround exists on an existing surface and is cheap.** `context_fetch`
   *does* recompute live (`:542-544`) and returns `_conflict_response` *before*
   `router.graph_status` (`:546`) and `build_evidence` (`:556`) — so a client
   holding `SNAP-abc` can detect movement for the cost of one `_source_epoch`
   scan, with no retrieval and no LLM call. My transcript shows the id actually
   moving on that path. Clunky and undiscoverable, but a real client-side
   detection route, which is exactly what P1 says must not exist.
3. **Expand introduces no *new* wrongness.** It serves payloads captured at
   fetch time (`:578-580`, `:621`), every one of which was already handed to the
   client in `next` at fetch. The client's *selected* items are equally stale and
   the client may hold the pack for any interval. This is stale replay over a
   bounded window, not fabrication (P0) and not a broken flow (P1).

The inspector's own second-pass note concedes P2 is defensible; the rubric makes
it correct. **severity_final: P2.** Priority is unchanged — it must still ship,
paired with `retrieval_context-3`.

**Correction to the fix direction — this matters for the Master Plan.** The
proposal's fix ("recompute, hard-conflict on any divergence") is spec-literal
but, shipped with `-3`, is a worse product than the bug: a routine
`wiki reindex` or Phase-C L4 regeneration would move the new epochs and
invalidate every pack in flight, so progressive expansion (the whole point of
§31.1) would fail continuously on an actively-ingesting vault, and users would
respond by not passing `expected_snapshot_id` at all — strictly worse than the
status quo. The repair needs three parts, not one:

- **Tier 1 (hard conflict):** `source_epoch`, `db_epoch`, `policy_hash` moved →
  `_conflict_response(expected, recomputed)`.
- **Tier 2 (soft drift):** `search_epoch`, `dependency_epoch`,
  `model_config_hash` moved → serve, but attach `current_snapshot_id` and an
  explicit drift warning. §31.3's "does not mix epochs silently" is satisfied by
  *disclosure*, not only by refusal — but this reading must be written into
  §31.3 in the same change or spec and code diverge again in the other
  direction.
- **Per-handle revalidation (absent from the proposal entirely, and the most
  useful part):** each stored payload already carries `record_hash`
  (`context_service.py:436-438`) and `source_span_ids`. Re-read those spans
  before serving an expanded item. That answers the question the caller actually
  has ("is *this* handle still real?"), which no global epoch digest can answer.

---

### 1.2 `retrieval_context-2` — **CONFIRMED (P2)**, spec grounding corrected, defect worse than stated

**Refutation attempts.**

*(a) Do the two cost functions differ, so `already_used != used_final`?* No.
`_apply_budget:207` costs `_estimate_tokens(item.text)`; `_item_payload:454`
stores `"token_cost": _estimate_tokens(item.text)`; `_payload_token_cost:460-461`
reads that value back; `:765` sums it over `context["selected_items"]`, which is
exactly the fetch-time selection (`:575-577`, `:620`). Identical number.

*(b) Can `omitted_items` contain non-budget omissions that escape the proof?*
No. The stored `omitted_items` is `omitted_payloads`, built solely from
`budget_omitted_items` (`:557`, `:578-580`, `:621`), and `next[]` is built from
that same list (`:642-650`). Policy and route omissions are counters in
`pack.omitted_counts` (`:562-566`) and never become handles. Every advertised
handle is a budget omission, so the monotonicity proof covers all of them.

*(c) Do real callers use different budgets on the two calls?* No — and this is
what makes it a shipped defect rather than a theoretical one.
`plugin_api/context.py:17` and `:58` both default `limit_tokens=8000`; the CLI
mirrors both at `commands/plugin.py:514,539`; and
`plugin/src/agent/incuratorClient.ts:560,585` append `--limit-tokens` **only if
`opts.limitTokens` is set**, otherwise both commands fall through to the same
8000 default. Equal budgets are the *default* path.

**Reproduced.** At `limit_tokens=100`: `reserved=25`, `available=75`, five items
selected (`used_tokens=75`), five handles offered. Expanding the first handle at
the **same** `limit_tokens=100` returned `items=[]` and
`expansion_refused[0].reason == "budget_exhausted"`, while the cumulative total
would have been `75 + 15 = 90 ≤ 100`.

**Where the inspector overreached — fix this before it reaches the plan.** §31.1
(3184–3186) reads *"a newly expanded item is admitted **only if** it fits within
`limit_tokens` alongside everything already selected."* That is a **necessary**
condition, not a sufficient one. The proposal's line "7200 ≤ 8000 = limit_tokens,
so §31.1 says it MUST be admitted" is a quantifier error — a stricter service
still satisfies "only if". A reviewer can shoot the finding down on that clause
alone if the plan cites it as the violated text.

**The correct grounding is stronger, and it is normative.**

- §31.2 (3207) makes `reserve_for_expansion` an explicit **request budget
  field**; §31.4 (3267) lists "reserved expansion budget" as an enforced budget
  dimension. `grep -rn "reserve_for_expansion" backend/src/curator/` → **zero
  hits**: the request field is never read at all, and `_DEFAULT_RESERVED_TOKENS`
  is hardcoded on both paths.
- The normative expand fixture settles the second half:
  `context_service_fixtures/context_expand.json` carries
  `request.budget.reserve_for_expansion: 0` **and**
  `response.budget.reserved_tokens: 0` at `limit_tokens: 2000`. Today's code
  would emit `reserved_tokens: 500` (`min(1000, 2000//4)`) for that exact
  request. The expand fixture and the expand code already disagree, in
  machine-readable form, independent of any prose reading.

So the defect is two-layered: (i) the request's `reserve_for_expansion` is
silently ignored, and (ii) the hardcoded substitute is withheld a second time on
the very operation it was reserved *for*, making it permanently unspendable.

**The inspector cited the wrong test, and the right one is worse for the code.**
The proposal points at `test_context_expand_consumes_successful_handles_once`
(`:656-692`, fetch at 20 / expand at 400) as the sidestep. But
`test_context_expand_keeps_cumulative_pack_within_budget` (`:812-835`) **does**
exercise the equal-budget case — fetch `limit_tokens=20` (`:819`), expand
`limit_tokens=20` (`:828`) — and passes green today. It passes because its only
assertions are `ok is True`, `used_tokens >= already_used`, and
`used_tokens <= limit_tokens` (`:833-835`); none of them look at `items`. At
`limit=20`: `reserved = min(1000, 5) = 5`, `available = 15`, the expansion admits
nothing, `omitted` is non-empty so the `:769` early return is skipped, and the
test is satisfied by a response with `items: []` and a populated
`expansion_refused`. The scenario is **pinned green by a live test that is
structurally blind to the outcome** — a stronger statement than "untested".

**Severity stays P2.** `increase_limit_tokens_or_refetch` is an honest,
advertised workaround and the surface degrades rather than breaks. It remains
the highest impact-to-cost item in this domain.

---

### 1.3 `retrieval_context-3` — **CONFIRMED (P2)**, strengthened; one sub-claim overstated

**Refutation attempts.** *(a) Does `db.SCHEMA_VERSION` + `source_epoch` already
cover §31.3?* Partially — `SCHEMA_VERSION` is a fair reading of "DB epoch", so
the closure covers roughly 4½ of 7 components, not 3 of 7. That does not save it:
the two hard-missing components are the search/index epoch and the
derived-state epoch, precisely the two that move most often here. *(b) Is
`"conservative"` a model identity?* No — it is a hardcoded literal at `:167` and
`:177` naming the estimation strategy. *(c) Does §31.3 really enumerate those
components?* Re-read verbatim: *"source/corpus identity, DB epoch, search/index
epoch, dependency or derived-state epoch, `curate.yml` policy hash,
model/tokenizer/config identity, and creation time."* Yes.

**The evidence the inspector should have led with.** The normative fixture
`context_fetch_pack.json` declares the pack snapshot as:

```json
"snapshot": {"snapshot_id": "SNAP-example", "source_epoch": "SRC-example",
 "db_epoch": "DB-example", "search_epoch": "IDX-example",
 "dependency_epoch": "DEP-example", "policy_hash": "POL-example",
 "model_config_hash": "MODEL-example", "tokenizer_id": "cl100k_base",
 "created_at": "2026-06-18T00:00:00Z"}
```

That is §31.3's closure enumerated field-by-field in a machine-readable spec
artifact. The code (`_snapshot:170-178`) emits `{snapshot_id,
source_epoch_hash, db_schema_version, policy_hash, tokenizer}` — **none** of
`search_epoch`, `dependency_epoch`, `model_config_hash`, `created_at`, and it
reports `tokenizer: "conservative"` where the fixture names a real
`tokenizer_id`. My transcript confirms the live key set at runtime. This
converts the finding from "prose says X, code does Y" (arguable) into "two spec
artifacts and the code disagree three ways" (not arguable).

**Reachability control.** `_source_epoch:136-152` reads exactly two statements.
My mutation test moved a `source_spans` row and the id *did* move — the control
proving the digest is sensitive to those two tables and nothing else. So a
`wiki reindex --embed` (rewrites `search_documents`/`search_chunks`/embeddings)
or a Phase-C rerun (rewrites `synthesis_nodes` wholesale, per briefing ENH-01)
leaves the digest byte-identical.

**Where the inspector overstated.** The claim *"§31.4's pack
`snapshot.created_at` is a `KeyError` for every caller"* is wrong: the field is
confirmed absent (`has created_at: False`), but `grep` for a snapshot-scoped
`created_at` across `backend/` and `plugin/src/` finds **no reader at all**.
Nothing crashes today. That sub-claim is contract drift, not a live fault; the
plan should not budget for a crash fix.

**One spec defect neither pass flagged as such.** §31.3 says the closure
"includes … and creation time", while the correct engineering fix emits
`created_at` *excluded* from the digest — including it would make every
`snapshot_id` unique and turn `expected_snapshot_id` into a permanent conflict
generator. That means **§31.3's prose is itself wrong** and must be amended in
the same commit. Ground rule 5: spec-vs-code divergence means both are wrong
until reconciled.

---

### 1.4 `retrieval_context-4` — **CONFIRMED (P2)**, two evidence errors corrected

**All three sub-claims re-verified.**

- (a) `_build_retrieval_trace:101-121` writes `contract_version`,
  `retrieval_execution_id`, `route`, `selection`, `warnings` and stops.
  `grep -n '"policy"'` across `context_service.py` and `retrieval/*.py` → zero
  hits; `grep -rn "source_include\|source_exclude"` over the same set → zero
  hits. `base` is seeded from the engine's §8 trace (`engine.py:364-384`), which
  has no `policy` key either, so it cannot be inherited. The response
  (`:651-691`) has no `policy` key. Runtime: `trace 'policy' key present: False`.
  §30.2 (3116-3129) carries `"policy": {"source_include": [], "source_exclude":
  []}` and calls the object "the only authoritative record of the retrieval
  execution"; §31.4 and `context_fetch_pack.json` both carry a top-level
  `policy: {applied_filters, excluded}`.
- (b) `_item_payload:433-457` emits the quoted key set; `_search_hits`
  (`evidence.py:219-224`) really does drop `EngineHit.contributions` (populated
  at `engine.py:355` from `fusion.FusedHit.contributions`) and
  `EngineHit.record_type` (`engine.py:350`) when it builds the `EvidenceItem`.
  `coverage` is `{sufficiency, omitted_counts}` only (`:665-668`).
- (c) `:439-440` is `"kind": item.kind, "layer": item.kind`; `"layer"` appears in
  the pack path exactly once. Runtime: `item kind/layer: entity / entity`. Other
  repo hits (`mcp/server.py:273`, `commands/common.py:418`) are unrelated
  surfaces.

**Evidence error #1 — the inspector's contradiction narrative is factually wrong,
and the truth is worse.** RC-5(b) argues contradictions are "reachable through a
*separate* `context_verify` round trip per item … whose response carries
`contradictions`", framing the cost as "12 extra service calls". `context_verify`
returns `"dependencies": []` and `"contradictions": []` as **hardcoded empty
literals** (`context_service.py:910-911`); my transcript confirms
`VERIFY … deps=[] contradictions=[]`. Those calls recover nothing, and the
assertion at `test_plan_f_context_service_contract.py:885` pins the presence of
an always-empty key, not a working feature. The correct statement is stronger:
**contradiction and dependency state is missing from the entire ContextService
surface**, including the operation §31.1 defines as *"Resolve an item/claim
handle to exact source evidence, **dependencies**, locator state, and
**contradictions**."* List this explicitly in the plan, or someone will "fix"
the item field by plumbing it to a `context_verify` that returns `[]`.

**Evidence error #2 — the `detail level` sub-claim is misdiagnosed.** The
proposal says detail level is "missing outright". It is not missing; it is
**occupied by the wrong content**. The fixture item carries `"detail": "index"`
— the §31.2 detail level — while the code writes `"detail": item.text`
(`:442`), the raw item body. That is the same defect shape as `layer`: correct
key, structurally wrong value, and it is why the `required <= set(item)` guard
never noticed. Do not add a new `detail_level` key on top of the collision;
reconcile `detail` against the fixture first.

**Correction #3 — the proposed `layer` mapping is wrong.** The inspector
proposes `source_span→"01_Contexts"`, `entity→"02_Atoms"`,
`community_report→"03_Concepts"`, `synthesis→"04_Synthesis"` (vault folder
names). The normative fixture uses **`"layer": "L1"`** alongside
`"kind": "source_span"`. Shipping folder names would satisfy §31.5's prose while
breaking the fixture the moment the same change upgrades the test to assert live
output — which is that change's own stated goal. Use `L1`/`L2`/`L3`/`L4`.

**Correction #4 — the field count is five, not four.** The fixture item's key
set is `[authority_state, contradiction_state, dependency_ids, detail,
expansion_handle, freshness_state, item_id, kind, layer, locator, ranking,
record_hash, record_id, route_reason, score, source_span_ids, summary,
token_cost, truth_state, verification_handle]`. Beyond the four the inspector
named, `route_reason` (§31.5's "route/expansion reason") is also absent from the
code. `coverage.contradictions_present` and `coverage.omission_categories` are
in the fixture too.

**Severity stays P2.** The `layer` mislabel is a live contract violation, but no
in-repo consumer filters on it (`plugin/src` does not read `layer` from pack
items), so the "external MCP agent drops the whole pack" scenario is
hypothetical rather than observed — a contract violation, not user-visible
breakage.

---

### 1.5 `retrieval_context-5` — **CONFIRMED (P2)**, framing trimmed

**Re-verified sites.** `query_expander.py:140-159` has two bare
`except Exception: return {}`. `expansion.py:97-101` wraps the call in
`try/except Exception: extra = {}`. `grep -n "logger\|logging"` over **both**
modules returns **zero hits** — neither file imports a logger.
`engine.py:270-274` computes `use_expander` from `self.expander is not None` and
gates the only `query_expander_unavailable` emission on `self.expander is None`.
`engine.py:371` writes `"used": use_expander` into the persisted trace.

**Where the inspector overreached #1 — the swallow is spec-legal.** §32
(3403–3406) says *"Optional classification or suggestion failures may preserve
deterministic fallback output, but the suppressed cause remains observable in
logs."* Query expansion is exactly an optional suggestion enhancer, and
`expansion.py:86-94` does preserve deterministic output (`_synonym_terms`,
`vec_texts=[raw]`). So "swallowed twice" is not itself the defect, and
`test_query_expander.py:45-52` (`exp("q") == {}` on a raising client) pins the
**sanctioned failsafe**, not the bug. The finding survives ground rule 4 only
because the real defect is the second half of that sentence.

**Where the inspector overreached #2 — "the trace lies" is an interpretation.**
SEARCH_ENGINE_SCHEMA §8 shows `expansion.used` in the required shape but defines
no semantics for it in the Rules block (311–322). Reading `used` as "the
expander path was taken" is defensible — it *was* taken (`engine.py:276-282`).
A defender can hold that line, so do not make it the load-bearing claim.

**What cannot be defended, and is the finding.**

1. **The suppressed cause is observable nowhere.** Three bare handlers
   (`query_expander.py:152,157`; `expansion.py:99-100`) discard the exception
   object, and neither module has a logger. §32's "remains observable in logs"
   has no implementation on this path. Unambiguous violation.
2. **The one machine-readable warning cannot fire in the failure case.**
   `engine.py:273-274` gates `query_expander_unavailable` on
   `self.expander is None` — it fires only when the expander was never *built*,
   never when a built expander fails at query time. SEARCH_ENGINE §8 (321) names
   that prefix for exactly this class of degradation.
   `grep -rn "query_expander_unavailable"` → one hit, `engine.py:274`;
   `backend/tests/` → zero.
3. **Internal incoherence in one dict.** `"used": use_expander` (`:371`) is
   config-derived while its sibling `"hyde_used": bool(expanded.hyde_text)`
   (`:376`) is outcome-derived. There is no reading under which both are
   coherent.

**Reachability is better than the inspector argued.** The proposal leans on a
llama.cpp OOM / moved GGUF. But the expander is rebuilt per query
(`search.py:236-237` calls `build_query_expander(config, want_hyde=True)` inside
the query path), so a startup-shaped failure returns `None` and the existing
warning *does* fire. The genuinely reachable path is the HTTP-provider one, and
it is already pinned green by `test_query_expander.py:45-52`: a successfully
built expander whose `.chat()` raises at call time and returns silence. For
Ollama/DeepSeek/Antigravity `build_client` performs no network I/O, so this is
the *normal* provider-down shape. Cite that test, not llama.cpp.

**Severity stays P2** — silent degradation with a preserved deterministic
fallback and no user-facing break.

---

## 2. Suggested Alternatives

### 2.1 `retrieval_context-2` — fix the root cause, not the symptom

The inspector offers two options; only one is correct. Threading the fetch-time
`reserved` back in (`available = limit - reserved + reserved_fetch`) is a
coincidence-fix that equals `limit` only because both sides compute `reserved`
identically *today* — it breaks the moment §31.2's `reserve_for_expansion` is
wired up. Do both layers:

1. Thread `budget.reserve_for_expansion` from the request into `_apply_budget`,
   falling back to `min(_DEFAULT_RESERVED_TOKENS, limit // 4)` only when the
   caller supplies nothing, so `reserved_tokens` reflects the request the way
   `context_expand.json` shows (`reserve_for_expansion: 0` → `reserved_tokens: 0`).
2. In `_budget_payloads`, gate on `already_used + cost <= limit_tokens`, still
   reporting `reserved_tokens` for symmetry with `context_fetch`.

Regression coverage — three tests, not one:

- Fetch at limit `L` with a non-empty `next`, expand at the **same** `L`, assert
  `items` is non-empty and contains the first handle. (My transcript is a working
  seed: `_seed_budget_vault`, fetch at 100, expand at 100.)
- **Upgrade `test_context_expand_keeps_cumulative_pack_within_budget`
  (`:812-835`) to assert on `items`, not only on `budget`.** As written it stays
  green through both the broken and the fixed behavior — that is how the defect
  survived.
- Assert `reserved_tokens == request.budget.reserve_for_expansion` when supplied.

Pre-checked for collateral breakage:
`test_budget_payloads_accounts_for_already_used_tokens` (`:785-801`) survives —
at `limit=200`, `already_used=190`, `cost=100`, the new rule gives `290 > 200`,
so the item is still omitted and `used_tokens` is still `190`. No existing
assertion has to be relaxed.

### 2.2 `retrieval_context-3` + `retrieval_context-1` — one change, this order

Land the closure first, the recomputation second, or the recomputation ships
blind.

1. **Widen the closure to the fixture's shape** — `source_epoch`, `db_epoch`,
   `search_epoch`, `dependency_epoch`, `policy_hash`, `model_config_hash`,
   `tokenizer_id`, `created_at` — reusing `_hash_epoch_rows` for the two new
   epochs so §31.3's "compact deterministic counts plus ordered hashes" rule
   still holds. Do not invent names; `context_fetch_pack.json` already fixes
   them. **Tag each component hard/soft in the closure itself** so step 3 is a
   lookup rather than a re-derivation.
2. **Amend §31.3's "and creation time"** to state that creation time is recorded
   on the snapshot object but excluded from the digest. Spec and code in the
   same commit.
3. **Persist the request closure** (`mode`, `source_key`, `workspace_path`,
   `policy_hash`) inside `context["snapshot"]` so expand/verify/feedback can
   recompute exactly; then recompute in all three and apply the tier split from
   §1.1: hard conflict on `source_epoch`/`db_epoch`/`policy_hash`, disclosed
   drift on `search_epoch`/`dependency_epoch`/`model_config_hash`.
4. **Add per-handle `record_hash` revalidation** before serving an expanded
   item — the cheapest and most useful half of the repair, and absent from the
   proposal.
5. Regression tests: insert a `sources` row between fetch and expand, assert
   `error_type == "snapshot_conflict"`; rebuild `search_documents` only, assert
   the disclosed drift rather than silence.

### 2.3 `retrieval_context-4` — drive the fix off the fixture, and make the fixture bite

- Map `kind → layer` as **`L1`/`L2`/`L3`/`L4`** (`source_span→L1`, `entity→L2`,
  `community_report→L3`, `synthesis→L4`), matching `context_fetch_pack.json`.
  **Not** `01_Contexts`-style folder names. For `search_hit`, thread
  `EngineHit.record_type` (`engine.py:350`, from `_hydrate`) into `EvidenceItem`
  and map that; emit an explicit `"unknown"` if unresolvable rather than echoing
  `kind`.
- Add `ranking` (thread the already-computed `EngineHit.contributions` from
  `engine.py:355` through `evidence.py:219-224` — same one-line plumbing change
  as `record_type`, so schedule them as one task), `route_reason`,
  `dependency_ids` (from `dag_edges`), `contradiction_state`, plus
  `coverage.contradictions_present` / `coverage.omission_categories` and the
  top-level `policy` block (`policy` is already in scope at `:556`).
- **Reconcile `detail` before adding anything named `detail_level`** — the key
  already exists and currently holds the item body instead of the §31.2 detail
  level.
- **Make `context_verify` stop returning hardcoded `[]`** (`:910-911`). Any fix
  to the item-level contradiction field that leaves this untouched is cosmetic.
- **Change the test, or none of this is durable.**
  `test_context_fetch_fixture_pins_pack_contract` (`:39-56`) validates the
  *fixture* against a hand-maintained `required` subset. Invert it: assert that
  every key present in the fixture item is present in **live** `context_fetch`
  output, so the fixture becomes the contract and drift fails the build; keep a
  value-level assertion that `layer` matches `^L[1-4]$`.
- Bump the pack `contract_version` (`:614`, `:653`) — `layer`'s value domain
  changes.

### 2.4 `retrieval_context-5` — split along the domain boundary

- **Retrieval-owned half (this batch):** record the outcome on `ExpandedQuery`
  (`expander_error: str` set in the `except` at `expansion.py:100`;
  `expander_contributed: bool` set when any `lex_terms` / `vec_texts` /
  `hyde_text` actually materialized); drive trace `expansion.used` from
  `expander_contributed`, keeping the config-time value under a distinct
  `expansion.attempted` key so the §8 shape stays legible and nothing is lost;
  append `query_expander_unavailable: <ExcType>: <msg>` to `warnings` whenever
  `use_expander` was True and nothing was contributed.
- **§32-owned half (merge with `exception_hygiene`):** the
  `logger.warning(..., exc_info=True)` calls at `query_expander.py:152,157` and
  `expansion.py:100`. This is the same defect class as already-confirmed CAND-01
  and CAND-02; expect a duplicate and merge rather than fix twice.
- **Do not change the expander's return contract.**
  `test_query_expander.py:39-52` pins `exp("q") == {}` on both the bad-JSON and
  chat-error paths. Returning a typed object breaks two passing tests for no
  benefit — carry the failure on `ExpandedQuery`, where the engine can see it.
- Add the missing coverage: a built-but-failing expander must produce a
  `query_expander_unavailable:` warning and `expansion.used is False`. That
  prefix has zero test references anywhere in `backend/tests/`.

### 2.5 Sequencing for the synthesizer

1. **`retrieval_context-2` first and alone** — one comparison plus the
   `reserve_for_expansion` threading, no contract-version bump, independently
   revertible, and the only finding that makes a shipped default path
   (`--limit-tokens 8000` on both `context fetch` and `context expand`) do
   nothing useful.
2. **`retrieval_context-3` → `retrieval_context-1` as one change**, one spec
   edit, one `contract_version` bump.
3. **`retrieval_context-4`** — can ride the same bump if it lands in the same
   release; shares the `evidence._search_hits` plumbing edit.
4. **`retrieval_context-5`** — independent; hand the logging half to
   `exception_hygiene`.

### 2.6 The highest-value cross-cutting item

`docs/specs/system_behavior/context_service_fixtures/*.json` is the most
valuable artifact in this domain and is currently near-inert: it is loaded by
exactly one test that validates the *fixture* against a hand-written subset
instead of validating the *code* against the fixture. Three of the five findings
here (`-2`'s `reserved_tokens`, `-3`'s snapshot closure, `-4`'s item shape)
would have been caught at authoring time by a single test asserting live
`context_fetch` / `context_expand` output against those files. Whatever batch
lands, make that test a deliverable rather than a side effect — it is the only
change here that prevents the next drift.

### 2.7 What I checked and found the inspector got right

Recorded so the synthesizer does not re-litigate: the proposal's "judged clean"
list was spot-checked on `_apply_policy_scope` invocation sites, `_selected_refs`
dedupe-without-sort, `_admit_route` ordering before `build_evidence`, and
`_estimate_tokens`' CJK-safe byte divisor — all four hold as described. The
inspector's stated limitations (unexecuted proofs, unmeasured churn rates,
unread modules) were accurate and honestly declared; the reproduction above
closes the two gaps it explicitly flagged for a red-teamer.
