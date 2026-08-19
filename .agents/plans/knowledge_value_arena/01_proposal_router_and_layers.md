# Proposal: `router_and_layers` — why every question routed `local`, and what actually has to change

Inspector: `router_and_layers` | Read-only. No code/doc/config/vault mutation. DB read via
`file:<path>?mode=ro` (sqlite3 CLI) and via `db.connect()` (read path only — the sole
write observed is the one `query_traces` row `ContextService.context_fetch()` inserts
per call, the same instrumentation side effect the briefing already sanctions for
`wiki plugin context fetch`, produced here by one additional direct call to the same
function for the route-forcing test in Finding 4).

Restart note: a prior attempt at this domain was cut off before writing. Nothing
below reuses unverified claims from that attempt — every citation was re-read and
every runtime number in this file was produced by a command I ran in this session.

---

## 1. `choose_route` in full — is the regex the only path to `global`, and what's the fallback?

Full text read: `backend/src/curator/retrieval/router.py:48-87`. Five branches, evaluated
in strict order, and the function *always* returns a route — there is no "give up"
state:

1. **Explicit `--mode`** (`router.py:65-68`) wins if `request.mode != "auto"` and the
   route is policy-allowed. This is the *only* non-regex path to `global`/`explore`.
2. **`source_key` set** → `source-section` (`router.py:71-72`).
3. **`_EXPLORE_SIGNALS` regex** match, gated by `policy.exploration_enabled AND
   status.has_relations` (`router.py:77-78`).
4. **`_GLOBAL_SIGNALS` regex** match, gated by `status.has_reports` (`router.py:81-82`).
5. **Default: `local`**, unconditionally — even the `not status.has_entities` branch
   (`router.py:85-86`) still returns `local`, just with a different reason string.

**Graph-status thresholds do not gate `local`.** `graph_status()` (`router.py:32-45`)
computes three booleans via `COUNT(*) > 0` — no numeric thresholds anywhere. I queried
the live vault's real DB directly (see path-discovery note under Finding 4) and
confirmed all three are `True` today:

```
$ sqlite3 "file:$DB?mode=ro" "SELECT
    (SELECT COUNT(*) FROM community_reports WHERE retired_at IS NULL),
    (SELECT COUNT(*) FROM synthesis_nodes),
    (SELECT COUNT(*) FROM graph_entities WHERE resolution_state='canonical'),
    (SELECT COUNT(*) FROM graph_relations WHERE lifecycle_status='active');"
233|4|965|782
```

So on this vault, branches 3 and 4's status gates were never the blocker — `has_reports`
and `has_relations` were both satisfied for all four measured questions. The only gate
that ever fired was the regex not matching.

**Policy does not gate it either.** All four measured packs ran with `workspace_path=""`
(no `curate.yml` resolved — confirmed independently by `curation_lens_persona`'s
Finding 2). `resolve_curate_policy("")` (`curate_yml.py:663-667`) returns
`compile_curate_policy(CurateSpec(project="default"))`, whose `allowed_modes` defaults
to empty → `allowed = VALID_ROUTES` (all four routes) and `exploration_enabled=True`
(`curate_yml.py:95,354,581-583`). This is confirmed by the packs' own
`route_admission.admitted_routes: [explore, global, local, source-section]` with
`disabled_routes: []`. Policy was wide open; it never once forced local.

**The "ambiguous case" LLM router doesn't run.** The module docstring
(`router.py:5-6`) and `SYSTEM_BEHAVIOR.md:1644-1645` both describe an LLM router
(`curator.query_router`) as the escape hatch "for the ambiguous case." I grepped the
whole backend: `query_router` is registered as a prompt contract
(`prompting/families/query.py:157`) and referenced nowhere else. `choose_route` never
calls it. There is no ambiguous-case fallback — every query, however hard to classify,
falls through branches 1-5 to a keyword match or the unconditional `local` default.

**Answer:** regex-or-explicit-mode is the entire path to `global`/`explore`. Explicit
mode is CLI-only (`wiki query --route`, see Finding 3) and unreachable from every
surface a real user's question travels through. Graph status and policy were never
the blocker on this vault; they were already wide open.

---

## 2. Does `local` ever consult `synthesis_nodes` / `community_reports`? What does each route assemble?

**No — confirmed at two independent layers, not just "the function isn't called."**

