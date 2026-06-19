# User Report

This document is a **plain Inbox (backlog) log** that records bugs reported by the user, required features, ideas, etc., in chronological order without any filtering.

Agents must check this document and triage the received items into the `To-Do (Queuing)` area or `Icebox` area of `.agents/ROADMAP.md`. Once the triage is complete, **immediately delete** the item from this document.

## 📝 User Inbox

### [Follow-up to v0.17.0] External-source links must resolve (2026-06-20)

User feedback (verbatim): "`.curator` 안에 있는 L1 - L4 의 링크를 만들어낼 필요는
없는데 적어도 그 밖에 있는 소스들에 대해서 링크 잘 되어야할거같음." (No need to make
the hidden L1–L4 inter-node links; but links to the sources OUTSIDE `.curator`
must work well.)

Decisions (via AskUserQuestion):
- **Keep** the PR #40 L1–L4 click-through; **ADD** external-source link resolution.
- Failing surfaces (all three): (a) chat sidechat / quick-query popover answers,
  (b) opened DAG page frontmatter/body (`source_path`, asset embeds), (c) graph /
  backlinks.

Grounding:
- External-source targets are REAL visible vault files (e.g.
  `04_Resources/smoke_images_paper.md`, `04_Resources/References/…md`,
  `05_Assets/…png`) — Obsidian CAN resolve them natively.
- `SearchHit.full_path` carries only the curator node relpath (search.py:53), so
  chat answers cite curator nodes, not source docs.
- The Sources & Trace panel ALREADY navigates to sources via locator targets
  (incuratorQueryTrace.ts openLocator: external_pdf / external / vault).
- **Hard constraint for (c)**: Graph view + Backlinks pane only index links that
  originate from a VISIBLE file. The curator pages that link to sources are hidden,
  so source↔knowledge edges can NEVER appear in graph/backlinks without a visible
  bridge file (= the previously-rejected Option B territory). Needs a design call.

Plan: `.agents/plans/` (follow-up milestone). Roadmap item 1 follow-up.
