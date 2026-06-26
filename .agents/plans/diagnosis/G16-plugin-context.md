# Diagnosis: G16-plugin-context
Coverage: plugin/src/context/*.ts and plugin/src/utils/*.ts source files; focused tests under plugin/src/context/*.test.ts and plugin/src/utils/*.test.ts; supporting evidence from plugin/src/types.ts, plugin/src/ui/chatSidebar.ts, plugin/src/ui/pdfCaptureService.ts, plugin/src/ui/externalPdfView.ts, plugin/src/agent/incuratorClient.ts, backend/src/curator/prompting/{contracts.py,registry.py}, backend/src/curator/context_service.py, docs/specs/plugin_schema/PLUGIN_SCHEMA.md, docs/specs/system_behavior/SYSTEM_BEHAVIOR.md, docs/specs/system_behavior/context_service_fixtures/context_fetch_pack.json, docs/guides/PLUGIN_GUIDE.md, and G09-llm-prompts.md.

## Findings
### [G16-1] (e/f/h) S2 - Plugin prompt policy is an unversioned second registry beside backend PromptContract
- Loc: plugin/src/context/promptRegistry.ts:1, plugin/src/context/promptRegistry.ts:47, plugin/src/context/promptRegistry.ts:78, plugin/src/context/systemPrompt.ts:17, plugin/src/context/systemPrompt.ts:62, plugin/src/context/quickQueryContext.ts:129, backend/src/curator/prompting/contracts.py:27, backend/src/curator/prompting/registry.py:17, docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:1036, docs/specs/plugin_schema/PLUGIN_SCHEMA.md:1612
- Evidence: Backend prompt governance is a real `PromptContract`/`PromptRegistry` with `prompt_id`, `version`, family, role, validators, hashes, and traceability. The plugin module named `promptRegistry.ts` is a surface-policy string helper for boundary constraints and recency anchors; `systemPrompt.ts` and `quickQueryContext.ts` still hardcode major prompt bodies outside any versioned contract. G09 already records the backend side of this; the plugin-specific drift is that frontend prompt blocks cannot be enumerated, versioned, hashed, diffed against backend invariants, or tied to prompt-v2 cross-provider consistency work.
- Fix sketch: Keep the frontend consolidation, but rename/split it to a precise `surfacePromptPolicy` concept and add a small shared prompt-policy manifest for cross-cutting invariants. Give sidechat and quick-query prompt assemblies explicit ids/versions/content hashes in tests, and decide which invariants are backend-global versus plugin-surface-only.
- Blast radius: Sidechat, quick query, external MCP tool boundaries, language bridge, edit contract, prompt-v2 governance, and docs that talk about prompt registries.
- Suggested PR: `refactor/plugin-prompt-policy-contracts`

### [G16-2] (h/a) S2 - XML-like prompt blocks inject unescaped user/evidence text
- Loc: plugin/src/context/quickQueryContext.ts:29, plugin/src/context/quickQueryContext.ts:153, plugin/src/context/systemPrompt.ts:75, plugin/src/context/systemPrompt.ts:87, plugin/src/context/crossReferenceResolver.ts:512, plugin/src/context/providerContextFormat.ts:111, plugin/src/context/providerContextFormat.ts:126, plugin/src/context/providerContextFormat.ts:132, plugin/src/context/quickQueryContext.test.ts:12, plugin/src/context/providerContextFormat.test.ts:90
- Evidence: The prompt builders wrap untrusted selected text, latest user text, resolved PDF snippets, ContextService summaries/details, and warnings inside XML-ish tags such as `<primary_focus_selection>`, `<original_user_request>`, `<resolved_cross_references>`, and `<incurator_evidence_pack>`. Attribute values are escaped in some places, but body content is raw. A note/PDF/backend evidence string containing `</primary_focus_selection>` or `<critical_invariants>` can break the intended prompt boundaries. Existing tests assert happy-path tags but do not cover hostile closing tags.
- Fix sketch: Add one prompt-block serializer for untrusted body text that preserves readable Markdown while neutralizing internal control tags, at least for known wrapper tags and critical invariant tags. Route quick query, sidechat context refs, resolved references, and ContextService pack formatting through it, then add adversarial fixture tests.
- Blast radius: All local provider prompts, prompt injection resilience, quick-query read-only guarantees, sidechat edit gating, and evidence grounding.
- Suggested PR: `fix/plugin-prompt-block-escaping`

### [G16-3] (f/e/a) S2 - Context pack client shape has drifted from the normalized fixture contract
- Loc: plugin/src/types.ts:517, plugin/src/types.ts:524, plugin/src/context/providerContextFormat.ts:90, plugin/src/context/providerContextFormat.ts:96, plugin/src/context/providerContextFormat.ts:105, plugin/src/context/providerContextFormat.ts:128, backend/src/curator/context_service.py:662, backend/src/curator/context_service.py:669, docs/specs/system_behavior/context_service_fixtures/context_fetch_pack.json:40, docs/specs/system_behavior/SYSTEM_BEHAVIOR.md:2638, docs/specs/plugin_schema/PLUGIN_SCHEMA.md:1813
- Evidence: The canonical fixture/spec models `route` as an object with `selected`, `reason`, and `stop_reason`, plus policy/coverage/omission details. Plugin `CuratorContextPack.route` is typed as a string, and `formatCuratorContextPack()` only emits `pack.route` as an attribute. The backend currently also returns legacy string `route` plus `route_reason`, so plugin and backend implementation agree with each other but not with the static normalized fixture. This will drop route detail if the backend moves to the fixture shape, and it makes docs-code parity ambiguous.
- Fix sketch: Reconcile the contract in one shared PR: either update specs/fixtures to the current additive transport or normalize backend/plugin to the fixture object. On the plugin side, define a stricter `NormalizedContextPack` type, normalize legacy string routes to `{selected, reason}`, and update provider/trace formatting tests with the canonical fixture.
- Blast radius: Provider grounding, Sources & Trace, context expand/verify/refetch UI, MCP/plugin parity, and future generated clients.
- Suggested PR: `fix/context-pack-contract-parity`

### [G16-4] (g) S2 - PDF page indexing rebuilds the whole BM25 index per page
- Loc: plugin/src/context/pdfDocumentIndex.ts:65, plugin/src/context/pdfDocumentIndex.ts:82, plugin/src/context/pdfDocumentIndex.ts:87, plugin/src/context/pdfDocumentIndex.ts:104, plugin/src/context/pdfDocumentIndex.ts:190, plugin/src/ui/externalPdfView.ts:1257
- Evidence: `PdfDocumentIndexService.upsertPage()` materializes all existing pages, replaces/adds one page, sorts, then calls `buildIndex()` for the full document. `ExternalPdfView.extractPageTextFromPdfJs()` calls `upsertPage()` as pages are extracted. For an N-page PDF this is O(N^2) tokenization/DF rebuild work, which is exactly the path used for local PDF RAG.
- Fix sketch: Add incremental index mutation for single-page updates, or batch rebuild after a page-load burst. Keep the current `upsertDocument()` full rebuild path for explicit full-document replacement and add a performance regression test with a synthetic large document.
- Blast radius: External PDF viewer responsiveness, local PDF RAG latency, long-paper memory/CPU usage, and perceived stability while scrolling/indexing.
- Suggested PR: `perf/pdf-index-incremental-upsert`

### [G16-5] (f/i/d) S2 - `pdfFullDocumentIndex` is documented and configurable but not consumed by context code
- Loc: plugin/src/types.ts:102, plugin/src/types.ts:188, plugin/src/settings.ts:504, docs/guides/PLUGIN_GUIDE.md:455, plugin/src/context/pdfDocumentIndex.ts:65, plugin/src/ui/pdfCaptureService.ts:53
- Evidence: The setting exists, defaults to `true`, and the guide says it indexes the entire PDF for better RAG accuracy. Search found no read of `pdfFullDocumentIndex` outside types/settings/tests. `PdfCaptureService` indexes/searches whatever pages are in `pageTextCache`, while `PdfDocumentIndexService` has no policy input for full-document versus incremental behavior.
- Fix sketch: Either wire the setting into the PDF context/index pipeline with clear behavior, or remove the setting and update docs. If kept, the setting should decide whether the external viewer eagerly indexes all pages, indexes only rendered/current-window pages, or delegates to backend PDF context.
- Blast radius: PDF RAG accuracy, settings UX, docs-code parity, long-PDF performance, and user trust in plugin settings.
- Suggested PR: `fix/pdf-full-document-index-setting`

### [G16-6] (f/i/a) S3 - Built-in PDF fallback ignores `pdfWindowRadius`
- Loc: plugin/src/context/pdfCapture.ts:8, plugin/src/context/pdfCapture.ts:50, plugin/src/context/pdfCapture.ts:405, plugin/src/ui/chatSidebar.ts:1713, plugin/src/settings.ts:450, docs/guides/PLUGIN_GUIDE.md:450
- Evidence: The built-in Obsidian PDF helper hardcodes `DEFAULT_PDF_WINDOW_RADIUS = 1` and calls `extractVisibleWindowPages(..., DEFAULT_PDF_WINDOW_RADIUS)`. The backend path in chat sidebar passes `this.plugin.settings.pdfWindowRadius`, and settings clamp the user value from 0 to 5. Users who change the setting get inconsistent context depending on whether the backend/external-view path or built-in local fallback path is active.
- Fix sketch: Pass the configured radius into `getPdfContext()` or move built-in capture through `PdfCaptureService`, then add a unit test that radius 0/2 changes the captured window pages.
- Blast radius: Built-in PDF quick context, offline backend fallback, quick-query background, and settings predictability.
- Suggested PR: `fix/pdf-window-radius-fallback`

### [G16-7] (a/h) S3 - Query trace formatter assumes complete legacy arrays despite partial/additive responses
- Loc: plugin/src/context/providerContextFormat.ts:69, plugin/src/context/providerContextFormat.ts:79, plugin/src/context/providerContextFormat.ts:80, plugin/src/context/providerContextFormat.ts:81, plugin/src/types.ts:439, plugin/src/types.ts:459, docs/guides/PLUGIN_GUIDE.md:1231
- Evidence: `formatCuratorQueryResult()` checks only that `trace` is truthy, then calls `trace.matched_concepts.slice()` and `trace.source_paths.slice()`. The guide says older/partial backend responses may omit ContextService fields, and `IncuratorClient` casts `r.trace` without runtime validation. A partial trace object can throw during provider-context assembly instead of degrading to "No backend evidence pack was returned."
- Fix sketch: Harden formatter reads with `Array.isArray` guards and fixture tests for minimal/partial trace payloads. Prefer formatting from `context_pack` when present and treating legacy trace fields as optional.
- Blast radius: Sidechat provider context, backend downgrade compatibility, update windows where plugin/backend versions differ, and user-visible generation failures.
- Suggested PR: `fix/provider-context-partial-trace`

### [G16-8] (b/e/h) S3 - Prompt/context formatting helpers are duplicated across modules
- Loc: plugin/src/context/providerContextFormat.ts:17, plugin/src/context/providerContextFormat.ts:22, plugin/src/context/crossReferenceResolver.ts:488, plugin/src/context/pdfCapture.ts:436, plugin/src/utils/textUtils.ts:132
- Evidence: Truncation and escaping exist as separate helpers with different scopes and markers (`truncateForProviderContext`, `trimText`, `truncateToLength`, local `escapeAttr`). This duplication is small today but directly touches prompt safety; one helper escapes attributes, another raw-writes body content, and truncation markers differ by surface.
- Fix sketch: Introduce a narrow `promptSerialization` helper for attribute escaping, untrusted body serialization, and consistent truncation markers. Migrate only prompt/context builders first; leave unrelated UI text helpers alone.
- Blast radius: Prompt block safety, quick query, sidechat provider context, PDF reference blocks, and tests that assert exact serialized context.
- Suggested PR: `refactor/prompt-context-serialization`

### [G16-9] (c) S3 - Zotero URL parsing has an empty catch that returns partial data
- Loc: plugin/src/utils/zoteroUtils.ts:7, plugin/src/utils/zoteroUtils.ts:12, plugin/src/utils/zoteroUtils.ts:28, plugin/src/utils/zoteroUtils.test.ts:6
- Evidence: `parseZoteroLink()` first regex-extracts an attachment key, then uses `new URL(href)` to parse page/annotation/viewer flags. If URL parsing throws, the empty `catch (err) {}` silently returns the attachment key without query metadata. That may be acceptable for malformed input, but the behavior is implicit and untested for malformed `zotero://` URLs.
- Fix sketch: Replace the empty catch with an explicit fallback comment/test, or return `null` for malformed URLs if callers require query correctness. Avoid binding an unused `err`.
- Blast radius: Zotero PDF link interception, page jump behavior, and noisy debugging when malformed links are generated upstream.
- Suggested PR: `chore/zotero-link-parse-fallback-test`

## Positives (keep / do-not-break)
- `promptRegistry.ts` successfully prevents sidechat/popover security wording from silently diverging for boundary constraints and recency anchors; keep the shared frontend policy even if it is renamed or versioned.
- `quickQueryContext.ts` and `chatSidebar.ts` both append recency anchors late in the latest user payload, which is a useful guard against long-history attention decay.
- `crossReferenceResolver.ts` is pure, well-tested, and uses outline, caption-index, page-label, and BM25 fallbacks without making unresolved references look resolved.
- `pdfTextLayout.ts` has a pragmatic text-quality model and explicit scanned-like fallback, with tests around text-layer extraction and crop text ordering.
- `assetSource.ts` centralizes Zotero/reference identity and avoids treating Reference Mode stubs as resolved local PDFs; tests cover stale path and cache invalidation behavior.
- Utility helpers are mostly small, pure, and unit-tested; `editMatch.ts`, `mathSource.ts`, `sessionData.ts`, `curatorWikilinks.ts`, and `streamContinuation.ts` have good focused regression coverage.

## Open questions for the human
- Should plugin sidechat/quick-query prompts become first-class prompt contracts, or should the backend registry remain backend-only with a shared invariant manifest for frontend policy?
- For the ContextService route shape, should the code normalize to the fixture object now, or should specs/fixtures be updated to bless the current string-plus-`route_reason` transport?
- Is `pdfFullDocumentIndex` still a product requirement, or should the setting be removed in favor of backend ContextService PDF retrieval?
- Should prompt-block escaping preserve literal XML-like source text for academic content, or is neutralizing wrapper/control tags acceptable even if it slightly changes displayed evidence text inside model prompts?
