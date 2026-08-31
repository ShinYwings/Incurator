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

/**
 * Which pointer blocks this turn can actually contain.
 *
 * The POINTER SELECTIONS paragraph below names `<resolved_cross_references>`,
 * `<resolved_citations>` and `read_pdf_page_image`. On a markdown-note turn none
 * of those can exist — the resolvers that produce them are gated on an open PDF —
 * so it was ~1,700 characters of instruction about blocks the model would never
 * see, on every note turn. That is the shape v0.54.1 removed a universal rule
 * for: a prohibition naming strings that never appear is dilution of the
 * instructions that do apply.
 *
 * Notes have their own pointer — the wikilink — so they get a sentence about
 * that instead of nothing.
 */
export type PointerKind = "pdf" | "markdown" | "none";

export function contextPriorityInstruction(
  hasPrimaryContext: boolean,
  pointers: PointerKind
): string {
  let instruction = "";
  if (!hasPrimaryContext) {
    instruction = "Pinned and visible Obsidian contexts (wrapped in `<background_reference_only>`, `<obsidian_incurator_context>`, or document outline tags) are the user's own notes and reading material. Draw on them: when one bears on the question, bring it into the answer and say what it adds — a note the user wrote and forgot is one of the most useful things you can surface. Where two sources meet, name the implication rather than restating each. Summarising this material back to the user, on its own, is not an answer."
  } else {
    instruction = "Primary user-selected context is the MAIN FOCUS of the current request. You MUST actively use the pinned and visible Obsidian context (wrapped in `<background_reference_only>`, `<obsidian_incurator_context>`, or document outline tags) to enrich your answer: connect the selected text to the user's own notes and to the current page/ToC, and name what that connection implies. Keep the selection the subject — the background is what you reason WITH, not what you report ON.";
  }
  
  instruction += "\n\nCRITICAL: When a file context contains `<primary_focus_selection>`, treat it as the absolute core subject. Treat `<background_reference_only>`, `<obsidian_incurator_context>`, `<markdown_outlines>`, and `<document_outline>` as supplementary material for resolving references. You MUST NOT explain the entire document or current page when a primary focus selection is provided. Focus strictly on answering the user's query regarding the `<primary_focus_selection>`.";
  if (pointers === "pdf") {
    instruction += "\n\nPOINTER SELECTIONS: When the `<primary_focus_selection>` is itself a cross-reference/pointer (e.g. \"see Section A4.2 (p580)\", \"Figure 19.1\", \"Eq. (3)\") and a `<resolved_cross_references>` block is present, the user wants the content of the REFERENCED TARGET, not the visible page. Answer using the resolved target text/section inside `<resolved_cross_references>`, treating the selection only as the address of what to explain. If `<resolved_cross_references>` lacks the target's text, answer about the referenced target using what the surrounding material does establish about it — its section, its role in the argument, the results that depend on it — and keep every statement traceable to the material given. A `<resolved_citations>` block holds bibliography entries for works the selection cites, and a `<workspace_notes>` block holds notes the reader wrote themselves; both carry their own instructions — follow them. A `<unresolved_cross_references>` block names pointers whose text is not in this context; when `read_pdf_page_image` is among the tools you were given, call it on the page a pointer names — an equation drawn as a picture has no text to find, and reading that page as an image is how you answer it. If you were not given that tool, treat those pointers as targets to describe from what you have. Write for a reader who cannot see this context: describe the paper, never the retrieval. Statements about what is or is not loaded, which blocks you received, or whether something is general knowledge are not part of an answer.";
  } else if (pointers === "markdown") {
    instruction += "\n\nPOINTER SELECTIONS: A `<resolved_wikilinks>` block, when present, holds the notes this note links to, already read for you. Answer about a linked note from its content there rather than from its title. Write for a reader who cannot see this context: describe the material, never the retrieval.";
  }
  return instruction;
}
