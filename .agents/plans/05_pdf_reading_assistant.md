# v0.54.0 Master Implementation Plan — The Reading Assistant

Date: 2026-08-09
Status: **AWAITING USER APPROVAL** — Arena concluded (briefing, role audit,
architect proposal, red-team critique, 6 convener verifications). No code written.
Arena record: `.agents/plans/pdf_reading_assistant_arena/`

## 1. Objective

Make sidechat and popover perform the role the user defined:

1. **Read with me** — papers and books, including pages and regions I have not opened.
2. **Remind me what I wrote** — surface my own notes unprompted when they bear on the question.
3. **Find new value** — say something from (1)+(2) I did not already have.

**Definition of done.** Selecting `[8] … Eq. (29)` in the popover and asking about
it yields: what paper [8] is, what equation 29 says, a pointer to my own note that
touches it — and no sentence about context, loading, or general knowledge.

## 2. Explicit Non-Goals

- **Not** a second retrieval engine. Vault-wide search goes through the DB-native
  FTS5/vector search that already exists; CLAUDE.md forbids adding search backends.
- **Not** raising `MAX_RECURSION`. The design must fit the existing budget (§4.2).
- **Not** granting the popover model MCP or filesystem tools. The zero-MCP
  guarantee holds (§4.3).
- **Not** persisting a new index.
- **Not** OCR of scanned books beyond the existing vision path.

## 3. Strict Quality Conditions & Release Gates

- The prompt stack **shrinks**: ≤ 17,000 chars (from 20,156) and ≤ 18 negative
  directives (from 24), enforced by a test with a hard ceiling.
- Zero prompt strings instruct the model to describe its context, its retrieval
  state, or the provenance of its knowledge.
- Each of the three duties has ≥ 1 explicit enabling instruction and no
  unqualified prohibition contradicting it (today duty 3 has **zero**).
- Popover still injects no MCP tools — asserted.
- Answering a `[8] + Eq (29)` question costs **0 extra tool rounds** (§4.2).
- Gates: vitest, `tsc --noEmit`, `scripts/backend-check ruff|mypy|pytest` green;
  every new behaviour has a test verified to fail without its fix.

## 4. Locked Design Decisions (Arena Consensus)

### 4.1 Route to pixels per REGION, using the signal we already store
The architect proposed gating vision on `PdfTextQuality.isScannedLike`. **Killed
by measurement.** That flag is a page aggregate
(`pdfTextLayout.ts:193-199`: `charCount < 20 || wordCount < 4 || …`), and the
real target — page 11, which holds equation 29 as a picture — measures
**3,354 chars / 855 words**, so it reads as healthy text and would never escalate.

The per-region signal already exists and is already stored: the parser emits
`**==> picture [W x H] intentionally omitted <==**` and `classify_span_loss`
classifies it. Measured: **12 such regions on page 11 alone, 132 vault-wide.**
Routing rule: *a region with a loss verdict is answered from pixels; everything
else from text.* No new classifier, no page-level guessing.

### 4.2 Resolve BEFORE the turn; do not make the model chase
`MAX_RECURSION = 5` (`LLMClient.ts:945`) is shared by all tool families, and the
last round strips tools. A 4-rung ladder plus depth-2 chaining cannot fit — the
red team is right that the proposal could not run.

It does not need to. `resolveSelectionReferencesAsync`
(`pdfReferenceContext.ts`) **already resolves references before the prompt is
built**, spending zero tool rounds. Citation resolution joins that path. The
model receives resolved content in `<resolved_cross_references>` and answers in
one turn. Tools remain for what genuinely needs the model's judgement.

### 4.3 The zero-MCP guarantee is about the MODEL's tools, not the plugin's calls
`shouldInjectMcpTools` returns false for `"local-only"` — the popover model gets
no MCP, and that stays. But a *local tool's implementation* already calls the
backend: `transcribePdfCrop` shells to `incuratorClient` today from plugin code.
So popover resolution runs in the plugin (which may call the backend), while the
model's surface stays local. The guarantee is preserved; the capability is not
blocked.

