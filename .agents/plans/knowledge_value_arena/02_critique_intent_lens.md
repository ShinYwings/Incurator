# Critique: `intent_vs_behavior` (§5.2) + `curation_lens_persona` (CAND-06, Global Persona)

Red-teamer role. Read in full: `01_proposal_intent_vs_behavior.md`,
`01_proposal_curation_lens_persona.md`. Read-only. No code, doc, config,
vault, or DB mutation performed. DB read via `?mode=ro`. Three additional
`wiki plugin context fetch` calls were run against the live vault (all
read-path, non-mutating), exactly as pre-authorized by `00_problem.md` Ground
Rule 1 and requested by the assignment — commands and output are reproduced
verbatim below.

---

## A. INTENT §5.2 — "hallucination-free answers by leveraging only the refined essence of curated knowledge"

### A1. Is judging `about.md` as a falsifiable claim fair?

**Ruling: fair, for §4/§5 — not fair, and not attempted, for §1–3.**

`about.md` is not uniform. §1–3 ("Core Philosophy," "Problems with Existing
Systems") are aspirational/thesis prose in future- or should-tense ("The
ultimate goal... is designed to automate," "we must avoid..."). Those are not
falsifiable and neither proposal under review tried to test them — correctly.

§4 ("Architecture: The Curator and The Artist") and §5 ("The Core of the
System: Knowledge Compiler") switch register entirely. They are written as
present-tense, declarative descriptions of what the running system currently
does: "the Curator **applies** the workspace KRS **as** a dynamic retrieval
lens," "the agent **retrieves** a bounded, traceable evidence pack," "Agent
response quality... **improve** because a project-specific Curation lens
**selects** bounded evidence... **providing** hallucination-free answers **by
leveraging only** the refined essence." Every verb is indicative-mood,
present-tense, mechanism-naming. This is architecture documentation wearing a
philosophy-folder path, not aspiration.

Two independent reasons this is fair to hold to a testable standard, not just
"vibes":
1. `CLAUDE.md`'s own contract: "Docs-First Development... Implementation and
   docs must always be in sync." That rule does not carve out an exception for
   `docs/philosophy/`; it says "the relevant doc file," and §4/§5 are the
   relevant doc file for the Curation/retrieval behavior under test.
2. This exact audit was commissioned by the user asking "did we ever check the
   system against `about.md`... its stated purpose" (`00_problem.md` lines
   6–10). Ruling §4/§5 unfalsifiable-by-genre would nullify the audit's own
   mandate before it starts.

So: the `intent_vs_behavior` proposal's practice of grading §4.3/§5.2/§4/§5.6
as TRUE/FALSE/PARTIALLY-FALSE is methodologically sound. This part of the
proposal survives red-teaming without modification.

### A2. Steelman: does "refined essence" plausibly mean L2, not just L3/L4?

This is the strongest attack available, and it is stronger than the original
proposal credited. Traced the actual code:

- `backend/src/curator/pipeline/graph_index.py:59-134` — `extract_graph_data(units)`
  where the docstring at line 73 states explicitly: **"`units` are
  `knowledge_units` rows"**. `graph_entities` and `graph_relations` — the
  `kind: "entity"` items in every measured pack — are LLM-synthesized
  *downstream of L2 knowledge_units*, not raw text.
- Verified live: `ENT-44c813e8` "Kruppa equations (method)" →
  *"Equations that relate the dual image of the absolute conic across
  multiple views"* (from my own `--workspace-path` test run below) is a real
  abstraction, not a quote — matches the proposal's own Q1 ellipsoid example.
- `db_sync.py:174-186`, `lint.py:464` confirm `knowledge_units` **is** the L2
  layer (`02_Atoms/ATM-*.md` is its projection, per `pipeline/projection.py:44`:
  *"Render an ATM page (the projection of one knowledge_unit)"*).

So the entity items are genuinely L2-refined, not a stretch. But I went
further than the proposal did and checked what the **`search_hit`** items
actually resolve to underneath the generic `kind: "search_hit"` label the
proposal treated as uniformly "flat/raw." Cross-referenced every `search_hit`
item's `item_id` prefix against `search_documents.record_type` in the live DB
(`.cache/vaults/13ed51f8b06cb88e/state.sqlite`, `?mode=ro`):

```sql
select record_type, record_id from search_documents
where record_id in ('ENT-955b26af','REL-3f5eafd6','REL-7f8fff31');
-- graph_entity|ENT-955b26af
-- graph_relation|REL-3f5eafd6
-- graph_relation|REL-7f8fff31

select record_type, record_id, projection_path from search_documents
where projection_path like '%2982af2e%';
-- knowledge_unit|KNU-44380335|02_Atoms/ATM-2982af2e.md

select record_type, record_id, projection_path from search_documents
where projection_path like '%4de012f6%' limit 5;
-- source_span|SPAN-...|01_Contexts/CTX-4de012f6.md  (×N — CTX-prefixed hits are raw spans, confirmed)
```

Result: `02_Atoms/ATM-*` search hits are `knowledge_unit` (L2, refined).
`graph_entity/ENT-*` and `graph_relation/REL-*` search hits are also L2
(same `extract_graph_data(units)` provenance as the first-class entity
items). `01_Contexts/CTX-*` search hits are `source_span` (L1, raw — the
Context grouping is cosmetic; the indexed record is the raw span). And
`04_Synthesis/SYN-e91665d4.md` (q4 only) is `synthesis_node` — genuine L4
(see A4).

Recomputed actual layer composition per pack, combining `kind:"entity"` +
dereferenced `kind:"search_hit"` + `kind:"source_span"`:

| pack | L1 (raw span) | L2 (entity/relation/knowledge_unit) | L3 | L4 | L2 fraction |
|---|---|---|---|---|---|
| q1 (39 items) | 26 | 13 | 0 | 0 | 33.3% |
| q2 (19 items) | 17 | 2 | 0 | 0 | 10.5% |
| q3 (35 items) | 26 | 9 | 0 | 0 | 25.7% |
| q4 (58 items) | 32 | 25 | 0 | 1 | 43.1% (+1.7% L4) |

This is a real, DB-verified correction to the original proposal, which
under-sold its own case by treating all `search_hit` items as generically
"raw L1" — some are genuinely L2. The steelman has real teeth: 10.5%–44.8%
of each pack's content is authentically refined (L2), not zero.

### A3. Does the steelman rescue the claim? No — and the reason is precise, not hand-wavy.

Three things survive the steelman and keep the verdict at FALSE:

1. **`about.md` §1 defines "refinement" as a pipeline that culminates in
   Concept/Synthesis, not Atoms**: *"prior knowledge is developed through a
   summarization/refinement process of 'Summarization ➡️ Atomization ➡️
   Concept Creation ➡️ Synthesis of Concepts.'"* The document's own vocabulary
   treats L3/L4 as the *end* of "refinement," and "essence" — a word that
   specifically connotes the most distilled, final form — reads far more
   naturally as "the Concept/Synthesis output" than "an intermediate Atom."
   The steelman borrows the word "refined" but not the word "essence"; L2 is
   refined, but it is not plausibly *the essence*.
2. **L1 (unrefined) is the majority in every single pack**, even under the
   most generous L2-inclusive counting: 66.7% (q1), 89.5% (q2), 74.3% (q3),
   55.2% (q4). §5.2 says "leveraging **only** the refined essence" — "only"
   is an exclusivity claim, and a claim of exclusive reliance on refined
   material is directly falsified by a majority-raw pack, regardless of where
   you draw the "refined" line.
3. **L3 is not merely under-represented, it is categorically absent** — 0 of
   233 live community reports surfaced in any pack through *any* path
   (first-class `community_report` kind, or dereferenced `search_hit`). This
   is the layer §1's pipeline names as "Concept Creation," immediately before
   "Synthesis" — i.e., squarely inside any reasonable reading of "essence." Its
   total absence, not partial under-representation, is what "refined essence"
   most directly promises and most directly fails to deliver.

**Ruling: FALSE stands**, not OVERSTATED-BUT-DEFENSIBLE — but on a corrected,
narrower basis than the original proposal argued. The original proposal's
"0/4 packs contain a single `community_report` or `synthesis` item" framing
is true and remains the sharpest single fact (L3 = 0/233 reachable, L4 =
1/4 nodes reachable and only via an unlabeled leak), but its supporting
claim that everything else is undifferentiated "raw L1 spans + unranked
flat FTS search_hits" is imprecise — a meaningful slice of `search_hit`
content is real L2. The correct FALSE argument rests on "only" + L1-majority
+ L3-zero, not on "0% refined."

### A4. Verify the q4.json L4 leak (`synthesis_node_id: ""`, score 0.016)

**CONFIRMED, exactly as described, and traced one layer deeper than the proposal did.**

The item exists verbatim in `q4.json`:
```json
{
  "item_id": "04_Synthesis/SYN-e91665d4.md",
  "kind": "search_hit",
  "synthesis_node_id": "",
  "score": 0.016129032258064516,
  "title": "Kernel Fusion and Memory Optimizations in High-Performance Gaussian Splatting Pipelines",
  ...
}
```
DB check confirms this is not coincidental naming — it is the actual L4 node,
verbatim opening sentence matches:
```sql
select id, title, substr(statement,1,300) from synthesis_nodes where id='SYN-e91665d4';
-- SYN-e91665d4|Kernel Fusion and Memory Optimizations in High-Performance Gaussian Splatting Pipelines|Consolidating execution steps into fused CUDA kernels...
```
and `search_documents` independently tags it correctly:
```sql
select doc_id, record_type, record_id, source_id, projection_path from search_documents
where record_id like '%SYN-e91665d4%';
-- DOC-synthesis_node-SYN-e91665d4|synthesis_node|SYN-e91665d4|14|04_Synthesis/SYN-e91665d4.md|Kernel Fusion...
```

**New finding, strengthening the original**: the `record_type = "synthesis_node"`
tag *is* known to the retrieval engine at hit time —
`backend/src/curator/retrieval/engine.py:35-43` (`EngineHit`) carries a
`record_type: str` field, populated at `engine.py:203-204` directly from the
DB row, and even threaded through as `family=data["record_type"]` at line 350.
But `backend/src/curator/search.py:255-266` (`query()`, building the public
`SearchHit` dataclass returned to callers) drops it — `SearchHit`
(`search.py:49-59`) has no `record_type`/`record_id` field at all, only
`docid` (a "legacy content-hash short id"). `evidence.py:219-224`
(`_search_hits`) then constructs `EvidenceItem(kind="search_hit", ...)` with
no way to recover the original record type, so `synthesis_node_id` defaults
to `""`. This is not a hard architectural gap — the fix is a one-line
plumbing change (surface `record_type`/`record_id` on `SearchHit`, branch on
it in `evidence.py`), not a redesign. Proposal's Finding 3 is **CONFIRMED**
and its severity (P2) is appropriately calibrated — it is a real traceability
bug, not a P1, since the content itself did reach the agent (just
mislabeled/unprivileged in the summary counters).

---

## B. LENS — CAND-06 ("chat sidebar can never bind a workspace KRS")

### B1. Current-code verification

`plugin/src/ui/chat/ChatSidebarView.ts:1904` on current master (`02faa0a`,
checked live, file is 5003 lines, line number unchanged from the proposal):

```ts
1903  if (client.available && query.trim()) {
1904    const wsPath = (this.app.vault.adapter as any).getBasePath();
```
and 1924-1930:
```ts
1924    const contextPack = await this.timedContextCall(
1925      "curator_context_fetch",
1926      wsPath || "default",
1927      () => client.fetchContext(query, {
1928        workspacePath: wsPath,
1929        limitTokens: packLimit,
1930      })
1931    );
```
**CONFIRMED verbatim, unchanged.** `getBasePath()` is the Obsidian vault
adapter's root path API; it is not `01_Workspaces/<project>`.

### B2. Other paths where a workspace IS passed

The assignment asked specifically about MCP, CLI `--workspace`, and the Quick
Query popover.

- **MCP: YES, a real path.** `backend/src/curator/mcp/server.py:3227`
  `curator_fetch_context(query: str, workspace_path: str = "")` accepts an
  arbitrary `workspace_path` and forwards it unmodified to
  `QueryOrchestrator(paths, client).fetch_context(QueryRequest(...,
  workspace_path=workspace_path))` (`orchestrator.py:39`), which calls
  `curate_yml.resolve_curate_policy(request.workspace_path)` at
  `orchestrator.py:208` — the identical policy-resolution function the plugin
  CLI path uses. This is not incidental: the MCP server's own top-level
  `instructions` string, injected into every connected agent's system prompt
  (`mcp/server.py:697-718`), states as protocol: *"SEARCH PROTOCOL: — Always
  pass `workspace_path` to `search_curator` / `curator_fetch_context`."* This
  is a documented, protocol-enforced entry point for any MCP-connected agent
  (Claude Code, Claude Desktop, Cursor, etc.), not a theoretical one.
- **CLI `--workspace-path`: YES, empirically confirmed working (see B3).**
- **Quick Query popover: does not use this path at all.**
  `plugin/src/ui/quickQueryPopover.ts` — its own doc comment (line 27) says
  *"This behaves like a lightweight `wiki query` for the selected passage"*;
  `grep -n "fetchContext\|workspacePath\|01_Workspaces"` on both
  `quickQueryPopover.ts` and `context/quickQueryContext.ts` returns zero
  hits. It is a separate, simpler mechanism (selected text + question →
  direct LLM call) that never touches `curate_yml`/KRS at all. It is neither
  a counter-example nor supporting evidence for CAND-06 — it's orthogonal.

### B3. Root-cause test: is `workspace_id="default"`/`policy_hash=""` in q1–q4.json caused by the measurement methodology (no `--workspace-path` passed) rather than the plugin defect?

Ran exactly the comparison the assignment specified, plus a third control
arm to settle it definitively. All three commands and their full output:

```
$ .venv/bin/wiki plugin context fetch --query "Kruppa Equation의 제약 조건과 한계는?" --limit-tokens 4000
policy_hash: ''   workspace_id: 'default'

$ .venv/bin/wiki plugin context fetch --query "Kruppa Equation의 제약 조건과 한계는?" \
    --workspace-path "/Users/shin/shinywings/second_brain" --limit-tokens 4000
policy_hash: ''   workspace_id: 'default'

$ .venv/bin/wiki plugin context fetch --query "Kruppa Equation의 제약 조건과 한계는?" \
    --workspace-path "/Users/shin/shinywings/second_brain/01_Workspaces/COLMAP free GS" --limit-tokens 4000
policy_hash: '61598094d334e434'   workspace_id: 'COLMAP free GS'
```

**Answer: no, methodology is not the real cause — but not for a trivial
reason.** Run 1 (no flag) and Run 2 (`--workspace-path` = vault root, i.e.
*exactly* what `ChatSidebarView.ts:1904`'s `getBasePath()` would supply) are
**byte-identical**: `policy_hash=""`, `workspace_id="default"` in both. This
is not a coincidence — `curate_yml.resolve_curate_policy()`
(`curate_yml.py:663-674`) treats a falsy `workspace_path` and a truthy path
with no `curate.yml` at it identically: both fall through to
`load_curate_spec(workspace) is None` → the same default-policy branch. Since
`curate.yml` lives only at `01_Workspaces/COLMAP free GS/curate.yml`, not at
the vault root, "the operator forgot `--workspace-path`" and "the plugin
passes the vault root" are **the same failure mode**, not competing
explanations — they are code-proven to produce identical output. So the
q1–q4.json packs, despite being generated via a bare CLI call rather than a
literal ChatSidebarView.ts replay, are legitimate stand-ins for what the real
chat-sidebar bug produces. The measurement methodology does not weaken this
finding.

Run 3 is the real news: it proves the underlying lens mechanism is not
broken in general — given any path that actually contains a `curate.yml`,
`resolve_curate_policy` correctly returns a non-empty hash and the real
workspace id, and this is a live, currently-functioning code path, reachable
by any CLI invocation or MCP tool call today.

### B4. Ruling

**CAND-06 chat-sidebar defect: CONFIRMED**, unmodified from the proposal.
`ChatSidebarView.ts:1904`'s `getBasePath()` really does always return the
vault root, that really is behaviorally identical to an unbound query, and
the code comment at lines 1914-1916 really does misdescribe this as an
intentional safety branch rather than the only branch that ever executes.
This is real, unfixed, and P1-appropriate for the exact reason the proposal
gives (Q1/Q2 are real user questions that fall inside a workspace whose
`curate.yml` was written for exactly this domain, and it never bound).

**The proposal's *up-front verdict* framing is DOWNGRADED, not the
finding itself.** Two specific oversells in `01_proposal_curation_lens_persona.md`'s
"Verdict up front" section:

1. *"§4 ... FALSE on the chat surface (the only surface a user actually
   queries through)."* — This over-narrows what counts as "a user." The
   architecture doc under test in this very audit (`about.md` §4) defines the
   Artist's primary consumer as **"The Agent: A high-reasoning agent resides
   in the workspace as a human assistant"** which **"retrieves a bounded,
   traceable evidence pack"** (§4.3) — i.e., the MCP-agent path *is* the
   canonical consumer this architecture was designed around, not a footnote.
   Dismissing MCP as not "a surface a user actually queries through"
   contradicts the very doc section the claim is testing. The correct,
   narrower claim: the chat sidebar (the one surface with zero setup
   friction for a human typing directly into Obsidian) cannot bind a
   workspace; MCP-mediated agent use (the surface `about.md` §4 actually
   describes) can and does, provided the calling agent supplies
   `workspace_path` as its own system prompt instructs it to.
2. *"TRUE only on a dead/unreachable code path."* — Empirically false, per
   B3 Run 3 above. The path is live, currently exercised correctly when given
   real input, and reachable today via CLI and MCP. What's actually missing
   (correctly identified by the proposal's own Finding 4 — no plugin-side
   `01_Workspaces` concept, `getCuratePlan()` called only by its own test,
   confirmed independently by me via the same greps) is a **discovery/picker
   UI** on the one human-facing surface, not a dead backend. "Unreachable
   without a workspace picker in the chat UI" is accurate; "dead code" is
   not — dead code doesn't return a correct 8-character policy hash from a
   correct workspace_id on the first real invocation.

Net effect: CAND-06 the *specific defect* is fully alive and correctly
diagnosed. The broader claim that follows from it in the write-up ("the lens
is never implemented," "true only on a dead path") overreaches the evidence
and should be narrowed to: *implemented and working end-to-end on the
CLI/MCP path; not implemented (no binding logic, no picker) on the one
human-typing-in-Obsidian surface.*

---

## C. LENS — Global Persona never reaches any answer the user reads

### C1. Grep verification, run independently

```
$ grep -rn "get_curator_persona\|curator_persona\b" backend/src/curator/*.py backend/src/curator/**/*.py | grep -v test_
backend/src/curator/config.py:346:def get_curator_persona(config: dict) -> dict:
backend/src/curator/sync.py:756:    curator_persona = cfg.get_curator_persona(cfg.load_config(paths))
backend/src/curator/sync.py:757:    domain_context = curator_persona.get("text", "")
backend/src/curator/commands/common.py:2540:    persona = cfg.get_curator_persona(config)   # `wiki persona show` — pure CLI display, no retrieval
```
**CONFIRMED exactly as proposed.** The only two production call sites are
`sync.py:756-757` (`run_mode_c`, DAG logical-deduction verification — an
internal maintenance pass, per `sync.py:736-757` and its callers at
`commands/core.py:1234,1262`) and `commands/common.py:2540`
(`_show_curator_persona`, a `wiki config persona show`-style CLI printer that
reads the persona back to the terminal — display only, feeds nothing
downstream).

```
$ grep -rn "persona" backend/src/curator/query.py backend/src/curator/context_service.py \
    backend/src/curator/retrieval/orchestrator.py backend/src/curator/retrieval/evidence.py \
    backend/src/curator/retrieval/router.py backend/src/curator/prompting/families/query.py
(zero output)
```
**CONFIRMED — zero matches**, run exactly as the proposal describes it, same
six files.

### C2. Query synthesis prompt family — read directly

`backend/src/curator/prompting/families/query.py:68-95`:
```python
class QueryLocalAnswerInput(BaseModel):
    question: str
    evidence_block: str
    valid_span_ids_block: str
    final_output_language: str = "English"

LOCAL_SYSTEM = """\
You are the Curator answering a precise question from grounded evidence.
...
Return ONLY JSON: {"answer": "...", ...}"""
```
No persona field in the Pydantic input model, no persona interpolation in
the hardcoded system string. Same pattern confirmed for
`QueryGlobalReduceInput`/`GLOBAL_SYSTEM` immediately below it (lines
113-140-ish). Confirmed single call site for both:
```
$ grep -rn "query_local_answer\|query_global_reduce" backend/src/curator/*.py backend/src/curator/**/*.py | grep -v test_
backend/src/curator/prompting/families/query.py:173:  prompt_id="curator.query_local_answer",
backend/src/curator/prompting/families/query.py:191:  prompt_id="curator.query_global_reduce",
backend/src/curator/retrieval/orchestrator.py:102-103: "curator.query_global_reduce" if ... else "curator.query_local_answer"
```
One producer (`prompting/families/query.py`), one consumer
(`retrieval/orchestrator.py`), zero persona plumbing anywhere in the chain.
This is the prompt family behind `wiki query`, MCP `curator_query`, and any
chat-sidebar backend-synthesized answer — i.e. every surface, not just chat.

### C3. Ruling

**CONFIRMED, no downgrade.** Unlike CAND-06, there is no alternate reachable
path here to soften the finding — I checked the MCP/CLI-equivalent angle on
purpose (the same angle that saved part of CAND-06) and it does not apply:
`curator_query` (MCP) and `wiki query` (CLI) both route through the identical
`orchestrator.py:102-103` call site with the identical persona-less input
models. There is exactly one production consumer of `get_curator_persona()`
(`sync.py` Mode C) and it is architecturally disconnected from every
answer-producing path. The proposal's framing — "Global Persona... reaches
only `wiki sync` Mode C verification prompts, never the answer-synthesis
prompt the user reads" — is accurate without qualification and I could not
construct a steelman against it that survives a source read.

---

## Verdict Table

| # | Finding (source doc) | Verdict | Severity | Note |
|---|---|---|---|---|
| 1 | §5.2 "hallucination-free... refined essence" is FALSE (`intent_vs_behavior`) | **CONFIRMED**, corrected reasoning | P1 | Steelman (L2 knowledge_units = refined) is real and DB-verified (10.5–44.8% of pack content is genuine L2, not the "0%" the original write-up implied) — but doesn't rescue the claim: "essence" tracks §1's pipeline endpoint (L3/L4, not L2), raw L1 is the majority in every pack (55.2–89.5%), and L3 (Concept layer) is categorically 0/233 through any path measured. FALSE stands on "only" + L1-majority + L3-zero, not on the original's less precise "0% refined" framing. |
| 2 | q4.json L4 leak: `synthesis_node_id:""`, score 0.016, item is real L4 (`intent_vs_behavior` Finding 3) | **CONFIRMED**, strengthened | P2 | Item verified verbatim in q4.json and cross-checked against live `synthesis_nodes`/`search_documents` tables — genuine SYN-e91665d4 content, `record_type="synthesis_node"` already known internally at `engine.py:35-43,203-204` but dropped when `search.py:255-266` builds the public `SearchHit`. Root cause is a one-line plumbing gap, not an architectural one — fix scope is smaller than the proposal implied. |
| 3 | Is `about.md` fair to test as falsifiable? (meta-question) | **Fair for §4/§5, not for §1–3** | — | §4/§5 are present-tense mechanism descriptions, not aspiration; `CLAUDE.md`'s docs-sync mandate and this audit's own charter both support testing them. |
| 4 | CAND-06: chat sidebar always passes vault root, KRS never binds on that surface (`curation_lens_persona` Finding 1) | **CONFIRMED**, unmodified | P1 | `ChatSidebarView.ts:1904` verified unchanged on current master; live 3-way CLI test proves passing the vault root is byte-identical to passing nothing (`policy_hash=""`, `workspace_id="default"` in both), so the measured q1–q4.json packs are valid evidence for this exact bug, not a methodology artifact. |
| 5 | "§4 FALSE... the only surface a user actually queries through" / "TRUE only on a dead/unreachable code path" (`curation_lens_persona` verdict framing) | **DOWNGRADED** | was P1 framing → narrow to P1 defect + P2 discoverability gap | Empirically refuted "dead": live test with `--workspace-path` pointed at `01_Workspaces/COLMAP free GS` returned `policy_hash="61598094d334e434"`, `workspace_id="COLMAP free GS"` on the first try — a working, unmodified code path. MCP `curator_fetch_context(workspace_path=...)` is a documented, protocol-mandated entry point (`mcp/server.py:697-718`), and `about.md` §4.3 itself names the workspace-resident Agent, not the chat sidebar human, as the canonical evidence-pack consumer. Correct scope: broken/unreachable on the one human-typing-in-Obsidian surface (no binding logic, no picker UI — Finding 4 confirmed); alive and correct on CLI and MCP. |
| 6 | Global Persona reaches only `sync.py` Mode C, never any answer prompt (`curation_lens_persona` Finding 2) | **CONFIRMED**, no downgrade | P1 | Independently re-grepped the same six files (zero hits) and read `prompting/families/query.py` directly — no persona field in `QueryLocalAnswerInput`/`QueryGlobalReduceInput`, single call site (`orchestrator.py:102-103`) shared by CLI `wiki query` and MCP `curator_query` alike. Unlike CAND-06, there is no MCP/CLI escape hatch — checked specifically and found none. |
