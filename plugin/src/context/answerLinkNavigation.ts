export type AnswerLinkTarget =
  | { kind: "page"; pageNum: number; pageKind: "physical" | "printed" }
  | { kind: "section"; sectionNumber: string }
  | { kind: "vault"; linkpath: string };

const PAGE_PATTERNS = [
  { re: /(?:^|[#?&])page=(\d{1,5})(?:$|[&#])/i, pageKind: "physical" as const },
  { re: /\b(?:p|pp|page)\.?\s*(\d{1,5})\b/i, pageKind: "printed" as const },
];

const SECTION_PATTERNS = [
  /(?:^|[#?&])section=([A-Z]?\d+(?:\.\d+)*)(?:$|[&#])/i,
  /\b(?:section|sec)\.?\s*([A-Z]?\d+(?:\.\d+)*)\b/i,
  /§\s*([A-Z]?\d+(?:\.\d+)*)/i,
];

const VAULT_BLOCK_LINK_RE = /^([^#\n]+)#\^([A-Za-z0-9_-]+)$/;
const VAULT_BLOCK_LABEL_RE = /^(.+?)\s*>\s*\^([A-Za-z0-9_-]+)$/;

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
    const vaultTarget = parseVaultBlockTarget(value);
    if (vaultTarget) return vaultTarget;
  }
  return null;
}

function parseVaultBlockTarget(value: string): AnswerLinkTarget | null {
  const decoded = decodeHref(value).trim();
  if (!decoded || /^[a-z][a-z0-9+.-]*:/i.test(decoded)) return null;

  const direct = VAULT_BLOCK_LINK_RE.exec(decoded);
  if (direct?.[1] && direct[2]) {
    const note = direct[1].trim();
    if (note) return { kind: "vault", linkpath: `${note}#^${direct[2]}` };
  }

  const label = VAULT_BLOCK_LABEL_RE.exec(decoded);
  if (label?.[1] && label[2]) {
    const note = label[1].trim();
    if (note && !note.includes("://")) {
      return { kind: "vault", linkpath: `${note}#^${label[2]}` };
    }
  }

  return null;
}

function decodeHref(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}
