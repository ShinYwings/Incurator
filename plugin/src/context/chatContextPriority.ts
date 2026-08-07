import type { ContextRef } from "../types";
import { formatVaultLocatorWikilink } from "./providerContextFormat";

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

/**
 * Localized-question edit-affordance suppression (v0.21.0).
 *
 * A `Cmd+Shift+L` line-range (and any other primary-focus selection) is BOTH a
 * primary-context ref (recency anchor: "answer only, do not modify the document")
 * AND an editable ref (which injects `<editable_selection>` + the
 * `<edit_review_loop>` contract: "you may edit these lines"). Emitting both into
 * the same payload is a direct contradiction that let long, edit-heavy sessions
 * drift back to whole-file edits on a simple localized question.
 *
 * When the latest turn carries a primary-focus selection AND is not itself a
 * Markdown edit request, suppress both edit affordances so the recency anchor is
 * unopposed. The decision is UNCONDITIONAL with respect to prior turns — it must
 * NOT consult `priorAnswerOpenedEditLoop`, because the reported failure case is a
 * fresh localized question that immediately follows an earlier whole-document
 * edit (where `priorAnswerOpenedEditLoop` is true). Any edit-phrased turn flips
 * `isEditRequest` true and restores the affordances.
 */
export function shouldSuppressEditAffordances(args: {
  hasPrimarySelection: boolean;
  isEditRequest: boolean;
}): boolean {
  return args.hasPrimarySelection && !args.isEditRequest;
}

export function contextPromptLabel(ref: ContextRef): string {
  if (!shouldIncludeContext(ref)) return `Excluded context: ${ref.label}`;
  const filePath = ref.filePath?.trim();
  let label = ref.label;
  if (filePath) {
    const lowerPath = filePath.toLowerCase();
    const sourceKind = lowerPath.endsWith(".md")
      ? "vault_markdown"
      : lowerPath.endsWith(".pdf")
        ? "vault_pdf"
        : "";
    const vaultLinkTarget = sourceKind
      ? formatVaultLocatorWikilink({
          source_kind: sourceKind,
          relpath: filePath,
          page_number: ref.pageNum,
          locator_status: "exact",
        })
      : null;
    label += vaultLinkTarget
      ? ` (vault_link_target: ${vaultLinkTarget})`
      : ` (file path: ${filePath})`;
  }
  if (ref.sourceViewType === "auto") return `Visible background context: ${label}`;
  if (ref.isPinned) {
    return isPrimaryUserContext(ref) ? `Primary user-selected context: ${label}` : `Pinned background context: ${label}`;
  }
  return `Primary user-selected context: ${label}`;
}

export function contextPriorityInstruction(hasPrimaryContext: boolean): string {
  let instruction = "";
  if (!hasPrimaryContext) {
    instruction = "Pinned and visible Obsidian contexts (wrapped in `<background_reference_only>`, `<obsidian_incurator_context>`, or document outline tags) provide background knowledge of the user's workspace. Focus your answer on the user's specific question. You should actively use the background context to enrich your answer and connect it to the user's existing notes, but avoid outputting a generic summary of the background context unless requested.";
  } else {
    instruction = "Primary user-selected context is the MAIN FOCUS of the current request. You MUST actively use the pinned and visible Obsidian context (wrapped in `<background_reference_only>`, `<obsidian_incurator_context>`, or document outline tags) to enrich your answer, connecting the explanation of the selected text to the user's existing notes and current page/ToC, but you MUST NOT explain the background context itself.";
  }
  
  instruction += "\n\nCRITICAL: When a file context contains `<primary_focus_selection>`, treat it as the absolute core subject. Treat `<background_reference_only>`, `<obsidian_incurator_context>`, `<markdown_outlines>`, and `<document_outline>` as supplementary material for resolving references. You MUST NOT explain the entire document or current page when a primary focus selection is provided. Focus strictly on answering the user's query regarding the `<primary_focus_selection>`.";
  instruction += "\n\nPOINTER SELECTIONS: When the `<primary_focus_selection>` is itself a cross-reference/pointer (e.g. \"see Section A4.2 (p580)\", \"Figure 19.1\", \"Eq. (3)\") and a `<resolved_cross_references>` block is present, the user wants the content of the REFERENCED TARGET, not the visible page. Answer using the resolved target text/section inside `<resolved_cross_references>`, treating the selection only as the address of what to explain. If a pointer was detected but `<resolved_cross_references>` is empty or lacks the needed text, say you could not locate the referenced target and answer from the available context instead of inventing it or silently explaining the current page. A `<unresolved_cross_references>` block lists pointers whose target text could not be retrieved from the material available — do NOT attempt to open, read, or search the source file yourself; say you could not retrieve the referenced item and answer from what you already have.";
  return instruction;
}
