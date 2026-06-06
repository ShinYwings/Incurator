export type AnswerLinkTarget =
  | { kind: "page"; pageNum: number; pageKind: "physical" | "printed" }
  | { kind: "section"; sectionNumber: string };

const PAGE_PATTERNS = [
  { re: /(?:^|[#?&])page=(\d{1,5})(?:$|[&#])/i, pageKind: "physical" as const },
  { re: /\b(?:p|pp|page)\.?\s*(\d{1,5})\b/i, pageKind: "printed" as const },
];

const SECTION_PATTERNS = [
  /(?:^|[#?&])section=([A-Z]?\d+(?:\.\d+)*)(?:$|[&#])/i,
  /\b(?:section|sec)\.?\s*([A-Z]?\d+(?:\.\d+)*)\b/i,
  /§\s*([A-Z]?\d+(?:\.\d+)*)/i,
];

export function parseAnswerLinkTarget(
  hrefOrText: string | null | undefined,
  fallbackText = ""
): AnswerLinkTarget | null {
  const candidates = [hrefOrText || "", fallbackText || ""].filter(Boolean);
  for (const value of candidates) {
    for (const pattern of PAGE_PATTERNS) {
      const match = pattern.re.exec(value);
      const pageNum = match ? Number(match[1]) : NaN;
      if (Number.isFinite(pageNum) && pageNum > 0) {
        return { kind: "page", pageNum, pageKind: pattern.pageKind };
      }
    }
    for (const pattern of SECTION_PATTERNS) {
      const match = pattern.exec(value);
      if (match?.[1]) {
        return { kind: "section", sectionNumber: match[1].toUpperCase() };
      }
    }
  }
  return null;
}
