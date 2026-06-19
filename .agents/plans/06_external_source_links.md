# v0.18.0 Master Implementation Plan — External-Source Link Resolution

Date: 2026-06-20
Status: DRAFT — awaiting user approval (Universal Strict Workflow Step 4 STOP).
Follow-up to v0.17.0 (curator wikilink native resolution, PR #40 — kept).

## 0. Background

v0.17.0 made hidden curator L1–L4 inter-node links clickable. User follow-up:
those inter-node links are not the priority — **links to the source documents
OUTSIDE `.curator/` must resolve well**. The user wants this across three
surfaces and chose to KEEP the v0.17.0 feature and ADD source-link resolution.

Source documents (`04_Resources/*.md`, `04_Resources/References/*.md`,
`05_Assets/*`) are **real, visible, indexed** vault files — Obsidian can resolve
them natively. The gap is that the system surfaces curator nodes, not source
documents, and the pages that link to sources are hidden.

## 1. Objective

Make a reader able to reach the underlying source document from the knowledge
that cites it, in each surface the user named:

- **(a) Chat sidechat / quick-query popover answers** — an answer grounded in a
  source can offer a clickable link that opens the real source document.
- **(b) Opened DAG page (frontmatter + body)** — `source_path` provenance and
  asset embeds in an opened CTX/ATM/CON/SYN page click through to the source /
  asset.
- **(c) Graph / backlinks** — source documents appear connected to the knowledge
  that references them (SUBJECT TO the architectural constraint in §4).

## 2. Explicit Non-Goals

- **Not** removing the v0.17.0 curator-internal link rewrite (user: keep it).
- **Not** changing how sources are ingested or where source files live.
- **Not** making EVERY curator node visible (that is the rejected Option B); any
  visibility introduced for (c) is a minimal, opt-in bridge, not the whole DAG.

## 3. Strict Quality Conditions & Release Gates

- Source-document links emitted into chat answers/pages MUST resolve to an
  existing visible file or be marked missing — never a dead native link.
- The v0.17.0 curator-link tests and behavior remain green and unchanged.
- Backend changes pass `scripts/backend-check ruff|mypy|pytest`; plugin changes
  pass `npx vitest run` + `tsc` + production build.
- No regression to the existing Sources & Trace panel locator navigation.

## 4. Locked Design Decisions (Arena Consensus — inline) + the (c) fork

### (a) Chat / popover source links — BACKEND-led, tractable
- `SearchHit` (search.py:53) carries only the curator node relpath. Extend the
  synthesis context (`query.py` `_build_synthesis_context` / the block that emits
  `Wikilink path: [[…]]`) to ALSO surface each hit's **source-document vault path**
  resolved via existing provenance (curator node → `source_id`/`source_spans` →
  source file path; the same provenance the trace `locator` already uses).
- Instruct the LLM to cite the source with a resolvable visible link
  (`[[04_Resources/…]]`) in addition to / instead of the curator node, per a clear
  prompt contract. These resolve natively in `MarkdownRenderer` because the target
  is indexed; the v0.17.0 post-processor already leaves non-curator links
  untouched, so no double-handling.
- Plugin: confirm `rewriteCuratorLinks` ignores source links (it does). Optionally
  add a sibling resolver that flags a source link whose file is missing
  (`is-missing`) for parity — REUSE the v0.17.0 helper shape.

### (b) Opened DAG page — VERIFY-then-minimal
- Body asset embeds `![[05_Assets/…]]` and body source links `[[04_Resources/…]]`:
  targets are indexed → resolve natively even from a hidden page. VERIFY in P0; if
  confirmed, NO code needed for the body.
- Frontmatter `source_path: '[[04_Resources/…]]'`: frontmatter links render in the
  Properties UI, which the markdown post-processor does NOT reach. If the user
  needs a clickable source from an opened page and the property pill is
  insufficient, emit a body `## Source` line carrying `[[04_Resources/…]]` at page
  generation (prompts.py / page_writer.py) so it is a real, natively-resolved body
  link. Decision gated on the P0 verification result.

### (c) Graph / backlinks — ARCHITECTURAL FORK (user decision needed in-plan)
**Constraint:** Obsidian's `resolvedLinks`/graph/backlinks ONLY index links from
VISIBLE files. The curator pages linking to sources are hidden, so source↔knowledge
edges cannot appear in graph/backlinks while those pages stay hidden. Options:
- **(c1) Visible provenance bridge (gets real graph/backlinks).** Generate a
  minimal VISIBLE note per source (or augment the existing visible `04_Resources/`
  source note) with `[[…]]` links to the knowledge that cites it. Real graph edges
  + backlinks, at the cost of writing visible derived links. Scope the bridge as
  narrow as possible (e.g. only promoted/`02_Wiki` knowledge, or a single
  per-source backlink list) to avoid vault clutter.
- **(c2) Accept the limitation; use the Trace panel (no new files).** The Sources
  & Trace panel already navigates to sources; document that graph/backlinks for
  hidden knowledge is out of scope. Zero clutter, no native graph.
- **(c3) Hybrid:** (c1) only for human-promoted `02_Wiki/` knowledge (already
  visible), (c2) for the raw hidden DAG.
**LOCKED: (c3) Hybrid (user-approved).** Native graph/backlinks ONLY for
human-promoted, already-visible `02_Wiki/` notes — promotion writes `[[04_Resources/…]]`
(and other source) links into the `02_Wiki/` note so Obsidian indexes real
source↔knowledge edges and backlinks there. The raw hidden L1–L4 DAG keeps
trace-panel navigation (no graph edges, by design). No new machine-visible files
beyond the human's own `02_Wiki/` promotions.

## 5. Scope Exclusions & Stop Conditions

- **Exclusions**: full visible DAG mirror; ingestion changes; changing source
  storage.
- **Stop Conditions**:
  - STOP for the user to choose (c1)/(c2)/(c3) before writing (c).
  - STOP if P0 shows body source links DON'T resolve natively from a hidden page
    (would mean a deeper Obsidian limitation; re-scope (b)).
  - STOP if provenance (node → source path) is not reliably available for all
    layers from the DB (would constrain (a)).

## 6. Evidence Ledger

- `SearchHit.full_path` = curator relpath only (search.py:53); `source_id` +
  `query_source_pages` provenance helpers exist (search.py:302-362).
- Trace panel already resolves sources via `openLocator` (external_pdf / external /
  vault) — `incuratorQueryTrace.ts:369-381`; locator built by
  `incuratorQueryTraceLocator`.
- L1 pages carry `source_path: '[[04_Resources/…]]'` frontmatter (prompts.py:170,
  178); testbed targets exist as real files (`04_Resources/*.md`, `05_Assets/*`).
- v0.17.0 helper `rewriteCuratorLinks` deliberately ignores non-curator links —
  reuse its shape for any source-link missing-state flagging.
- Versions at plan time: 0.17.0 across all three manifests → target 0.18.0.
- Branch: continue on `feature/wikilink-architecture-validation` (PR #40 open) or
  open a follow-up branch — DECISION: open `feature/external-source-links` from
  master AFTER PR #40 merges, to keep PRs reviewable. (Confirm with user.)

## 7. Execution Phases (TDD + CI per phase)

- **P0 — Verify native resolution (no code).** In the testbed/Obsidian: confirm
  whether body `[[04_Resources/…]]` and `![[05_Assets/…]]` already resolve from an
  opened hidden page, and whether the frontmatter `source_path` pill is clickable.
  Record results; they gate (b). Confirm DB provenance gives a source path for a
  hit at every layer (gates (a)).
- **P1 — Contract spec (docs-first).** Update `PLUGIN_SCHEMA.md`,
  `SYSTEM_BEHAVIOR.md` (chat source-citation contract), and PLUGIN_GUIDE (+KR) for
  the chosen (a)/(b)/(c) behavior. STOP for (c) choice.
- **P2 — (a) backend source surfacing (TDD).** query.py: surface source path per
  hit + prompt contract to cite source links; `backend/tests/` coverage.
- **P3 — (b) page/body source link (TDD), only if P0 requires it.** prompts.py /
  page_writer.py emit a body `## Source` link; tests.
- **P4 — plugin parity (TDD).** Optional source-link missing-state flag reusing
  the v0.17.0 helper; tests.
- **P5 — (c) per chosen option (TDD).** Visible bridge generation (c1/c3) or docs
  note (c2).
- **P6 — Testbed smoke + docs sync + version bump 0.18.0 + PR.**
