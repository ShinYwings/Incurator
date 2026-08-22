import type { ContextRef, IncuratorSourceStatus } from "../types";
import { includedContextRefs, isPrimaryUserContext } from "./chatContextPriority";

const SHORT_FOLLOW_UP_RE = /^(again|retry|redo|regenerate|once more|다시|다시 해줘|한번 더|재시도)$/i;

/** An instruction to ACT ON the selected text rather than a question about it.
 *
 * The vault query used to be skipped whenever a selection existed at all, which
 * its own test described as "selected-context edits" and illustrated with
 * "rewrite this". The intent was right and the condition was too wide: it also
 * suppressed "what else have I written about this?", which is duty 2 itself.
 * Matching the request instead of the ref keeps the original protection and
 * returns the retrieval to the question that needs it. */
const EDIT_COMMAND_RE =
  /\b(rewrite|reword|rephrase|paraphrase|edit|fix|correct|shorten|expand|translate|proofread|polish|format)\b|(고쳐|수정해|다시\s*써|바꿔|번역|요약해\s*줘)/i;

export function hasPrimaryImageContext(refs: ContextRef[] | undefined): boolean {
  return includedContextRefs(refs).some(
    (ref) => isPrimaryUserContext(ref) && Boolean(ref.imageBase64)
  );
}

export function hasPrimarySelectedContext(refs: ContextRef[] | undefined): boolean {
  return includedContextRefs(refs).some(
    (ref) =>
      isPrimaryUserContext(ref) &&
      (ref.type === "image" ||
        ref.type === "pdf-page" ||
        ref.type === "selection" ||
        ref.type === "line-range")
  );
}

export function shouldUseBackendPdfContext(args: {
  query: string;
  userContextRefs?: ContextRef[];
  hasLocalViewerContext?: boolean;
}): boolean {
  if (hasPrimaryImageContext(args.userContextRefs)) return false;
  if (args.hasLocalViewerContext) return false;
  return true;
}

export interface PdfReferenceFocusTarget {
  isActive: boolean;
  openTabKey: string;
  filePath?: string;
  fileHash?: string;
  zoteroAttachmentKey?: string;
}

function openTabDocumentKey(openTabKey: string | undefined): string | undefined {
  if (!openTabKey) return undefined;
  try {
    const parsed: unknown = JSON.parse(openTabKey);
    if (
      !Array.isArray(parsed) ||
      parsed.length < 2 ||
      typeof parsed[0] !== "string" ||
      typeof parsed[1] !== "string"
    ) {
      return undefined;
    }
    return JSON.stringify([parsed[0], parsed[1]]);
  } catch {
    return undefined;
  }
}

function sameDefinedIdentity(left: string | undefined, right: string | undefined): boolean {
  return Boolean(left && right && left === right);
}

function primaryPdfRefMatchesTarget(
  ref: ContextRef,
  target: PdfReferenceFocusTarget
): boolean {
  if (ref.type !== "pdf-page" || !isPrimaryUserContext(ref)) return false;

  const refDocumentKey = openTabDocumentKey(ref.openTabKey);
  const targetDocumentKey = openTabDocumentKey(target.openTabKey);
  return (
    sameDefinedIdentity(refDocumentKey, targetDocumentKey) ||
    sameDefinedIdentity(ref.zoteroAttachmentKey, target.zoteroAttachmentKey) ||
    sameDefinedIdentity(ref.fileHash, target.fileHash) ||
    sameDefinedIdentity(ref.filePath, target.filePath)
  );
}

export function shouldResolveLatestUserPdfReferences(args: {
  target: PdfReferenceFocusTarget;
  userContextRefs?: ContextRef[];
}): boolean {
  if (args.target.isActive) return true;
  return includedContextRefs(args.userContextRefs).some((ref) =>
    primaryPdfRefMatchesTarget(ref, args.target)
  );
}

export function shouldRunCuratorDomainQuery(args: {
  query: string;
  userContextRefs?: ContextRef[];
  pdfFocused?: boolean;
  pdfSourceStatuses?: IncuratorSourceStatus[];
}): boolean {
  const query = args.query.trim();
  if (!query) return false;
  if (SHORT_FOLLOW_UP_RE.test(query)) return false;
  // Only an EDIT of the selection skips the vault. A question about it does not:
  // "이거 무슨 뜻이야? 내가 쓴 다른 노트 중 관련된 게 있어?" is duty 2, and the
  // blanket selection rule turned off the only retrieval that answers it.
  if (hasPrimarySelectedContext(args.userContextRefs) && EDIT_COMMAND_RE.test(query)) {
    return false;
  }
  // L3 is NOT a gate on retrieval. It governs how an answer may be framed —
  // "concept-grounded" — which is a prompt concern, not a reason to withhold
  // evidence. Measured on a live vault: `l3_status='done'` for 0 of 44 sources
  // (34 error, 2 pending, 8 skipped), so this condition could never pass and the
  // vault query never ran while any PDF tab was focused. And the fetch does not
  // need L3: the same question returned `route: local` with 30 evidence items
  // and 26 source spans while `community_report_ids` was 0.
  return true;
}
