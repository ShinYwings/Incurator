# Curation Rethink — is a static Exhibition the right abstraction?

The user asked, critically and correctly, whether the Exhibition (EXH) concept is
actually the best vehicle for curation's goal. This document thinks it through
from first principles and proposes a redesign. Treat the user's points as input,
not constraints — large changes are acceptable.

## 1. What curation is actually FOR

The reason this system can beat a generic "LLM wiki + RAG" is a single claim:

> The Curator can supply prior knowledge **tailored to a workspace's purpose**
> better than generic retrieval, so the Artist (workspace human + reasoning agent)
> builds on refined, relevant, cited knowledge instead of trawling raw text.

That is the whole value. Everything else (DAG, spans, graph, reports) is in
service of *high-fidelity, workspace-relevant grounding*.

## 2. The flaw in a STATIC Exhibition (the user's critique, sharpened)

The v0.2.x notion of EXH is a **pre-staged, frozen package**: at curate time the
Curator selects/synthesizes "the knowledge this workspace needs" into one
artifact, and the Artist reads that artifact.

Relevance, however, is **query- and conversation-dependent and evolving**. A
frozen package therefore:

1. **Under-recalls.** At turn N the agent may need prior knowledge that was not
   staged. If it is limited to the EXH, it simply cannot reach it — exactly the
   user's worry. The freeze pre-decides relevance and is wrong as soon as the task
   moves.
2. **Goes stale.** The DAG keeps refining (new sources, corrections, reports); a
   frozen EXH drifts from the live refined knowledge.
3. **Duplicates the DAG.** The EXH is a lossy copy of knowledge that already lives
   in the graph, creating a second thing to sync, GC, and de-pollute (the qmd
   corpus problem we just hit).

A knowledge system whose entire pitch is *high-fidelity grounding* should not
trade away recall and freshness for a one-time convenience. **The static
Exhibition is premature, lossy compression of "what this workspace needs."**

## 3. The fix: tailoring belongs at RETRIEVAL time, as a bias — not a pre-freeze

Keep the goal ("workspace-tailored prior knowledge"); move *where* the tailoring
is applied:

> **Curation = a workspace-tailored LENS over the entire refined DAG, applied
> dynamically per request — not a frozen gallery.**

The workspace's `curate.yml` (KRS) plus its accumulated memory become a
**retrieval/synthesis policy** that scopes, biases, ranks, and verifies every
query against the *full* refined knowledge. You get tailoring **and** full recall
**and** freshness — strictly better than a frozen package, and exactly what modern
agentic/GraphRAG retrieval does.

This is, notably, what the v0.3.1 `QueryOrchestrator` + `CurationPolicy` already
do. The redesign is mostly **reframing what we built and deleting the static-EXH
baggage**, not new machinery.

## 4. Two consumers, two products (the user's wiki-query vs Obsidian-agent point)

The user is right that these differ fundamentally:

- **`wiki query` (CLI)** — the caller wants a *final answer*. The backend LLM is
  the synthesizer: retrieve (KRS-biased) → synthesize → return answer + trace.
  Self-contained; no MCP.
- **Obsidian agent / external reasoning agents** — the agent *is* the Artist and
  has its **own reasoning LLM**. It does not want a backend-synthesized answer; it
  wants **curated prior knowledge** to reason over. So the backend's primary
  agent-facing product is a **curated context / evidence pack** (the tailored,
  refined, cited slice of the DAG), fetched via MCP, which the agent's LLM then
  uses.

So the backend exposes two surfaces over the *same* dynamic-curation core:

1. `fetch_curated_context(query, workspace)` → evidence pack (spans / units /
   entities / community reports / memory paths, all cited, KRS-biased). **No
   synthesis.** This is the main product for reasoning agents.
2. `answer(query, workspace)` → evidence pack **+ backend-LLM synthesis**. For
   `wiki query` and any caller that wants a finished answer.

(#2 is just #1 followed by the synthesis prompt — already how the orchestrator is
structured.)

## 5. "Memory", done right (the user's cache/memory idea, reframed)

The user's instinct — persist, per workspace, *how to bring prior knowledge based
on the conversation* — is valuable, but it should be **additive bias, never a
replacement package**. Per-workspace memory =

