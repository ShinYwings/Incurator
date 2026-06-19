/**
 * Curator DAG wikilink resolution.
 *
 * The L1–L4 DAG lives under the hidden `.curator/Collections/` folder, which
 * Obsidian's `metadataCache` never indexes — so a `[[02_Atoms/ATM-…]]` link
 * renders as a dead, unresolved internal link with no click, hover, graph, or
 * backlink behavior. These helpers detect curator-layer link targets and rewrite
 * the rendered anchors into clickable links that open the hidden page via
 * `workspace.openLinkText`. Navigation only: hidden nodes never enter the native
 * Graph view or Backlinks pane (see docs/specs/plugin_schema/PLUGIN_SCHEMA.md).
 */

/** Curator layer folder → node-ID prefix. */
export const CURATOR_LAYER_PREFIX: Record<string, string> = {
  "01_Contexts": "CTX",
  "02_Atoms": "ATM",
  "03_Concepts": "CON",
  "04_Synthesis": "SYN",
};

const COLLECTIONS_DIR = ".curator/Collections";

// Matches a curator-layer link target with an optional `.curator/Collections/`
// prefix, an optional `.md` suffix, and an optional `#heading` / `#^block`
// subpath. The layer/prefix pairing is validated separately in parseCuratorTarget.
// Greedy `[\w-]+` (not lazy): the ID charset (`\w`, `-`) cannot overlap the `.md`
// suffix (`.`) or `#` subpath separator, so a greedy match never has to backtrack.
const CURATOR_LINK_RE =
  /^(?:\.curator\/Collections\/)?(01_Contexts|02_Atoms|03_Concepts|04_Synthesis)\/((?:CTX|ATM|CON|SYN)-[\w-]+)(?:\.md)?(#.*)?$/;

export interface CuratorTarget {
  /** Layer folder, e.g. "02_Atoms". */
  layer: string;
  /** Node ID, e.g. "ATM-9f8e7d6c". */
  id: string;
  /** Hidden vault path: ".curator/Collections/<layer>/<id>.md". */
  path: string;
  /** Link text for openLinkText (path + any "#subpath"). */
  linktext: string;
  /** Heading/block subpath including the leading "#", or "". */
  subpath: string;
}

/**
 * Parse a rendered link target into a curator DAG target, or null if it is not a
 * curator-layer link. Accepts the bare `layer/ID` form, the
 * `.curator/Collections/layer/ID` form, a trailing `.md`, a `#subpath`, and a
 * defensive `|alias` tail.
 */
export function parseCuratorTarget(
  href: string | null | undefined
): CuratorTarget | null {
  if (!href) return null;
  // Obsidian's data-href omits the "|alias", but a raw body link may not.
  const raw = href.split("|", 1)[0].trim();
  const m = CURATOR_LINK_RE.exec(raw);
  if (!m) return null;
  const [, layer, id, hash] = m;
  // The ID prefix must match its layer (reject e.g. 02_Atoms/CON-…).
  if (!id.startsWith(`${CURATOR_LAYER_PREFIX[layer]}-`)) return null;
  const subpath = hash ?? "";
  const path = `${COLLECTIONS_DIR}/${layer}/${id}.md`;
  return { layer, id, path, linktext: path + subpath, subpath };
}

export interface RewriteDeps {
  /** Open the hidden page (wraps workspace.openLinkText). */
  open: (linktext: string) => void;
  /** Whether the hidden target file exists (wraps vault.getAbstractFileByPath != null). */
  exists: (path: string) => boolean;
}

/**
 * Rewrite every curator-layer wikilink anchor under `root` into a clickable link
 * that opens the hidden DAG page. Idempotent per element (guarded by the
 * `data-curatorTarget` marker), so re-processing a persistent reading-view
 * section never double-binds. Returns the number of anchors rewritten.
 */
export function rewriteCuratorLinks(root: HTMLElement, deps: RewriteDeps): number {
  const anchors = root.querySelectorAll<HTMLAnchorElement>(
    "a.internal-link, a[data-href]"
  );
  let count = 0;
  anchors.forEach((a) => {
    if (a.dataset.curatorTarget) return; // already rewritten
    const href = a.getAttribute("data-href") ?? a.getAttribute("href");
    const target = parseCuratorTarget(href);
    if (!target) return;
    a.dataset.curatorTarget = target.path;
    a.classList.add("incurator-curator-link");
    // The link is resolvable by us even though Obsidian flagged it unresolved.
    a.classList.remove("is-unresolved");
    if (!deps.exists(target.path)) {
      a.classList.add("is-missing");
    }
    // Anchors are rebuilt on every render, so the listener is GC'd with the node.
    a.addEventListener("click", (evt) => {
      evt.preventDefault();
      evt.stopPropagation();
      deps.open(target.linktext);
    });
    count++;
  });
  return count;
}
