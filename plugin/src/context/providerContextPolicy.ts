import type { ContextRef } from "../types";
import { includedContextRefs, isPrimaryUserContext } from "./chatContextPriority";

const SHORT_FOLLOW_UP_RE = /^(again|retry|redo|regenerate|once more|다시|다시 해줘|한번 더|재시도)$/i;

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

export function shouldRunCuratorDomainQuery(args: {
  query: string;
  userContextRefs?: ContextRef[];
}): boolean {
  const query = args.query.trim();
  if (!query) return false;
  if (SHORT_FOLLOW_UP_RE.test(query)) return false;
  if (hasPrimarySelectedContext(args.userContextRefs)) return false;
  return true;
}