- (a) **curate.yml KRS** — explicit intent (domains, topics, disambiguation,
  avoid_merges, verification, output contract);
- (b) **accumulated insights / corrections / promotions** — learned truth from use
  (the v0.3.1 insight-candidate lifecycle + `02_Wiki` promotions);
- (c) *(optional, later)* a lightweight **retrieval memory**: which knowledge /
  queries recur for this workspace, used to bias ranking.

All three **bias** retrieval; none **freeze** it. All live in the DB / KRS, not in
a frozen EXH. This gives the user's "memory" benefit without the under-recall and
staleness of a static package. A frozen per-conversation "how to retrieve" cache
is the wrong shape — the conversation's needs are exactly what should stay live.

## 6. Is EXH-driven backprop correct?

Backprop should re-refine the **shared refined DAG** (knowledge_units / entities /
reports) in response to **corrections**, and corrections arrive from *use* (an
agent or human says "this generated claim is wrong / this is a later
interpretation"). That is correct and valuable — it is the self-healing compiler.

But it must be **EXH-independent**. Tying backprop to "editing a frozen EXH file"
is the weakest possible trigger: it depends on an artifact we are arguing to
remove, and it conflates "the workspace's frozen view" with "the shared truth".
The right trigger is a **correction event** (`curator_propose_correction` from any
interaction) → classify → patch generated nodes / create insight candidate,
source-truth-protected. The v0.3.1 `backprop_classifier` + `insight_lifecycle`
already do this; the `backprop_sync` EXH-reverse-parse path should be **dropped**.

## 7. What "Exhibition" becomes

Keep the Curator/Artist metaphor; redefine the Exhibition as the **live curated
context the Curator presents on request** (the evidence pack), not a persisted
gallery file. The only durable, human-facing artifacts remain **promotions to
`02_Wiki/`** — when a human/agent decides a synthesized insight is worth keeping,
they promote it (deliberate, not an automatic per-session dump). This preserves
the philosophy ("the Curator stages exhibits for the Artist") while fixing the
rigidity ("the staging is live and query-responsive, not frozen").

## 8. Concrete shape of the redesign

Keep (reframe):
- `QueryOrchestrator` = the dynamic curation engine. `CurationPolicy` = the
  workspace lens. `EvidencePack` = the curated context.
- Insight lifecycle + `02_Wiki` promotion = learned memory + durable human truth.
- Correction-driven backprop = self-healing DAG refinement.

Add:
- MCP `curator_fetch_context(query, workspace)` → evidence pack only (the main
  reasoning-agent product). `curator_query` keeps doing evidence + synthesis.
- Per-workspace memory as a retrieval **bias** input to the orchestrator (start
  with KRS + insight candidates; the recurrence memory is a later option).

Delete (no backward-compat per locked decision):
- Static/ephemeral **EXH markdown files** as a persistence mechanism, the EXH
  answer-cache, `lint.gc_ephemeral_exhibitions`, and the `backprop_sync`
  EXH-reverse-parse path. Sessionless Q&A returns answer + trace (no file); chat
  history stays in `sessions.json`. Optional answer cache, if wanted, is a DB
  table with TTL — never a vault file.

Specs/guides: redefine "Exhibition" as live curated context; document the two
surfaces (fetch context vs answer); remove the frozen-EXH/GC model. EN then KR.

## 9. Honest counterpoints

- **"But pre-staging saves tokens/latency."** Real, but solvable without freezing:
  cache the *evidence pack* per (workspace, query) in the DB with a TTL keyed on
  `curate_spec_hash` + DAG version, so it auto-invalidates on refinement. That is a
  cache of a *dynamic* result, not a frozen curation.
- **"A workspace wants a stable 'current briefing'."** Provide it as a *view*
  generated on demand from the live DAG (a `wiki curate` snapshot the human can
  read), explicitly marked as a point-in-time render — not the authoritative
  context the agent is limited to.

## 10. Status

PROPOSAL / discussion. This reframes curation from a frozen Exhibition to a
dynamic, workspace-tailored lens over the refined DAG, with a context-fetch
surface for reasoning agents and a synthesis surface for `wiki query`. Awaiting
the user's direction before any spec/code changes.
