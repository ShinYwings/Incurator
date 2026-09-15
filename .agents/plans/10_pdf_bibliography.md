# v0.82.8 Master Implementation Plan

Date: 2026-09-14
Status: APPROVED — independent Arena proposals and cross-critique concluded.

## 1. Objective

From visible PDF page7, a bibliography question must retrieve References on
page11 and include its actual text in the outgoing popover prompt. Followups
must retain source evidence. Missing context is not an acceptable substitute
for attempting retrieval. Exact incident viewer/provider remain unverified.

## 2. Explicit Non-Goals

No schema change, document ingest/reindex, whole-paper injection every turn,
new model tools, new retention policy or live data migration. This patch repairs
existing reference-reading capability independently of v0.83 lifetime work.

## 3. Strict Quality Conditions & Release Gates

- Native reader path/authoritative page count are tested through preparation;
  outgoing message contains page11 author token with current page7 only in DOM.
- Reader remains bound to one source during focus switches and async fetches.
- Failed first scan and failed continuation retry on the next request.
- Explicit bibliography requests deliver heading-anchored raw section text for
  author-year formats; numeric reference90 survives the whole-list40 cap.
- Source pages and any clipping remain distinguishable from prior model claims.
- Existing collision, query preparation, budget and provider isolation tests pass.
- All repo local checks, review and remote CI green before merge.

## 4. Locked Design Decisions (Arena Consensus)

Capture a reader from the same last content leaf as ActiveContext before await.
Snapshot native absolute file path or external hash/key/path and optional viewer
identity. Read authoritative metadata via existing getPdfContext; DOM page count
is only a fallback observation. Per-page calls use immutable identity arguments,
with the captured viewer fallback checked before and after asynchronous reads.

Keep bibliography heading detection and existing bounded tail/continuation
policy; use a known References outline page first. Retain raw heading-anchored
section pages independently of numbered parsing. Cache only complete successful
scans, not failed or partial outcomes. Expose retrieval coverage as actual
observations, never as proof of exhaustive whole-document search. A short
followup reuses prior bibliography intent for the same captured document so
the original source text, not only assistant text, reaches the next prompt.

Use existing prompt budget priorities; include a per-page boundary and source
scope instruction. Verification proves source payload/attribution, not that
every future model will obey every instruction. Broader document search retains
its existing roadmap milestone; no invented locator is added to this patch.

## 5. Scope Exclusions & Stop Conditions

Production migration/deletion and product capability reductions require user
decision. Existing approval covers this bug fix, review and release. Actual
incident cannot be attributed to a viewer without runtime evidence.

## 6. Evidence Ledger

Base14b793f4; shipped code1d614e06/schema14. Domain analyses are Arena
01_proposal.md/01_adversary.md and cross-critiques. WIP schema15 saved in
52783718 at sibling Incurator-lifetime-dev. Original root runtime restored
to schema14 and original cache13ed51f8b06cb88e verified; hotfix worktree separate.
Execution ledger:10_pdf_bibliography_evidence.md. No data rollback needed.

## 7. Execution Phases (Follow TDD and CI at each phase)

Review extension: native file paths have no reliable revision identity. Native
popover bibliography scans must bypass global bibliography cache reads AND
writes, including pre-existing entries. Keep external registered-document caching
and stable followup identity. Independent pdf_final_review approved this over
mtime/size fingerprints, which miss same-size timestamp-preserving replacements.
Regression: replace page11 text with unchanged path/count/outline; verify new
evidence. Cost: repeated bounded native scans; backend page caching stays intact.

- P0 — independent failure-path evidence and cross-critique (complete).
- P1 — update plugin spec and English/Korean guides before logic.
- P2 — failing reader/bibliography tests, implement pure helpers.
- P3 — integrate captured reader and followup evidence in popover; test final payload.
- P4 — full backend/plugin checks, patch version/changelog, private smoke.
- P5 — independent review, PR/CI/merge, prune completed hotfix worktree.
