import type { ContextRef } from "../types";

export function shouldIncludeContext(ref: ContextRef): boolean {
  return ref.includeInPrompt !== false;
}

export function includedContextRefs(refs: ContextRef[] | undefined): ContextRef[] {
  return (refs ?? []).filter(shouldIncludeContext);
}

export function isPrimaryUserContext(ref: ContextRef): boolean {
  if (!shouldIncludeContext(ref)) return false;
  return ref.sourceViewType !== "auto" && ref.isPinned !== true;
}

export function hasPrimaryUserContext(refs: ContextRef[] | undefined): boolean {
  return includedContextRefs(refs).some(isPrimaryUserContext);
}

export function contextPromptLabel(ref: ContextRef): string {
  if (!shouldIncludeContext(ref)) return `Excluded context: ${ref.label}`;
  if (ref.sourceViewType === "auto") return `Visible background context: ${ref.label}`;
  if (ref.isPinned) return `Pinned background context: ${ref.label}`;
  return `Primary user-selected context: ${ref.label}`;
}

export function contextPriorityInstruction(hasPrimaryContext: boolean): string {
  if (!hasPrimaryContext) {
    return "Pinned and visible Obsidian context are background grounding. Use them to understand the workspace, but do not treat them as an explicit user focus unless the user asks about them.";
  }
  return "Primary user-selected context is the focus of the current request. Use pinned and visible Obsidian context only as background grounding unless it directly clarifies the selected context.";
}