### 4.4 The prompt is re-posed around the three duties before capability is added
Measured (`A_prompt_role_audit.md`): duty 1 has 32 enabling / 13 limiting
sentences; duty 2 has 6/3 and **both** sentences that mention the user's notes
cancel themselves in the same breath ("…connect it to the user's existing notes,
**but avoid**…", "…**but you MUST NOT** explain the background context itself");
duty 3 has **no role instruction at all** — its four hits are MCP tool
descriptions. Adding tools under this prompt cannot surface duty 2 or 3.

### 4.5 Provenance comes from what was fetched, not from regexing the output
The architect's `[[wikilink]]` render check would fire "no citation" on every
popover answer — `quickQueryContext.ts` contains **zero** `[[` occurrences, so
that model is never told wikilinks exist. Provenance is instead assembled from
the resolution results the plugin already holds (which rung answered, which
page/paper), displayed as UI state.

### 4.6 The general-knowledge mandate is deleted, and its job is done structurally
`promptRegistry.ts:78-83` mandates the sentence the user quoted back at us,
example text included. It goes. Its honest purpose — letting the user tell
paper-content from model-knowledge — is served by 4.5, which cannot be argued
out of by a model mid-turn.

### 4.7 Vault coverage is fixed by ingestion, not by a second index
36 sources vs 137 markdown files. The architect's ephemeral vault-wide BM25 would
copy `upsertPage`'s rebuild-per-call shape (measured elsewhere at 331x linear).
Instead: ingest the missing files so the existing DB-native search covers them.

**AMENDED 2026-08-14 (user decision). "The missing files" is not all 103 of
them, and the two halves need different mechanisms.**

Measured breakdown of what is unindexed:

| location | files | disposition |
|---|---|---|
| `01_Workspaces/<project>/` research notes | 75 | **NOT ingested** |
| `01_Workspaces/<project>/.agents/` + `CLAUDE.md` | 14 | never — agent scaffolding |
| `03_Notes/` | 7 | ingest — `[Source]` per the vault contract |
| `00_System/` | 6 | ingest |
| `04_Resources/` | 2 | ingest — `[Source]` per the vault contract |

Workspace content does **not** enter the knowledge graph. `01_Workspaces` is the
Artist Space: project studios holding `curate.yml`, agent scaffolding, and
working notes bound to one project. Promoting that into a vault-wide DAG mixes
project-local working state into shared knowledge, which is the separation the
vault topology exists to maintain — and 14 of those files are agent machinery
that would be indexed as if the user had written them.

But the reader still wants those notes *consulted* when an answer is being
composed. That is a retrieval question, not an ingestion one: the agent reads
workspace files at query time, scoped to the active workspace, without any of it
becoming L1–L4. Ingestion and consultation are different mechanisms and this
plan had conflated them.

So P5 splits:
- **P5a** — ingest `03_Notes`, `00_System`, `04_Resources` (15 files). Needs LLM
  capacity; blocked while Antigravity returns 429.
- **P5b** — query-time workspace consultation, scoped to the active workspace,
  read-only, never written to the DAG. Needs its own design; it is a new
  retrieval path, not a change to an existing one.

### 4.8 `[8]` extraction is scoped to reduce collisions
Bare `[...]` collides with `[^8]` footnotes, `[text][8]` reference links, and
array indices. Extraction requires a bibliography match to survive: a citation
number that does not resolve against a parsed References section is dropped, not
rendered as unresolved.

## 5. Scope Exclusions & Stop Conditions

**Exclusions**: web/CrossRef lookup and multi-hop citation chaining are deferred
to a follow-up — they add a network egress boundary and a round budget this plan
deliberately does not spend. Depth-1 (this paper's own bibliography) only.

**Stop conditions — halt and ask:**
- The References section cannot be located within the existing page budget for a
  representative paper.
- Prompt rework cannot hit the §3 ceilings without dropping a real safety rule.
- Re-posing the prompt measurably worsens duty 1 (the model starts over-explaining
  whole documents again) — the regression the prohibitions were added to stop.
- Any change would require raising `MAX_RECURSION` or granting popover MCP.

## 6. Evidence Ledger

Verified 2026-08-09 against master (v0.53.2 + PR #152 pending):

- Prompt stack **20,156 chars, 24 negative directives** across four modules.
- Duty coverage 32/13, 6/3, 4/0 — duty 3 uninstructed.
- `promptRegistry.ts:78-83` mandates the general-knowledge sentence **with an
  example**; the user quoted it back verbatim.
- `MAX_RECURSION = 5`, shared, last round strips tools.
- `isScannedLike` is a page aggregate; page 11 = 3,354 chars / 855 words → false.
- **12 picture-region placeholders on page 11; 132 vault-wide** — the per-region
  signal exists already.
- `quickQueryContext.ts`: 0 occurrences of `[[`.
- `shouldInjectMcpTools("local-only") === false`.
- Vault: 36 ingested sources vs 137 markdown files.
- Vision route proven: `claude-code::claude-sonnet-4-6` returned equation 29's
  LaTeX verbatim from a page render; it is now stored as `SPAN-df48323a`.

**Rollback**: plugin TypeScript + prompt strings; no schema change. Anchor is
master at the branch point.

## 7. Execution Phases (TDD + CI each phase)

- **P0 — Prompt re-pose.** Rewrite the stack around the three duties: delete the
  general-knowledge mandate, remove the self-cancelling clauses on duty 2, add
  duty 3's first instruction. *Verify: the §3 ceilings hold as a test; duty
  coverage re-measured; a live popover question shows no context narration.*
- **P1 — Contract.** PLUGIN_SCHEMA §13.7 gains the three-duty role, the
  per-region pixel rule, and the provenance-from-results rule. *Docs-first; stop
  for approval if the contract moves off §4.*
- **P2 — Per-region pixel routing.** Use the stored loss verdict to answer a
  picture region from a crop. *Verify: equation 29 answered without the user
  snipping; a text region still answers from text.*
- **P3 — Citation resolution (depth 1).** Bibliography parse + `[8]` → paper,
  resolved pre-turn. *Verify: collision cases (`[^8]`, `[text][8]`, code indices)
  are dropped; a real `[8]` resolves.*
- **P4 — Provenance surface.** Assemble from resolution results; no output regex.
- **P5 — Vault coverage.** Ingest the missing ~101 files so duty 2 is true.
- **P6 — Live acceptance.** The definition-of-done question, end to end.

**Version**: Minor → **v0.54.0**. `MAJOR.MINOR` moves 0.53 → 0.54, so all four
spec titles bump.
