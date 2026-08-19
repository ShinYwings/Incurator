# Proposal: `curation_lens_persona` — does §4 / §5.6 of about.md hold?

Inspector: `curation_lens_persona` | Domain: does `curate.yml` (Artist Persona/KRS)
and the vault Global Persona actually influence retrieval on a surface a user uses.

Read-only investigation. No mutation performed. Live vault read at
`/Users/shin/shinywings/second_brain` (read-only). Additional read-path calls run:
none beyond reading the pre-measured `q1.json`–`q4.json` packs already in this
folder (per Ground Rule 1, re-derivation of the measured facts was avoided).

## Verdict up front

- **§4** ("the Curator applies … `curate.yml` as a dynamic retrieval lens over
  the live DAG") — **FALSE on the chat surface** (the only surface a user
  actually queries through). TRUE only on a dead/unreachable code path.
- **§5.6 Artist Persona** ("overlays workspace-specific context … frame the
  same underlying facts in fundamentally different ways") — **FALSE**, same
  reason: the lens never binds.
- **§5.6 Global Persona** ("defines the identity of the Curator") — **FALSE**
  for every user-facing answer. The vault persona reaches exactly one prompt
  family, and it is not the answer/retrieval family — it's `wiki sync`'s
  internal DAG-verification pass, which the user never reads.

---

## Finding 1 — P1 — CAND-06 reconfirmed on current master: chat sidebar can never bind a workspace KRS

**Evidence.**
`plugin/src/ui/chat/ChatSidebarView.ts:1904`:
```ts
const wsPath = (this.app.vault.adapter as any).getBasePath();
```
This is the Obsidian **vault root** (e.g. `/Users/.../second_brain`), not a
`01_Workspaces/<project>` folder. It is then passed straight through at
`ChatSidebarView.ts:1927-1930`:
```ts
() => client.fetchContext(query, {
  workspacePath: wsPath,
  limitTokens: packLimit,
})
```
`curate.yml` lives **only** under `01_Workspaces/<project>/curate.yml` (confirmed
live: `/Users/shin/shinywings/second_brain/01_Workspaces/COLMAP free GS/curate.yml`
exists; `/Users/shin/shinywings/second_brain/curate.yml` does not). On the
backend, `curate_yml.resolve_curate_policy()` (`backend/src/curator/curate_yml.py:657-691`)
does `Path(workspace_path) / "curate.yml"`; when that file is absent it silently
returns the same empty default as an unset path:
```python
# curate_yml.py:670-674
spec = load_curate_spec(workspace)
if spec is None:
    if require_spec:
        raise ValueError(...)
    return compile_curate_policy(CurateSpec(project="default")), ""
```
So passing the vault root is **behaviorally identical** to passing `""` — the
KRS never loads.

**Measured, not re-derived** (per Ground Rule 1, reading the existing packs):
all four packs in this folder — including **Q1 and Q2, the two real questions
the user actually asked** — resolved with:
```
workspace_id: "default"
snapshot.policy_hash: ""
```
Q1 ("ellipsoid 형태의 quadric 은 어떻게 매트릭스로 표현되나?") and Q2 ("Kruppa
Equation의 제약 조건과 한계는?") land squarely inside the live workspace's own
KRS — `curate.yml`'s `knowledge.topics` lists "Quadric lifting" verbatim and
`persona.disambiguation_keywords` lists "dual quadric" / "Plucker lines"; the
persona's `goal` text is explicitly about quadric/Plucker-lifting geometry. This
is not an edge case — it is the exact domain the workspace KRS was written for,
and it never bound.

**Prior-audit status.** This exact defect was already found and named CAND-06
in `.agents/plans/system_defect_audit_arena/03_synthesis.md:91,292,502` (P2 at
the time), queued as batch B6/`v0.??.0` pending a product decision (Q7: "nearest
ancestor `curate.yml` from the active note" was the recommended answer). Git
history (`git log --oneline --all | grep workspace`) shows no commit implementing
that decision, and the code read above is current master @ `02faa0a`. **Still
unfixed.** Re-rated P1 here (not P2) because Ground Rule 4 in this briefing
defines P1 as "the product fails its stated purpose for a real user question" —
that is exactly what the Q1/Q2 measurement shows, not a hypothetical.

**Compounding: the code's own comment is wrong.** `ChatSidebarView.ts:1914-1916`:
```ts
// Run the knowledge-graph query for both in-workspace and plain vault
// chat. When wsPath is empty the backend resolves workspace_id=default,
// so a conversational chat never binds an unrelated workspace.
```
This frames "always defaults" as an intentional safety guard against binding
the *wrong* workspace. In reality `wsPath` is never empty (a vault is always
mounted, so `getBasePath()` is always truthy) — the comment describes a branch
that cannot execute in the chat surface, papering over the fact that chat
*cannot bind any* `01_Workspaces` KRS, correct or not.

**Test coverage.** `grep` finds no `*.test.ts` for `ChatSidebarView.ts` at all
(only `chatSidebarSource.test.ts`, a different, older file). No test would
catch a regression or a fix here.

**Failure scenario.** A researcher opens the vault, asks the exact question
their workspace's `curate.yml` was written to answer ("what's the Kruppa
Equation's constraint?" inside a workspace whose KRS lists "dual conic",
"pose estimation", `min_confidence: 0.60`, audience `researcher`,
`output_intent: researcher`). The KRS never loads. The pack returned is
identical to what a brand-new, un-onboarded vault with zero persona would
return. about.md's promise that "the same curation engine frame[s] the same
underlying facts in fundamentally different ways depending on the project's
goal" is not happening — there is exactly one, undifferentiated lens: none.

---

## Finding 2 — P1 — Global Persona never reaches any answer the user reads, on any surface

**Trace.** `grep -rn persona` across `query.py`, `context_service.py`,
`retrieval/orchestrator.py`, `retrieval/evidence.py`, `retrieval/router.py`,
and `prompting/families/query.py` returns **zero matches**. The only
production call to `cfg.get_curator_persona()` (`backend/src/curator/config.py:346-348`,
which reads `.curator/settings.yml`'s `persona` block) is:
```python
# backend/src/curator/sync.py:755-757, inside run_mode_c()
curator_persona = cfg.get_curator_persona(cfg.load_config(paths))
domain_context = curator_persona.get("text", "")
```
`run_mode_c` is `wiki sync`'s **Mode C — LLM logical-deduction verification**:
it re-checks whether existing CON/SYN nodes are still logically derivable from
their ATM/CON evidence (`sync.py:736-757`, invoked from `commands/core.py:1234,1262`).
`domain_context` only feeds `build_theme_logic_verify_messages` and
`build_curation_logic_verify_messages` (`backend/src/curator/prompts.py:756-803`),
prompts the user never sees output from directly — they produce pass/fail
verification gaps during background DAG maintenance, not an answer.

**The actual answer prompt has no persona slot.** The synthesis path used for
every `wiki query` / `curator_query` / chat-sidebar answer is
`curator.query_local_answer` / `curator.query_global_reduce`
(`backend/src/curator/prompting/families/query.py:68-119`). Their Pydantic
input models are:
```python
class QueryLocalAnswerInput(BaseModel):
    question: str
    evidence_block: str
    valid_span_ids_block: str
    final_output_language: str = "English"
```
and the hard-coded `LOCAL_SYSTEM` prompt (`query.py:82-95`) opens with a static
"You are the Curator answering a precise question from grounded evidence" —
no domain, no verification philosophy, no output_intent, no confidence
thresholds from `.curator/settings.yml`'s persona block (`area: STEM`,
`verification_philosophy: citation-and-derivation + ...`,
`output_intent: researcher`, `confidence.high_threshold: 0.9`, read live from
`/Users/shin/shinywings/second_brain/.curator/settings.yml`). None of it is
interpolated anywhere in this contract.

**Failure scenario.** about.md §5.6 says the Global Persona "defines the
identity of the Curator … residing in each vault" and that separating vaults
is "the one justified reason" to run more than one, because "each Curator
interprets and exhibits knowledge through a different expert lens." In
practice, two vaults with opposite personas (one `STEM`/`researcher`, one,
say, `Chef`/`generalist`) synthesize the **identical** `QueryLocalAnswerInput`
prompt shape for the same evidence — the only variable that differs is which
DB rows got retrieved, not how the Curator "interprets" them. The persona
interview (`wiki init`) collects real, structured data
(`verification_philosophy`, `confidence` thresholds, `disambiguation_keywords`)
that is then provably discarded for every query the user issues.

---

## Finding 3 — P2 — Even when a policy resolves, most of the compiled KRS is inert plumbing

**Evidence.** `CurationPolicy` (`curate_yml.py:519-543`) compiles 15 fields
from `curate.yml`. Grepping every consumer of each field outside `curate_yml.py`
itself:

| field | consumed at query/retrieval time? | where |
|---|---|---|
| `source_include` / `source_exclude` | **yes** | `retrieval/evidence.py:57-110` (`_apply_policy_scope`/`allows_source`) |
| `allowed_routes` / `exploration_enabled` | **yes** | `retrieval/router.py:54-77` |
| `max_explore_followups` | **yes** | `retrieval/orchestrator.py:214` |
| `min_confidence` / `high_threshold` | **no** in the ContextService/QueryOrchestrator path — 0 matches in `evidence.py`, `orchestrator.py`, `router.py` | only referenced in the separate `search_curator` MCP tool (`mcp/server.py:1926`) |
| `persona.domain`/`subdomain`/`disambiguation_keywords` → `boost_query()` | **no** in `curator_fetch_context`/`curator_query` (the measured path) | called only by `search_curator` (`mcp/server.py:1927`), a different, secondary tool that returns raw hits, not the evidence pack or answer |
| `avoid_merges` | **no** | `db/_entities.py:1259` accepts an `avoid_merges` parameter with a real merge-guard implementation, but `grep -rn "avoid_merges="` across the whole backend finds **zero call sites** that pass it — the guard exists and is dead |
| `contradiction_policy` | **no** | zero matches outside `curate_yml.py` |
| `prompt_profile` | **no** (never selects a prompt variant) | only round-tripped into metadata payloads (`mcp/server.py:3194,3221`, `commands/plugin.py:723,728`) |
| `backprop_enabled` | **no** at query time | same, metadata-only |

**Failure scenario.** Even a user who *did* somehow get a workspace path to
bind (e.g. calling `search_curator` directly from an external MCP client with
an explicit `workspace_path=`) gets `min_confidence`/`boost_query` bias on
raw search hits, but the moment they ask for the curated evidence pack
(`curator_fetch_context`) or a synthesized answer (`curator_query`) — the
two surfaces about.md actually describes as "the dynamic retrieval lens" and
"bounded, traceable evidence pack" — persona-domain boosting silently stops
applying and only the source include/exclude filter remains active.

---

## Finding 4 — P2 — No client-side concept of "workspace" exists to bind, even in principle

**Evidence.** The one code path that resolves a `CurationPolicy` correctly
with `require_spec=True` — i.e., it would actually fail loudly instead of
silently defaulting — is the CLI command `wiki plugin curate plan`
(`backend/src/curator/commands/plugin.py:706-738`, calling
`curate_yml.resolve_curate_policy(workspace_path, require_spec=True)`). Its
plugin-side counterpart is `IncuratorClient.getCuratePlan()`
(`plugin/src/agent/incuratorClient.ts:728-734`).
```
$ grep -rn "getCuratePlan(" plugin/src --include="*.ts"
plugin/src/agent/incuratorClient.ts:728:  async getCuratePlan(workspacePath: string): ...
plugin/src/agent/incuratorClientV031.test.ts:63,147: ...only test calls...
```
No UI component, command palette entry, or view in `plugin/src` calls
`getCuratePlan()`. Further, `grep -rn "01_Workspaces" plugin/src --include="*.ts"`
returns **zero hits** anywhere in the plugin — the plugin source has no
data model, setting, or UI affordance for "which `01_Workspaces/<project>` is
active." This is not just Finding 1's default-argument bug; it is the reason
Finding 1 cannot be trivially patched by changing one default. There is
nothing to bind *to* — no workspace picker, no "current workspace" state, no
per-note nearest-ancestor lookup. The prior audit's own synthesis document
reached the same conclusion independently, queuing CAND-06 as "its own batch
because its fix is a *product* decision about which workspace binds, not a
defect patch" (`system_defect_audit_arena/03_synthesis.md:123-124`).

**Failure scenario.** Suppose a future patch fixes only `ChatSidebarView.ts:1904`
to resolve a nearest-ancestor `curate.yml` — there is still no way for a user
sitting in `01_Workspaces/COLMAP free GS/Research Notes/foo.md` chatting
generally (not anchored to a specific note) to see or confirm which workspace,
if any, is bound to their current chat turn; §5.6's promise of persona
*framing being visible/attributable* has no UI surface to land on even after
a backend fix.

---

## Summary table

| # | Finding | Severity | Primary file:line |
|---|---|---|---|
| 1 | Chat sidebar always resolves `workspace_path` = vault root → KRS never binds on the surface the user actually uses (CAND-06, reconfirmed unfixed, now measured against real user questions) | P1 | `plugin/src/ui/chat/ChatSidebarView.ts:1904,1927-1930`; `backend/src/curator/curate_yml.py:663-674` |
| 2 | Global Persona (`.curator/settings.yml`) reaches only `wiki sync` Mode C verification prompts, never the answer-synthesis prompt the user reads | P1 | `backend/src/curator/sync.py:755-757`; `backend/src/curator/prompting/families/query.py:68-95` |
| 3 | Most compiled `CurationPolicy` fields (`min_confidence`, `high_threshold`, `avoid_merges`, `contradiction_policy`, `prompt_profile`, persona domain-boost) are dead at query time even when a policy does resolve | P2 | `backend/src/curator/retrieval/evidence.py:57-110`; `backend/src/curator/db/_entities.py:1259` |
| 4 | No plugin-side concept of "active workspace" exists at all — `getCuratePlan()` is called only by its own test, `01_Workspaces` is never referenced in `plugin/src` | P2 | `plugin/src/agent/incuratorClient.ts:728`; (absence, whole-repo grep) |

## What would make §4 / §5.6 true

1. Give the chat surface a real workspace binding rule (per prior audit Q7:
   nearest-ancestor `curate.yml` from the active note, or an explicit picker),
   and cover it with a `ChatSidebarView.test.ts` that asserts a non-default
   `workspace_path`/`policy_hash` when a note under `01_Workspaces/*/` is active.
2. Either wire the Global Persona into `QueryLocalAnswerInput`/
   `QueryGlobalReduceInput` (system-prompt injection, the same pattern already
   proven for `domain_context` in `prompts.py:756-803`), or narrow about.md
   §5.6's claim to say the Global Persona currently governs DAG verification
   (`wiki sync`), not query answering — the doc and the code must agree.
3. Either wire `min_confidence`/`high_threshold`/`persona.*`/`avoid_merges`
   into the `curator_fetch_context`/`curator_query` path the same way
   `search_curator` already does, or delete the unused fields from
   `CurationPolicy` so the schema stops promising bias it never applies.
