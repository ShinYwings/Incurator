# Briefing: User-Reported Stability Bug Batch

Date: 2026-06-25
Branch: `feature/system-stability-overhaul`
Source: `.agents/USER_REPORT.md` inbox items triaged on 2026-06-25.

## 1. Core Problem Definition

The active System Stability Overhaul is paused for a user-prioritized bug batch.
The user has been exercising the system and logged urgent stability failures in
the inbox. These reports are concrete workflow blockers around source
registration, generated L1 portability, CLI job recovery, PDF/LaTeX interactions,
PDF reference lookup, and UI responsiveness.

This batch must be handled before resuming Phase A diagnosis. The goal is narrow,
report-driven stability repair, not broad refactoring.

## 2. Preserved User Reports

1. VLM-generated CTX content contains device-dependent temp image paths such as
   `![Tangent frame](file:///Users/shin/shinywings/Incurator/.cache/vision_render/7644776981ac/page-ebdf5106.png)`.
   This breaks on other devices.

2. After Add Source, the PDF chip can still show an actionable Add Source state.
   It should show an ingested/added/queued state instead.

3. Immediately after `wiki add`, `wiki status` shows malformed wikilink findings
   in `01_Contexts/CTX-8502639c.md`, including several
   `[[MultipleViewGeometry#...]]` heading links.

4. From Atom/L2 onward, generated content should be English, but it still appears
   in Korean.

5. Sidechat LaTeX copy works, but popover LaTeX copy does not.

6. Convert-to-LaTeX copy should copy the selected region as LaTeX+text faithfully,
   but currently adds extra prose and is slower than the earlier dedicated path.

7. Popover did not find equation `(19.11)` elsewhere in the currently open PDF;
   it answered that the formula was outside the provided context. The intended
   use case is following references outside the current page.

8. `wiki jobs list` showed queued jobs `30` and `31`, but `wiki jobs rerun 30`
   reported: `Job #30 is not done, failed, cancelled, or does not exist.`

9. A generated link was created but not interactive (`.agents/image-1.png`).

10. `wiki source ls` showed L2 layer errors for sources `#19` and `#24`, but
    `wiki source retry` returned `No errored sources found.`

11. `wiki source rm 24` prompted:
    `About to remove from tracking AND delete file: #24 03_Notes/Vision/MultipleViewGeometry.md.`
    This is wrong; source truth must never be modified or deleted by Incurator.

12. An Add Resource PDF stayed at L1 `RUN`, while the pin still showed Add Source.
    The user also asked why L4 was not created after build for the other sources
    (`.agents/image-2.png`).

13. The system feels slower; PDF scrolling/rendering janks.

14. Quick query popovers are single-instance: opening a new quick query removes
    the previous one. The user wants multiple quick queries to coexist.

Screenshots in the workspace:
- `.agents/image.png`
- `.agents/image-1.png`
- `.agents/image-2.png`

## 3. Initial Repository Facts

- Current branch is `feature/system-stability-overhaul`.
- Active master plan `.agents/plans/01_system_stability_overhaul.md` is still
  `DRAFT — awaiting user approval`.
- Docs already say `wiki source rm <id>` removes source registration and generated
  L1 nodes. Current CLI behavior conflicts with that contract by defaulting to
  source-file deletion.
- Docs/specs say `queued` and `running` source states keep their own labels; the
  key UI bug is that registration must not leave an actionable Add Source badge.

## 4. Constraints

- Do not edit `03_Notes/`, `04_Resources/`, or `06_Archives` autonomously.
- Every code change needs matching tests and docs.
- Backend changes require focused `pytest` coverage under `backend/tests/`.
- Plugin changes require focused `vitest` coverage.
- Generated L1/CTX content must not contain device-local temp paths.
- Passive PDF popover/chat must not auto-register untracked PDFs.

## 5. Open Ambiguities

- For report 2/12, should registered-but-not-built PDFs show `Queued`/`Building...`
  per current spec, or collapse to `Added` immediately after L1?
- For report 7, a narrow fix can detect bare `(19.11)` and use existing PDF search
  hits. A guaranteed whole-PDF equation lookup may require a backend-backed
  quick-query context fetch.
- For report 13, PDF scroll jank needs profiling before a real fix.
- For report 14, popovers should remain ephemeral and session-local; the fix is
  multiple independent open popovers, not persistence in chat history.
