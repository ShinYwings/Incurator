import { basename } from "path";

/**
 * Pure resolution of a ContextService evidence locator into a clickable
 * open-target descriptor for the "Sources & Trace" panel.
 *
 * Kept free of Obsidian/Electron imports so the open-target decision (which
 * source kind opens where, and which anchor/page is applied) is behaviorally
 * unit-testable without an Obsidian `ItemView`. The actual opening side effects
 * live in `incuratorQueryTrace.ts`.
 */
export type LocatorTarget =
  | { kind: "vault" | "external" | "external_pdf"; label: string; linkpath: string; page?: number };

export function locatorTarget(locator: Record<string, unknown>): LocatorTarget | null {
  if (locator.locator_status === "unavailable") return null;
  const relpath = typeof locator.relpath === "string" ? locator.relpath : "";
  const externalUri = typeof locator.external_uri === "string" ? locator.external_uri : "";
  const sourceKind = typeof locator.source_kind === "string" ? locator.source_kind : "";
  const page = typeof locator.page_number === "number" ? locator.page_number : undefined;
  const pageLabel = page ? ` p.${page}` : "";

  // External Reference Mode sources are NOT in the vault: the file lives at
  // external_uri while relpath only points to an in-vault stub. Resolve the real
  // file first so a non-null stub path can't shadow it. PDFs open in the
  // plugin's own external PDF viewer at the cited page; other external
  // references open through the system handler.
  if (externalUri) {
    const isFilePath = !/^[a-z][a-z0-9+.-]*:\/\//i.test(externalUri);
    const isPdf = sourceKind === "vault_pdf" || /\.pdf($|[?#])/i.test(externalUri);
    if (isPdf && isFilePath) {
      return {
        kind: "external_pdf",
        label: `${basename(externalUri)}${pageLabel}`,
        linkpath: externalUri,
        page,
      };
    }
    return { kind: "external", label: externalUri, linkpath: externalUri };
  }

  if (relpath) {
    const heading = typeof locator.heading === "string" && locator.heading ? locator.heading : "";
    const blockId = typeof locator.block_id === "string" && locator.block_id ? locator.block_id : "";
    // Registered/vault PDFs jump to the cited page through Obsidian's native
    // viewer via the #page=N anchor; other notes use heading/block anchors.
    const anchor =
      sourceKind === "vault_pdf" && page
        ? `#page=${page}`
        : blockId
          ? `#^${blockId}`
          : heading
            ? `#${heading}`
            : "";
    return { kind: "vault", label: `${relpath}${pageLabel}${anchor}`, linkpath: `${relpath}${anchor}` };
  }
  return null;
}
