# Critique on B_provider_edit
Date: 2026-09-10 | Agent Persona: Performance / Frontend Reviewer

## 1. Vulnerabilities & Flaws

1. Appending independent completed Codex messages fixes destructive length subtraction, but output-last-message reconciliation must not append an already partially streamed final answer in full; that would duplicate edit fences and proposals. Require an explicit accumulator invariant and test partial final snapshot followed by a larger final file. Same item ID updates should be deduplicated; different ID identical text can be a provider replay and needs a defined policy. Confirm stream item text semantics against installed runtime event shape.
2. The streamed/returned equality requirement can conflict with preserving progress messages because the output-last-message file only contains the final assistant item. Define whether commentary stays visible as status or remains in the returned content. Do not let progress prose be parsed as a second edit block or replace the real final patch.
3. The proposed agy invocation says read_file only for attached images. Search-off must retain native reads of explicit document context if the plugin supplied a document path but had insufficient page text; otherwise the toggle silently reduces the requested reading capability, not just prior-knowledge lookup. Prefer plugin-supplied current page/reference text and avoid broad filesystem scans. Do not promise missing figures are visible merely because a file path exists.
4. The API path still has automatic MCP tool injection. A prompt to avoid lookup is not an enforced off switch. The new control should be documented specifically as automatic prior-knowledge retrieval, with direct user-invoked tool work distinguished. If it means all retrieval off, a call-level MCP policy must filter automatic retrieval tools; changing provider-global settings during one turn would race concurrent popovers.
5. A schema-buffered agy answer is likely a regression to first visible answer time. Keep native text streaming and reject that alternative unless measured evidence shows it improves both failure rate and latency.

## 2. Suggested Alternatives / Validation

- Keep independent message identity and exact completion matching in a pure accumulator, then fake-process integration test the same code path the sidebar streams. Include final edit fences straddling chunk boundaries and unterminated final JSON line.
- Compare canonical resolved paths in the existing diff gate; no new intent-routing regex, no automatic application.
- Pin sidechat retrieval intent per turn and convey it via messages/options, never by temporarily mutating global plugin settings shared with popovers.
- Live agy probe should record startup-to-first-text separately from startup-to-close, use the same narrow permission surface as plugin, and demonstrate actual mathematical answer content. A successful exit code alone cannot establish answer quality or absence of command-denial masking.

## 3. Verification

Reviewed B against `ChatSidebarView.ts` existing retrieval/prompt policy and native `LLMClient.ts` CLI argument assembly. The parent should retain the deterministic Codex fix as required; agy complete resolution remains contingent on provider agent's scoped live probe rather than prompt tests alone.
