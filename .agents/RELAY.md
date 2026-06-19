# Cross-Agent Relay State

## Status
v0.17.0 (curator wikilink resolution) shipped via PR #40 (open). NEW follow-up:
external-source link resolution. Plan drafted, awaiting user approval + a (c)
graph/backlinks decision (Universal Strict Workflow Step 4 STOP).

## Goal
Make source documents OUTSIDE `.curator/` (04_Resources, 05_Assets, 03_Notes)
reachable from the knowledge that cites them, across (a) chat/popover answers,
(b) opened DAG pages, (c) graph/backlinks. KEEP the v0.17.0 curator-link feature.

## Key constraint (must resolve before (c))
Graph/Backlinks only index links from VISIBLE files; the curator pages linking to
sources are hidden, so source↔knowledge graph edges need a visible bridge file
(= Option B territory). Plan recommends (c3) hybrid: native graph/backlinks only
for human-promoted visible `02_Wiki/` knowledge; trace panel for the hidden DAG.

## Plan Reference
`.agents/plans/06_external_source_links.md` (PLAN_TEMPLATE-compliant, v0.18.0).
(a) backend query.py source surfacing + cite contract; (b) verify native
resolution / optional body `## Source` link; (c) fork c1/c2/c3.

## (c) decision: LOCKED (c3) Hybrid
Native graph/backlinks only for visible `02_Wiki/` promotions (they get
`[[source]]` links); hidden DAG uses trace panel.

## Immediate Next Action
STOP — plan + (c3) locked. Awaiting user "go" to begin P0 (verify native
resolution of body source links / asset embeds from a hidden page; confirm DB
provenance gives a source path per hit at every layer). Branch decision pending:
recommend merging PR #40 first, then `feature/external-source-links` from master.