**Layer 1 — the evidence-assembly code.** `evidence.py:441-448`, the entire `local`
branch of `build_evidence()`:
```python
# local: entities + their spans + search hits.
ent_items, span_ids = _entity_evidence(db_path, q)
pack.items.extend(ent_items)
pack.items.extend(_span_items(db_path, span_ids))
pack.source_span_ids = span_ids
_add_search_hits(pack, paths, q, limit)
```
`_report_items()` (`evidence.py:297-327`, queries `db.list_community_reports`) and
`_synthesis_items()` (`evidence.py:330-350`, queries `db.list_synthesis_nodes`) are
never called here. (`intent_vs_behavior`'s Finding 1 independently found the same
lines; I re-derived it from the code, not from their proposal.)

**Layer 2 — the search fallback can't reach them either, structurally.** `local`'s
third evidence source, `_add_search_hits()` → `search.query()`, is the FTS5/vector
hybrid engine. I grepped `search.py` (and `search_index.py`) for any reference to
`community_reports` or `synthesis_nodes`: zero hits. The DB-native search index is
built over `sources`/`source_spans` only. So even `local`'s generic keyword-search
fallback is *incapable* of surfacing L3/L4 content by any query, not merely
unconfigured to look there — the corpus it searches doesn't contain L3/L4 rows.
(A promoted-`02_Wiki/` *copy* of an L4 statement can still surface as a `search_hit`
if a human promoted it there as markdown — that's `intent_vs_behavior`'s Finding 3,
a different, indirect path, not `synthesis_nodes` being queried.)

This is a hard, two-layer exclusion: `local` cannot reach L3/L4 no matter how the
query is phrased, in any language, because neither of its two evidence sources is
wired to those tables.

**What each route assembles (full read of `build_evidence`, `evidence.py:361-448`):**

| route | assembles | L3/L4 access |
|---|---|---|
| `source-section` (382-392) | spans of one named source only | none |
| `global` (394-412) | `_synthesis_items(limit=6)` + `_report_items(limit=10, query-scored)`; falls back to `_add_search_hits` only if *both* are empty | full — this is the only route with unbounded-by-primer L3/L4 as primary evidence |
| `explore` (414-439) | entity-seeded memory paths (`mp.build_memory_paths`, depth 2) + a 3-report/3-synthesis "primer" + entity items; **no search-hit fallback at all** | bounded (primer of 3+3) |
| `local` (441-448) | entities + their spans + search hits | **none, ever** |

---

## 3. The key question: what has to change for a real question to reach the 233 L3 reports?

**Recommendation: (c), but not symmetric — (b) is necessary and does most of the
work; (a) is necessary but insufficient alone. Code and the SYSTEM_BEHAVIOR/guide
spec both have to move together toward the user's stated L4→L3→L2→L1 intent; the
current code and current spec already agree with each other (§17, `local` = "entity/fact
questions... expand to related claims/concepts/spans," `USER_GUIDE.md:848` says the
same) — so this is not a code-vs-spec bug, it's both of them implementing an intent
the user has since moved away from. I built and ran two direct tests to settle which
half of the fix actually moves the needle for the four real questions in the briefing.**

