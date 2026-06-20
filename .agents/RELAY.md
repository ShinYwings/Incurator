# Cross-Agent Relay State

## Status
Milestone 6 (External-Source Link Resolution) SHIPPED as v0.18.0 on
`feature/external-source-links`. Release commit done; PR pending.

## What shipped (v0.18.0)
- Chat/query answers cite real source docs `[[04_Resources/…]]` via
  `db.sources_for_spans` (forward span→source trace; only `.md` stripped).
- `02_Wiki/` promotions append a deterministic `## Sources` section → sources
  appear in native Graph/Backlinks (c3 hybrid). Threaded `source_span_ids` through
  promote_answer (plugin_api + MCP tool + CLI `plugin promote --source-span-ids`)
  and `incuratorClient.promoteAnswer` (plugin TS). NOTE: promoteAnswer has no UI
  caller yet — plumbing ready for a future "save to wiki" action.
- Verified the RAG-stabilization abstraction→source provenance gap
  (test_abstraction_source_trace, incl. multi-source synthesis).
- (b) opened-page body `## Source` link SKIPPED (user deprioritized).

## Validation
Full backend 983 passed (+ D2 frozen-hash re-armed for the additive db.py change,
documented in D2_HOLDOUT_RESULT.yml external_source_links_rearm). Plugin 480 pass,
tsc/build OK. ruff/mypy clean (96 files). spec-sync 10 pass at v0.18.0 (no reinstall
needed — build-manifest driven). Versions consistent 0.18.0.

## Follow-up: "Save to 02_Wiki" UI action — DONE (on same v0.18.0 branch/PR #42)
- `incuratorQueryTrace.renderCuratorQueryTrace(..., { onPromote })` renders a
  "💾 Save to 02_Wiki" button in the Sources & Trace panel.
- chatSidebar `promoteAnswerToWiki(result, msg)` promotes the answer via
  `getIncuratorClient().promoteAnswer(question, answer, ws, result.source_span_ids)`,
  question falls back to last user msg; Notice on success/failure.
- Activates the `## Sources` footer end-to-end (no more dormant plumbing).
- Tests: incuratorQueryTraceV031 (button render) + chatSidebarSource (wiring).
  Plugin 482 pass, tsc/build OK. Docs: PLUGIN_GUIDE EN/KR; CHANGELOG [0.18.0].

## Immediate Next Action
PR #42 already open — push these follow-up commits to it. After merge: IDLE /
next roadmap item 2 (Obsidian Agent UI/UX & Context Architecture Overhaul).
