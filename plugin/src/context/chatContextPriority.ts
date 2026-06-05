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
    instruction = "Pinned and visible Obsidian contexts (wrapped in `<background_reference_only>` or `<obsidian_incurator_context>`) provide background knowledge of the user's workspace. Focus your answer on the user's specific question. You should actively use the background context to enrich your answer and connect it to the user's existing notes, but avoid outputting a generic summary of the background context unless requested.";
  } else {
    instruction = "Primary user-selected context is the MAIN FOCUS of the current request. You MUST actively use the pinned and visible Obsidian context (wrapped in `<background_reference_only>` or `<obsidian_incurator_context>`) to enrich your answer, connecting the explanation of the selected text to the user's existing notes, but you MUST NOT explain the background context itself.";
  }
  
  instruction += "\n\nCRITICAL: When a file context contains `<primary_focus_selection>`, treat it as the absolute core subject. Treat `<background_reference_only>` and `<obsidian_incurator_context>` as supplementary material. You MUST NOT explain the entire document or current page when a primary focus selection is provided. Focus strictly on answering the user's query regarding the `<primary_focus_selection>`.";
  return instruction;
}