**Test A — does fixing only the language gate help Q1/Q2 (real, entity/fact-shaped
questions)?** No, and it cannot even in principle: Q1 and Q2 are genuinely
entity/fact questions ("how is a quadric expressed as a matrix," "what are Kruppa
Equation's constraints") — under *any* reasonable classifier, including a
hypothetical perfect multilingual one, these should route `local`, because they are
not asking for cross-source synthesis. Their failure to reach L3 is not a
misclassification; it's `local`'s contract (§2 above) that's the wall. Fixing (a)
alone leaves Q1/Q2 routing `local` forever, correctly, and still 0/233 L3 reports.

**Test B — does fixing only the regex's language coverage help Q3 (the one explicit
cross-source synthesis request)?** I tested this directly rather than assuming it:
```
seed_terms('2D GS가 3D보다 표면 재구성에 유리한 이유를 여러 논문을 종합해서 설명해줘')
  -> ['D', 'GS']
_GLOBAL_SIGNALS.search(...) -> False       (Korean, as already established)
_GLOBAL_SIGNALS.search(
  'Why is 2D GS more advantageous than 3D for surface reconstruction, '
  'please explain by synthesizing multiple papers') -> False   (the natural
  English translation of the SAME question)
```
Even a flawless translation still fails `_GLOBAL_SIGNALS`
(`overall|summar(?:y|ize|ise)|across (?:all|the)|in general|big picture|themes?|
landscape|state of` — "synthesizing multiple papers" matches none of these; "across"
alone doesn't count, only "across all"/"across the"). So (a) is not just
language-incomplete, it is keyword-taxonomy-narrow *in English too*. Translating
Korean to English, even perfectly, would not have routed Q3 to `global` either.

**Therefore:** the highest-leverage, language-independent fix is (b) — give `local`
(the route nearly every real question will take, correctly, regardless of language
or classifier quality) a bounded top-down slice of L3/L4, the same "primer" pattern
`explore` already uses successfully (`evidence.py:429-433`, 3 reports + 3 synthesis
nodes alongside its main evidence — this is not a new pattern, it already exists and
is already tested). This single change fixes Q1, Q2, Q3, and Q4 simultaneously and
is completely insensitive to what language the question was asked in, because it
does not depend on route classification at all. (a) should *still* be fixed — it is
an independent, real defect (Finding on the language bridge below) that keeps
`global`'s unbounded, better-suited synthesis path unreachable for non-English big-picture
questions like "what are the overall themes in my vault" — but fixing (a) alone
does not touch the four questions actually measured in this briefing.

**Which of code/spec/intent moves:** intent wins (per the briefing and per this
project's own rule: "any divergence means both are wrong until reconciled"). Both
`SYSTEM_BEHAVIOR.md:1651-1653` (`local` = "entity/fact questions... expand to related
claims/concepts/spans") and `USER_GUIDE.md:848` (`local` = "precise entity/fact
answers grounded in source spans") currently describe exactly what the code does —
they are internally consistent, just consistent with the wrong contract relative to
the user's stated intent. A `local`-contract change is therefore a **spec change**
(§17 + the guide line) that must land in the same PR as the code change, not a
code fix against an unchanged spec — this repo's `CLAUDE.md` "Docs-First
Development" and "Spec-First Version Development" rules require the
`docs/specs/system_behavior/SYSTEM_BEHAVIOR.md` contract to be rewritten first,
then `docs/guides/USER_GUIDE.md` (and its `_KR.md`) updated to match, before the
`evidence.py:441-448` branch is touched.

---

## 4. Does `global` actually work today? Forced-route test.

**No CLI flag on `wiki plugin context fetch`.** I read its full Typer signature
(`commands/plugin.py:558-578`): `--query`, `--workspace-path`, `--limit-tokens` only.
No `--route`/`--mode`. **`wiki query` does have `--route`**
(`commands/core.py:1353-1359`: `auto | local | global | explore | source-section`,
"Routes through the QueryOrchestrator... with a QTR trace"), but every real-user
surface I traced hardcodes `mode="auto"` and never exposes an override: the plugin's
`context fetch` JSON command (`plugin_api/context.py:37-41`), MCP
`curator_fetch_context` (`mcp/server.py:3243`), and MCP `curator_query` (no `mode`
param exists on `plugin_api.curator_query`, `plugin_api/query_api.py:94-103`). The
`--route` escape hatch exists only on the CLI, which is not the surface any of the
four measured questions came through.

**What I ran.** Since `wiki plugin context fetch` itself can't force a route, I called
the exact function it wraps — `ContextService.context_fetch()`
(`context_service.py:543`) — directly with `mode="global"` instead of the CLI's fixed
`mode="auto"`, using the real Q3 text against the real vault DB (path discovered via
`config.get_vault_cache_dir()`, since `<vault>/.curator/state.sqlite` is a stale
0-byte file — the live DB is machine-cached at
`.cache/vaults/<sha256(root)[:16]>/state.sqlite`, confirmed correct by cross-checking
`wiki status`'s live counts, 233 L3 / 4 L4, against a direct read-only `sqlite3`
query on that path, both matching). `context_fetch()` never reads `self.client`
(grepped — assigned in `__init__`, read nowhere else), so this needed no LLM call;
it is a pure retrieval-path call, the same class of operation as
`wiki plugin context fetch`, and writes the same one `query_traces` row.

```python
req = QueryRequest(
    question="2D GS가 3D보다 표면 재구성에 유리한 이유를 여러 논문을 종합해서 설명해줘",
    workspace_path="", mode="global",
)
ContextService(paths, client=None).context_fetch(req)
```

**Result:**
```json
{
  "route": "global",
  "route_reason": "explicit --mode",
  "coverage": {"sufficiency": "partial", "omitted_counts": {"global_reports": 223}},
  "num_items": 14,
  "community_report_ids_count": 10,
  "synthesis_node_ids_count": 4,
  "warnings": [],
  "item_kinds": ["community_report", "synthesis"],
  "sample_titles": [
    "Kernel Fusion and Memory Optimizations in High-Performance Gaussian Splatting Pipelines",
    "Hierarchical Paradigm Shift in Visual Localization and Feature Matching",
    "Integration of Structural Line Features and Quadric Primitives for Robust Multi-View Reconstruction and SLAM",
    "Surface Resampling and Prior Constraints for Accurate Geometry and Relighting in Radiance Fields",
    "Mip-Splatting Anti-Aliasing and CUDA Implementation Overview"
  ]
}
```
`global` correctly selected 10 of 233 community reports (capped by
`_MAX_GLOBAL_REPORTS`, `evidence.py:29`) and all 4 of 4 synthesis nodes (capped by
`_MAX_GLOBAL_SYNTHESIS=6`, `evidence.py:30`), with correct `omitted_counts`
accounting (233 - 10 = 223) and zero warnings. **This is the exact same question that
measured `route: local, L3: 0, L4: 0` in the established table** — a clean,
controlled A/B on identical input, differing only in route. `global`'s evidence
assembly is not broken; it is simply unreachable for this question by the router.
This closes off a plausible alternative hypothesis (that `global` is aspirational/
never-actually-tested code) — it works correctly on live data today.

---

## 5. Other language-dependent behavior on the query path

This is the deepest finding and the actual root-cause explanation for *why* Q1/Q2
(the two questions "recovered from `.curator/sessions.json`" — genuine user chat
turns, not synthetic tests) failed, beyond "the regex is English-only."

**`SYSTEM_BEHAVIOR.md` claims a deterministic language bridge that does not exist for
routing.** Line 876: *"Input-language detection is a deterministic, logic-level
step, not merely a prompt instruction."* Lines 1706-1707 (§17): *"the v0.2.2 language
bridge... is unchanged: detect latest-input language, reason in English, answer in
the detected language."* I traced this end to end:

- The Unicode-script detector genuinely exists and is deterministic:
  `plugin/src/context/languageBridge.ts:14-38` (`detectLanguage`, Hangul/Kana/Han/
  Cyrillic/etc. ranges), tested in `languageBridge.test.ts`.
- But its *only* production call site is `ChatSidebarView.ts:1574`, and its output
  feeds `wrapLatestUserMessageForLanguageBridge()` (`systemPrompt.ts:79-94`), which
  wraps the user's message with a **prompt string** for the sidechat's own LLM:
  *"Reason, search, and build MCP/tool arguments internally in English, then write
  the final answer in \[lang\]..."* This is exactly the "merely a prompt instruction"
  the spec explicitly says the mechanism is *not*. Whether an MCP tool-call argument
  (i.e. the query text that reaches `choose_route`) actually ends up in English
  depends entirely on whether the sidechat LLM complies with this instruction for a
  given turn — unverifiable, not guaranteed, and (per Test B in §3) wouldn't fix
  routing even if it always complied.
- `inferQueryLanguageMetadata()` (`languageBridge.ts:40-58`) — the function that
  *would* actually populate a translated `englishQuery` field per its own docstring
  ("the backend computes english_query") — is called nowhere in production plugin
  code, only in its own test file (`languageBridge.test.ts`). It is dead.
- On the backend, `translate_to_english()` (`query.py:160-186`) is likewise dead for
  every routing-relevant path. I grepped every caller: its only real invocation is
  inside MCP `curator_search` (`mcp/server.py:1929-1937`) — a flat-search tool that
  bypasses `choose_route` entirely and never touches `QueryRequest`. Every
  routing-relevant entry point leaves `QueryRequest.english_query` empty or a
  same-text passthrough:
  - `wiki plugin context fetch` → `plugin_api/context.py:37-41`: no `english_query`
    at all.
  - MCP `curator_fetch_context` → `mcp/server.py:3243`: no `english_query` at all.
  - MCP `curator_query` → `mcp/server.py:2019`: hardcodes
    `english_query=question, input_language="English"` **unconditionally** —
    literally labels the raw, un-inspected text "English" regardless of what
    language it's actually in, rather than detecting or translating anything.
  - CLI `wiki query` → `commands/common.py:2169-2175`'s `run_kwargs` never includes
    `english_query`; `run_query()`'s default is `None`.
  - Since `QueryRequest.working_query` (`models.py:35-36`) is `english_query or
    question`, every one of these leaves the router reading the **raw, untranslated
    original text** — confirmed, not inferred: none of the four measured packs could
    have had `working_query` be anything but the literal Korean/English the user
    typed, because no code on their call path ever writes to `english_query`.

**A second, independent language gap sits inside evidence assembly itself, below the
router.** `seed_terms()` (`evidence.py:188-196`, feeds `_entity_evidence()`, used by
both `local` and `explore`) and `_report_score()`'s term-overlap
(`evidence.py:292`, feeds `global`'s report ranking) both use ASCII/Latin-only
regexes (`[A-Za-z][A-Za-z0-9+\-]*` / `[a-zA-Z][a-zA-Z0-9+\-]*`). I tested this
directly:
```
seed_terms('ellipsoid 형태의 quadric 은 어떻게...')  -> ['ellipsoid', 'quadric']   # mixed: partial credit
seed_terms('이 개념의 핵심이 뭐야?')                    -> []                        # pure Korean: zero
```
Q1/Q2 happened to embed English technical terms ("ellipsoid," "quadric," "Kruppa,"
"Equation"), which is why their entity evidence wasn't *completely* empty (30/15 L1
spans each, per the established table) — but a pure-Korean question with no
embedded Latin technical vocabulary gets zero entity seeding on `local`/`explore`,
and `global`'s report relevance ranking degrades to `rank`-only ordering (no query
term ever overlaps). This is a second, independent failure mode from routing —
fixing the router does not fix this, and it would need its own multilingual
tokenization pass (e.g. run everything through the same translation the router
needs, once, upstream of both `choose_route` and `seed_terms`/`_report_score`,
rather than duplicating language handling in three places).

**By contrast, DB-native hybrid search (the `local`/`global` fallback,
`_add_search_hits`) is comparatively language-tolerant already** — Q1/Q2 did surface
real LaTeX-bearing spans (11 and 5, per the established table), most plausibly via
the vector leg of hybrid search (`llama-cpp::qwen3-embedding-0.6b` per `wiki
status` — a multilingual embedding model) rather than the FTS5/BM25 lexical leg,
which is not multilingual-tokenization-aware. I did not deep-dive FTS5's tokenizer
behavior on Hangul — that's a reasonable follow-up but secondary to the two
confirmed defects above, and partially overlaps `content_quality`'s assigned
territory (why spans/sufficiency look the way they do).

---

## Summary table

| # | Finding | Severity | file:line | Failure scenario |
|---|---|---|---|---|
| 1 | `local`'s evidence contract structurally excludes L3/L4 at **two** layers: `build_evidence()`'s `local` branch never calls `_report_items`/`_synthesis_items`, **and** the FTS5/vector search index it falls back to doesn't contain `community_reports`/`synthesis_nodes` rows at all. This is the root blocker for real entity/fact questions and is language-independent. | P1 | `evidence.py:441-448`; `search.py` (no `community_report`/`synthesis_node` reference); `SYSTEM_BEHAVIOR.md:1651-1653`; `USER_GUIDE.md:848` | User asks Q1/Q2 (real, correctly-`local`-routed entity/fact questions) in any language, under any router quality. Answer: 0 of 233 L3 reports, forever, until `local`'s contract itself changes. |
| 2 | `_GLOBAL_SIGNALS`/`_EXPLORE_SIGNALS` are narrow even in English, not just English-only: the natural English translation of Q3 ("...explain by synthesizing multiple papers") still fails to match `_GLOBAL_SIGNALS`. Fixing translation alone would not have routed Q3 to `global`. | P1 | `router.py:20-29`; verified live via `seed_terms`/regex test in §3 Test B | A native English speaker asks Q3's exact phrasing and still gets routed `local`, 0 L3/L4, identical to the Korean case. |
| 3 | The "deterministic language bridge" `SYSTEM_BEHAVIOR.md:876` and `:1706-1707` claim exists is, for the routing-relevant query argument, a soft LLM prompt instruction (`systemPrompt.ts:82`, "reason... internally in English") with no code-level enforcement — `inferQueryLanguageMetadata()` (the function that would actually translate) is called only in its own test file, and the backend's `translate_to_english()` is wired into exactly one tool (`curator_search`) that bypasses routing entirely. Every routing entry point leaves `QueryRequest.english_query` empty or a same-text passthrough. | P1 | `languageBridge.ts:40-58` (dead in prod); `systemPrompt.ts:79-94`; `mcp/server.py:1929-1937,2015-2020,3243`; `plugin_api/context.py:37-41`; `models.py:35-36` | A real user's Korean chat turn (Q1, Q2 — recovered from actual session history) reaches `choose_route` as raw Korean with no deterministic guarantee it was ever translated, contradicting the spec's explicit "not merely a prompt instruction" claim. |
| 4 | `global` route's evidence assembly is verified correct on the live vault when reached — forcing `mode="global"` on the exact Q3 text returns 10/233 community reports + 4/4 synthesis nodes, correctly capped and accounted, zero warnings. The defect is 100% on the selection side; nothing needs fixing in `global`'s evidence code. | Confirms scope | `evidence.py:394-412` (`_MAX_GLOBAL_REPORTS=10`, `_MAX_GLOBAL_SYNTHESIS=6`, `evidence.py:29-30`); live test in §4, command shown in full | Rules out "global is aspirational/broken" as an alternative explanation — narrows the fix entirely to routing + `local`'s contract. |
| 5 | `seed_terms()` and `_report_score()`'s term-overlap are ASCII/Latin-only regexes, a second and independent language-dependent gap beneath the router: a pure-Korean query with no embedded Latin technical terms gets zero entity-seeded evidence on `local`/`explore` and zero-overlap (rank-only) report scoring on `global`. | P2 | `evidence.py:188-196` (`seed_terms`), `evidence.py:292` (`_report_score`); verified live: `seed_terms('이 개념의 핵심이 뭐야?') == []` | A vault with mostly-Korean source material and a user who writes pure-Korean questions (no embedded English jargon) gets materially worse entity/report evidence than Q1/Q2's mixed-language phrasing already showed, on every route including a hypothetically-fixed `global`. |
| 6 | `choose_route` has no ambiguous-case fallback despite the module docstring and spec describing one: the registered `curator.query_router` LLM-router prompt contract is never invoked anywhere in the live retrieval path. Routing is 100% deterministic keyword-match-or-default, with the CLI-only `--route` flag as the sole non-regex escape hatch — unreachable from plugin/MCP, the surfaces real users actually use. | P2/P3 | `router.py:5-6` (docstring), `prompting/families/query.py:157` (registered, never called); `commands/core.py:1353-1359` vs. `plugin_api/context.py:37-41`, `mcp/server.py:2015-2020,3243` (no override exposed) | Any query the two regexes can't classify — in any language — silently falls to `local` with no smarter fallback and no way for a plugin/MCP caller to override it, unlike what the docstring/spec imply exists. |

---

## What I did NOT do

- Did not modify `router.py`, `evidence.py`, any spec, or any doc.
- Did not touch the vault's `.curator/state.sqlite` (confirmed stale/0-byte and
  unused by the app — noted as a side observation, not a finding, since it's outside
  this domain's scope and doesn't affect any measurement here: the app reads/writes
  the machine-cached DB at `.cache/vaults/<hash>/state.sqlite` via
  `config.WikiPaths.state_db`, confirmed by cross-checking `wiki status`'s live
  counts against a direct read-only query on that path).
- Ran exactly one additional retrieval-path call beyond what the briefing already
  sanctions (`wiki plugin context fetch`-equivalent, forced to `mode="global"` since
  no CLI flag exists on that specific command) — one `query_traces` row inserted,
  no other mutation, no LLM call.
- Did not re-run Q1/Q2/Q4 forced to `global`/`explore` — one controlled A/B (Q3) was
  sufficient to answer "does global work," and the briefing asked for one query.
