# Performance / Frontend Proposal: Overlap preparation and make prior-knowledge retrieval explicit
Date: 2026-09-10 | Agent Persona: Performance / Frontend Engineer

## 1. Core Logic & Implementation

### Observed evidence (structural, not a new live-vault benchmark)

- `ChatSidebarView.ts:1736–2070` prepares PDF tabs serially and only then awaits `client.fetchContext`. No deadline on the sidechat evidence wait. `context_service.py:720–741` may run a separate LLM derivation for non-English queries; its existing measurements document 12–50 seconds. `retrieval/evidence.py:221` then requests hybrid search with reranking. Every plugin backend call is a CLI process (`incuratorClient.ts:616–639`), so process-local embedder/reranker caches do not survive turns.
- `quickQueryPopover.ts:129–138` records prior live-vault evidence fetches at 59–99 seconds. A four-second deadline already exists, but the call starts at line 616, AFTER references and wikilinks resolve. The result therefore adds a separate delay even when document preparation could overlap it. This is a real serialization defect; another shorter timeout would merely hide its cost.
- `ChatSidebarView.ts:1916` runs `workspaceNotesFor` inside the PDF loop. Three PDF tabs duplicate the same workspace lookup three times, while markdown-only turns never run that consultation. Moving one consultation to the per-turn boundary eliminates duplicate scans and restores the documented project-notes duty to markdown.
- `workspaceNotes.ts:160` cold-reads workspace notes sequentially. Preserve current index/signature behavior; bounded concurrent reads can remove I/O serialization without changing rankings or evidence selection.
- `ChatSidebarView.ts:407–424`, `types.ts:31,90,144`, `systemPrompt.ts:65–74`: Plan is a real saved setting and prompt addendum, not just a UI label. Removing only its selector leaves old `chatMode: plan` users in the old behavior.

### Proposed contract

1. Introduce `sidechatKnowledgeEnabled: boolean`, default `true` (legacy settings absent => enabled). A composer button/toggle replaces Chat/Plan and displays both states explicitly, persists through `saveSettings`, exposes accessible pressed/state text. Disable while a turn is in progress or snapshot the setting at send; avoid a mid-turn toggle changing half the preparation policy.
2. Off skips automatic vault evidence fetch, workspace-note consultation and semantic PDF RAG. It keeps selected text, active/open/pinned context, explicit document references/wikilinks, PDF page text/outline, image materialization, and edit review. Explicit user-selected context is not “prior knowledge.” Add a prompt instruction that automatic prior-knowledge retrieval is off and the answer should use included context, rather than advertising an automatic MCP lookup that would defeat the toggle. Decide explicitly whether manual Sources & Trace actions remain available; proposed yes, as deliberate user actions.
3. Delete ChatMode, chatMode defaults/type/UI handler, `planMode` prompt option and addendum, and update fixtures/tests. Existing stored `chatMode` is ignored naturally by current code (no migration or compatibility shim needed).
4. Start sidechat vault evidence once at the top of `buildIncuratorProviderContext`, alongside PDF context preparation. Await its result at the existing append point so evidence order/trace identity remain stable. Move project-note consultation outside the PDF loop and compute once. Do not lower search quality, force English fallback tokens, drop evidence, or invent a second retrieval engine.
5. Start popover `vaultEvidenceFor` before asynchronous local reference/link preparation; await the already-started promise at the existing append point. Preserve its one-popover pending/cache semantics and four-second deadline measured from fetch start, and preserve document identity snapshot before all awaits.
6. If needed, parallelize workspace cold reads in fixed small batches, retaining original ordered path/page assignment. Do not change unbounded PDF lookaround policies as part of this hotfix.

### Tests / docs

- Behavioral deferred-promise tests: evidence fetch starts before slow PDF work resolves; total preparation is maximum of independent work, not their sum. Popover existing fake-timer tests must retain its four-second ceiling and reuse pending/cache results.
- Toggle test: off produces zero calls to `fetchContext`, `workspaceNotesFor`, PDF RAG while explicit PDF/reference context still resolves; on retains normal evidence/trace. Test three PDFs => one workspace search. Include markdown-only turn.
- Plan regression: `buildBaseSystemPrompt` never includes Plan instructions, including loading old settings whose extra property says plan; composer no longer emits Chat/Plan select.
- Workspace batching: defer note reads and verify bounded concurrency, stable path mapping, same hits, empty/unreadable note handling.
- Update English `docs/guides/PLUGIN_GUIDE.md` first, then `_KR.md` (Plan line 52 and sidechat/quick query retrieval sections). Update `docs/specs/plugin_schema/PLUGIN_SCHEMA.md` setting list and sidechat preparation/prompt contract. No DB change; public setting change requires minor release under current repository contract even though user calls the batch hotfix.

## 2. Pros & Cons

- Preserves retrieval capability when on and gives the requested immediate bypass when off. Reduces provable serial overhead in both surfaces; does not claim to remove external model generation latency or the backend cold-start cost.
- Starting evidence earlier may consume backend work even if later document preparation fails; existing popover already permits evidence to finish in background. Attach rejection handling immediately and preserve turn cancellation guards.
- A strict sidechat timeout would make “on” silently skip evidence and is a product capability trade. Do not add one by assumption. Query translation/rerank suppression is likewise a capability reduction and violates current English internal-query contracts.
- Live timings must distinguish prep time, first provider output, and full response completion; scripted timing tests prove scheduling, not real model speed. Parent should assess backend improvements separately if the enabled path still needs substantial reduction.
