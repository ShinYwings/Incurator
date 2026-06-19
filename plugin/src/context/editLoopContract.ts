/**
 * Runtime validator for the edit-loop state machine (v0.14.0).
 *
 * Pure and unit-testable. Parses an assistant response for the canonical phase
 * markers emitted under the `getEditLoopContract()` prompt block and decides
 * whether an edit-bearing response satisfies the four-phase loop
 * (Analysed -> Reviewed -> Updated -> Reviewed). The chat sidebar uses the
 * result to hard-gate the Diff Viewer entry point: an edit proposal that skips
 * the loop must not auto-open for review.
 */

export type PhaseLabel = "ANALYSED" | "REVIEWED" | "UPDATED";

export interface PhaseMarker {
  label: PhaseLabel;
  /** Character index of the marker within the response content. */
  index: number;
}

export interface EditLoopParse {
  phases: PhaseMarker[];
  /** Number of `ai-agent-edit` fenced blocks found in the content. */
  editBlocks: number;
}

export interface EditLoopValidation {
  /** True when the content contains at least one `ai-agent-edit` block. */
  hasEdits: boolean;
  /** True when the loop is satisfied, or when no edits require it. */
  ok: boolean;
  /** Human-readable list of missing/mis-ordered phases (empty when ok). */
  missing: string[];
}

const PHASE_MARKER_RE = /\[\[PHASE:(ANALYSED|REVIEWED|UPDATED)\]\]/g;
const EDIT_BLOCK_RE = /```ai-agent-edit\b/gi;

/** Parse phase markers (in document order) and count `ai-agent-edit` blocks. */
export function parseEditLoopPhases(content: string): EditLoopParse {
  const text = content ?? "";
  const phases: PhaseMarker[] = [];
  for (const m of text.matchAll(PHASE_MARKER_RE)) {
    phases.push({ label: m[1] as PhaseLabel, index: m.index ?? 0 });
  }
  const editBlocks = (text.match(EDIT_BLOCK_RE) || []).length;
  return { phases, editBlocks };
}

/**
 * Validate the four-phase loop. The contract is required ONLY when the response
 * contains at least one edit block. The required sequence is:
 *   ANALYSED → REVIEWED (pre-edit) → UPDATED → REVIEWED (post-edit)
 * Order matters: the first REVIEWED must precede UPDATED and a second REVIEWED
 * must follow it.
 */
export function validateEditLoop(content: string): EditLoopValidation {
  const { phases, editBlocks } = parseEditLoopPhases(content);
  const hasEdits = editBlocks > 0;
  if (!hasEdits) return { hasEdits: false, ok: true, missing: [] };

  const missing: string[] = [];
  const labels = phases.map((p) => p.label);

  const analysedIdx = labels.indexOf("ANALYSED");
  const updatedIdx = labels.indexOf("UPDATED");
  // First REVIEWED that comes before UPDATED, and one that comes after it.
  const preReviewIdx = labels.findIndex(
    (l, i) => l === "REVIEWED" && updatedIdx >= 0 && i < updatedIdx
  );
  const postReviewIdx =
    updatedIdx >= 0
      ? labels.findIndex((l, i) => l === "REVIEWED" && i > updatedIdx)
      : -1;

  if (analysedIdx < 0) missing.push("ANALYSED");
  if (preReviewIdx < 0) missing.push("REVIEWED (pre-edit)");
  if (updatedIdx < 0) missing.push("UPDATED");
  if (postReviewIdx < 0) missing.push("REVIEWED (post-edit)");

  // Order check: ANALYSED → pre-REVIEWED → UPDATED → post-REVIEWED.
  const ordered =
    analysedIdx >= 0 &&
    preReviewIdx > analysedIdx &&
    updatedIdx > preReviewIdx &&
    postReviewIdx > updatedIdx;

  const ok = missing.length === 0 && ordered;
  if (!ok && missing.length === 0) missing.push("phases out of order");
  return { hasEdits, ok, missing };
}
