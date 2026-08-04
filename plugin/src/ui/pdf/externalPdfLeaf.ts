import type { ExternalPdfView } from "./ExternalPdfView";
import { EXTERNAL_PDF_VIEW_TYPE } from "./externalPdfViewType";

/**
 * Methods every caller in `main.ts` invokes after narrowing a leaf to the
 * external-PDF view. A placeholder that answers the view type but lacks these
 * is not usable as one.
 */
const REQUIRED_METHODS = [
  "getRuntimePath",
  "getActivePdfContext",
  "getDisplayText",
  "getState",
] as const;

/**
 * Narrow an arbitrary `leaf.view` to a *loaded* {@link ExternalPdfView}.
 *
 * Obsidian >= 1.7.2 restores workspace tabs as **deferred** views: `leaf.view`
 * reports the real `getViewType()` while being a placeholder that carries none
 * of the concrete class's methods. A matching view-type string is therefore NOT
 * proof of class identity, and casting on it threw
 * `TypeError: getRuntimePath is not a function` out of `getLeafFile()` — which
 * feeds both `updateActiveContext()` and the open-tab inventory, taking the
 * context pins, sidechat Send, and the Quick Query popover down together.
 *
 * The check is capability-based rather than `instanceof` on purpose: it also
 * rejects a stale instance left behind by a previous bundle after an in-place
 * plugin update, which `instanceof` against the freshly loaded class would
 * likewise fail but which no version check can see. Callers fall back to the
 * leaf's persisted state, so a deferred tab degrades instead of throwing and is
 * never force-loaded as a side effect of building context.
 */
export function asLoadedExternalPdfView(view: unknown): ExternalPdfView | null {
  if (!view || typeof view !== "object") return null;
  const candidate = view as Record<string, unknown>;
  if (typeof candidate.getViewType !== "function") return null;
  if ((candidate.getViewType as () => unknown)() !== EXTERNAL_PDF_VIEW_TYPE) {
    return null;
  }
  for (const method of REQUIRED_METHODS) {
    if (typeof candidate[method] !== "function") return null;
  }
  return candidate as unknown as ExternalPdfView;
}
