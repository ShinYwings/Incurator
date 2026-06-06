import type { ContextRef } from "../types";

export type GitSidechatCommand =
  | { kind: "status" }
  | { kind: "push" }
  | { kind: "history"; filePath: string; queryText: string };

interface ActiveContextLike {
  viewType?: string;
  filePath?: string;
  absolutePath?: string;
}

export function detectGitSidechatCommand(
  message: string,
  contextRefs: ContextRef[] = [],
  activeCtx?: ActiveContextLike | null
): GitSidechatCommand | null {
  const normalized = message.toLowerCase();
  if (isHistoryRequest(normalized)) {
    const target = findHistoryTarget(contextRefs, activeCtx);
    if (target.filePath) {
      return { kind: "history", filePath: target.filePath, queryText: target.queryText };
    }
  }
  if (isPushRequest(normalized)) return { kind: "push" };
  if (isStatusRequest(normalized)) return { kind: "status" };
  return null;
}

function isPushRequest(value: string): boolean {
  return (
    /\bpush\b/.test(value) ||
    value.includes("push해") ||
    value.includes("푸시") ||
    (value.includes("github") && (value.includes("올려") || value.includes("동기화")))
  );
}

function isStatusRequest(value: string): boolean {
  return (
    value.includes("unpushed") ||
    value.includes("푸시되지") ||
    (value.includes("git") || value.includes("github")) &&
    (value.includes("status") ||
      value.includes("상태") ||
      value.includes("ahead") ||
      value.includes("behind"))
  );
}

function isHistoryRequest(value: string): boolean {
  return (
    value.includes("history") ||
    value.includes("히스토리") ||
    value.includes("바뀌") ||
    value.includes("변경 내역") ||
    value.includes("변경사항") ||
    value.includes("예전에")
  );
}

function findHistoryTarget(
  contextRefs: ContextRef[],
  activeCtx?: ActiveContextLike | null
): { filePath: string; queryText: string } {
  const selected = contextRefs.find(
    (ref) =>
      (ref.type === "selection" || ref.type === "line-range" || ref.type === "text") &&
      Boolean(ref.filePath) &&
      Boolean(ref.content?.trim())
  );
  if (selected?.filePath) {
    return {
      filePath: selected.filePath,
      queryText: normalizeHistoryQuery(selected.content),
    };
  }

  const filePath =
    activeCtx?.viewType === "markdown"
      ? activeCtx.absolutePath || activeCtx.filePath || ""
      : activeCtx?.absolutePath || activeCtx?.filePath || "";
  return { filePath, queryText: "" };
}

function normalizeHistoryQuery(value: string): string {
  return value.replace(/\s+/g, " ").trim().slice(0, 240);
}
