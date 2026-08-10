# Problem Brief: Popover Chat Strict Grounding Relaxation

## 1. The Core Problem (What & Why)
**What**: The user reported that when they ask a question in the Quick Query popover about a topic not explicitly covered in the currently provided page context, the assistant strictly refuses to answer. It responds with statements like "The current page and provided context do not contain specific mathematical formulas or projection matrices for camera projection..." and stops there.
**Why**: The prompt constraints in `promptRegistry.ts` (e.g., `Answer only from the context provided in this request`) and `chatContextPriority.ts` (e.g., `do NOT attempt to open, read, or search the source file yourself; say you could not retrieve the referenced item and answer from what you already have`) strictly enforce a "grounding-only" policy. These were designed to prevent hallucinations and keep the assistant focused as a "reading assistant" rather than a general oracle. However, the user wants the assistant to fall back on its parametric knowledge ("추정이라도 했으면 좋겠어서") when the document context genuinely lacks the answer, rather than stonewalling them.

## 2. Analysis of the Affected Constraints
The grounding constraints currently live in several places:

1. **`promptRegistry.ts`**:
   - `POPOVER_PROFILE` / `local-only` policy: "Answer from the provided context plus any page you fetch."
   - Recency Anchor: "Do NOT explain, summarize, or modify the whole document unless the latest request explicitly asks for it... If the pointer's target appears in `<unresolved_cross_references>` instead, say you could not retrieve it and answer from the context already given..."

2. **`quickQueryContext.ts`**:
   - System instruction: "Use current page, document outline/ToC, and prior quick-query turns from the same popover only as background to resolve references, equations, and citations... When asked about a region of the document, summarize or quote that region's actual content."

3. **`chatContextPriority.ts`**:
   - `contextPriorityInstruction(true)`: "You MUST NOT explain the entire document or current page when a primary focus selection is provided. Focus strictly on answering the user's query regarding the `<primary_focus_selection>`."
   - Pointer selections: "A `<unresolved_cross_references>` block lists pointers whose target text could not be retrieved from the material available... say you could not retrieve the referenced item and answer from what you already have."

## 3. Constraints & New Requirements for the Solution
1. **Preserve Grounding When Context Exists**: The primary focus must remain on the selected text and provided context. If the answer is in the context, it must strictly use the context.
2. **Safe Fallback**: When the context does NOT contain the answer (or when a cross-reference fails), the assistant should explicitly state that the context lacks the information, and *then* provide an answer based on its general parametric knowledge, explicitly marking it as a general explanation or guess.
3. **No Hallucinated Citations**: The LLM must not pretend its parametric knowledge came from the document.
4. **Shared Prompts**: Modifications to shared prompts (like `boundaryConstraints` or `chatContextPriority`) must be evaluated for their impact on the sidechat surface as well. The fix might need to be isolated to the popover or carefully generalized.
5. **[NEW] Incorporate Sidechat / Pinned Sources**: The user requested that the popover ALSO search/use the provided sources from the sidechat (e.g., purple pinned PDF or MD files). 
   - **Architectural Decision Needed**: The popover currently runs with `toolPolicy: "local-only"` (no MCP tools) and only receives the `activeContext`. To satisfy this, the Executor must decide whether to (a) inject the sidechat's pinned contexts directly into the popover's context payload without changing the tool policy, or (b) upgrade the popover's tool policy to `auto` so it can use MCP tools to search the vault like the sidechat does. The former (injecting pinned context) maintains the ephemeral/read-only security boundary, while the latter changes the fundamental architecture of the popover. The Arena debate must address this.

## 4. Success Criteria
1. The Quick Query popover, when asked a question whose answer is missing from the provided context/page, provides a helpful fallback explanation using its own knowledge instead of just saying "I don't know based on the context".
2. The response clearly demarcates the boundary between "what the document says" and "what general knowledge says".
3. The popover chat successfully utilizes information from the main sidechat's pinned sources (purple pins, PDFs, MDs) to answer the query if applicable.
4. The assistant still strictly grounds its answers in the provided context when the context *does* hold the information.
5. No degradation in the handling of cross-references.
