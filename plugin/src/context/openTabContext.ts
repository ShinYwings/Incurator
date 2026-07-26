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

export function buildOpenTabContextKey(tab: OpenTabIdentity): string {
  const identity = tab.sourceIdentity || tab.filePath || tab.label;
  return JSON.stringify([tab.viewType, identity, tab.pageNum ?? null]);
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
