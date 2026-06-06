import type { ContextRef } from "../types";

export function shouldIncludeContext(ref: ContextRef): boolean {
  return ref.includeInPrompt !== false;
}

export function includedContextRefs(refs: ContextRef[] | undefined): ContextRef[] {
  return (refs ?? []).filter(shouldIncludeContext);
}

export function isPrimaryUserContext(ref: ContextRef): boolean {
  if (!shouldIncludeContext(ref)) return false;
  if (ref.sourceViewType === "auto") return false;
  if (ref.isPinned) {
    // Pinned whole files/pdfs are background, but explicit snippets/selections are primary.
    const labelLower = ref.label?.toLowerCase() || "";
    return (
      ref.type === "selection" ||
      ref.type === "text" ||
      ref.type === "line-range" ||
      labelLower.includes("select") ||
      labelLower.includes("crop")
    );
  }
  return true;
}

export function hasPrimaryUserContext(refs: ContextRef[] | undefined): boolean {
  return includedContextRefs(refs).some(isPrimaryUserContext);
}

export function contextPromptLabel(ref: ContextRef): string {
  if (!shouldIncludeContext(ref)) return `Excluded context: ${ref.label}`;
  if (ref.sourceViewType === "auto") return `Visible background context: ${ref.label}`;
  if (ref.isPinned) {
    return isPrimaryUserContext(ref) ? `Primary user-selected context: ${ref.label}` : `Pinned background context: ${ref.label}`;
  }
  return `Primary user-selected context: ${ref.label}`;
}

export function contextPriorityInstruction(hasPrimaryContext: boolean): string {
  let instruction = "";
  if (!hasPrimaryContext) {
    instruction = "Pinned and visible Obsidian contexts (wrapped in `<background_reference_only>`, `<obsidian_incurator_context>`, or document outline tags) provide background knowledge of the user's workspace. Focus your answer on the user's specific question. You should actively use the background context to enrich your answer and connect it to the user's existing notes, but avoid outputting a generic summary of the background context unless requested.";
  } else {
    instruction = "Primary user-selected context is the MAIN FOCUS of the current request. You MUST actively use the pinned and visible Obsidian context (wrapped in `<background_reference_only>`, `<obsidian_incurator_context>`, or document outline tags) to enrich your answer, connecting the explanation of the selected text to the user's existing notes and current page/ToC, but you MUST NOT explain the background context itself.";
  }
  
  instruction += "\n\nCRITICAL: When a file context contains `<primary_focus_selection>`, treat it as the absolute core subject. Treat `<background_reference_only>`, `<obsidian_incurator_context>`, `<markdown_outlines>`, and `<document_outline>` as supplementary material for resolving references. You MUST NOT explain the entire document or current page when a primary focus selection is provided. Focus strictly on answering the user's query regarding the `<primary_focus_selection>`.";
  instruction += "\n\nPOINTER SELECTIONS: When the `<primary_focus_selection>` is itself a cross-reference/pointer (e.g. \"see Section A4.2 (p580)\", \"Figure 19.1\", \"Eq. (3)\") and a `<resolved_cross_references>` block is present, the user wants the content of the REFERENCED TARGET, not the visible page. Answer using the resolved target text/section inside `<resolved_cross_references>`, treating the selection only as the address of what to explain. If a pointer was detected but `<resolved_cross_references>` is empty or lacks the needed text, say you could not locate the referenced target and answer from the available context instead of inventing it or silently explaining the current page.";
  return instruction;
}
