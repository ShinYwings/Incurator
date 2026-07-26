const OPEN_TAB_CONTENT_VIEW_TYPES = new Set([
  "markdown",
  "pdf",
  "ai-agent-external-pdf",
]);

export function isEligibleOpenTabView(viewType: string): boolean {
  return OPEN_TAB_CONTENT_VIEW_TYPES.has(viewType);
}

export interface OpenTabIdentity {
  viewType: string;
  sourceIdentity?: string;
  filePath?: string;
  label: string;
  pageNum?: number;
}

export interface OpenTabLayoutContext extends OpenTabIdentity {
  sourceIdentity: string;
}

export function buildOpenTabContextKey(tab: OpenTabIdentity): string {
  const identity = tab.sourceIdentity || tab.filePath || tab.label;
  return JSON.stringify([tab.viewType, identity, tab.pageNum ?? null]);
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null
    ? value as Record<string, unknown>
    : null;
}

function finitePage(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim() && Number.isFinite(Number(value))) {
    return Number(value);
  }
  return undefined;
}

/**
 * Return identity-only contexts for every eligible leaf saved in Obsidian's
 * public workspace layout. Some hidden tabs in pop-out tab groups are deferred
 * and therefore do not appear in iterateAllLeaves() until activated.
 */
export function collectOpenTabLayoutContexts(
  layout: unknown
): OpenTabLayoutContext[] {
  const tabs = new Map<string, OpenTabLayoutContext>();
  const visited = new Set<object>();

  const visit = (value: unknown): void => {
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }

    const node = record(value);
    if (!node || visited.has(node)) return;
    visited.add(node);

    if (node.type === "leaf") {
      const viewState = record(node.state);
      const state = record(viewState?.state) ?? {};
      const viewType =
        typeof viewState?.type === "string" ? viewState.type : "";
      if (isEligibleOpenTabView(viewType)) {
        const filePath =
          typeof state.file === "string" ? state.file : undefined;
        const fallbackLabel =
          filePath?.split("/").pop()?.replace(/\.[^/.]+$/, "") || viewType;
        const label =
          typeof viewState?.title === "string"
            ? viewState.title
            : typeof state.name === "string"
              ? state.name
              : fallbackLabel;
        const pageNum =
          viewType === "ai-agent-external-pdf"
            ? finitePage(state.currentPage)
            : viewType === "pdf"
              ? finitePage(state.page)
              : undefined;
        const sourceIdentity =
          viewType === "ai-agent-external-pdf"
            ? typeof state.zoteroAttachmentKey === "string"
              ? `zotero:${state.zoteroAttachmentKey}`
              : typeof state.externalRef === "string"
                ? `external:${state.externalRef}`
                : typeof state.docId === "string"
                  ? `document:${state.docId}`
                  : filePath || label
            : filePath || label;
        const tab: OpenTabLayoutContext = {
          viewType,
          sourceIdentity,
          filePath,
          label,
          pageNum,
        };
        tabs.set(buildOpenTabContextKey(tab), tab);
      }
    }

    Object.values(node).forEach(visit);
  };

  visit(layout);
  return Array.from(tabs.values());
}

export interface OpenTabInclusionState {
  isVisible: boolean;
  isReady: boolean;
  explicitlyIncluded: boolean;
  explicitlyExcluded: boolean;
}

export function shouldIncludeOpenTab(state: OpenTabInclusionState): boolean {
  if (!state.isReady || state.explicitlyExcluded) return false;
  if (state.explicitlyIncluded) return true;
  return state.isVisible;
}
