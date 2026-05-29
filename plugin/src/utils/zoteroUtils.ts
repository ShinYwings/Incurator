export interface ZoteroLinkInfo {
  attachmentKey: string;
  pageNum?: number;
  annotationKey?: string;
}

export function parseZoteroLink(href: string): ZoteroLinkInfo | null {
  const match = href.match(/^zotero:\/\/(?:open-pdf|select)\/library\/items\/([A-Z0-9]+)/i);
  if (!match) return null;

  const info: ZoteroLinkInfo = { attachmentKey: match[1] };
  try {
    const url = new URL(href);
    if (url.searchParams.get("viewer") === "zotero") {
      return null; // Bypass interceptor, let OS open Zotero
    }
    const pageParam = url.searchParams.get("page");
    if (pageParam) {
      const pageNum = parseInt(pageParam, 10);
      if (!isNaN(pageNum) && pageNum > 0) {
        info.pageNum = pageNum;
      }
    }
    const annotationParam = url.searchParams.get("annotation");
    if (annotationParam) {
      info.annotationKey = annotationParam;
    }
  } catch (err) {}

  return info;
}
