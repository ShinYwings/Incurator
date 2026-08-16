/**
 * Consulting the active workspace's notes at answer time (v0.57.0).
 *
 * The reader's own project notes are the raw material for duty 2 — "remind me
 * what I already wrote". Measured on the reporting vault: 137 markdown files on
 * disk, 36 ingested, and **75 of the gap are research notes inside one
 * workspace**. Duty 2 could not be true while those were invisible.
 *
 * They are deliberately NOT ingested (plan 05 §4.7, user decision).
 * `01_Workspaces` is the Artist Space: project studios holding `curate.yml`,
 * agent scaffolding, and notes bound to one project. Promoting that into a
 * vault-wide DAG mixes project-local working state into shared knowledge, which
 * is the separation the vault topology exists to maintain.
 *
 * So this is a retrieval path, not an ingestion one. Nothing here writes to the
 * DAG, to `state.sqlite`, or to `.curator/`. The index lives in memory for the
 * session and is rebuilt from the files themselves.
 *
 * **Bulk build, never per-call rebuild.** §4.7 rejected an ephemeral vault-wide
 * index precisely because it would copy `upsertPage`'s rebuild-per-call shape,
 * measured elsewhere at 331x the bulk path (26,881 ms against 81 ms for a
 * 673-page document). This builds once per workspace with `upsertDocument` and
 * reuses it until the workspace's files actually change.
 */
import { PdfDocumentIndexService } from "./pdfDocumentIndex";
import { WORKSPACES_DIR } from "./workspaceScope";

/** One note available for consultation. */
export interface WorkspaceNote {
  /** Vault-relative path, e.g. `01_Workspaces/Proj/Research Notes/svd.md`. */
  path: string;
  text: string;
  /** Last-modified epoch ms, used to notice edits without re-reading files. */
  mtime: number;
}

export interface WorkspaceNoteHit {
  path: string;
  score: number;
  snippet: string;
}

/**
 * The subset of the vault this module needs, so the selection rules can be
 * tested without an Obsidian app.
 */
export interface WorkspaceVaultPort {
  /** Vault-relative markdown paths with their mtimes. */
  list(): Array<{ path: string; mtime: number }>;
  read(path: string): Promise<string>;
}

/**
 * Paths inside a workspace that are machinery rather than the reader's notes.
 *
 * `.agents/` is the agent's own scaffolding — plans, relay state, reports.
 * Feeding it back as "notes you wrote" would have the assistant quoting its own
 * bookkeeping at the reader. Measured on the reporting vault: 13 of the
 * workspace's 88 markdown files are under `.agents/`, plus its `CLAUDE.md`.
 */
export function isConsultableNote(relpath: string): boolean {
  const p = relpath.replace(/\\/g, "/");
  if (!p.toLowerCase().endsWith(".md")) return false;
  const parts = p.split("/");
  if (parts.some((seg) => seg === ".agents" || seg === ".obsidian" || seg === ".curator")) {
    return false;
  }
  const name = parts[parts.length - 1];
  // Agent rule files are instructions to a tool, not the reader's thinking.
  if (name === "CLAUDE.md" || name === "AGENTS.md" || name === "GEMINI.md") return false;
  return true;
}

/** Notes belonging to `workspaceRelpath`, machinery excluded. */
export function notesInWorkspace(
  entries: Array<{ path: string; mtime: number }>,
  workspaceRelpath: string
): Array<{ path: string; mtime: number }> {
  if (!workspaceRelpath) return [];
  const prefix = `${workspaceRelpath.replace(/\/+$/, "")}/`;
  return entries.filter((e) => e.path.startsWith(prefix) && isConsultableNote(e.path));
}

/**
 * A cheap fingerprint of the workspace's files.
 *
 * Rebuilding the index costs a read of every note; recomputing this costs
 * nothing beyond the listing the vault already has. Any create, delete, rename,
 * or edit changes it.
 */
export function workspaceSignature(
  entries: Array<{ path: string; mtime: number }>
): string {
  return entries
    .map((e) => `${e.path}:${e.mtime}`)
    .sort()
    .join("|");
}

interface CachedIndex {
  signature: string;
  /** Index page number -> note path. The BM25 service is page-shaped. */
  paths: string[];
  service: PdfDocumentIndexService;
}

const cache = new Map<string, CachedIndex>();

/** Drop a workspace's cached index. Exported for tests and for vault reloads. */
export function forgetWorkspaceIndex(workspaceRelpath: string): void {
  cache.delete(workspaceRelpath);
}

/** How many notes a single consultation may return. */
export const WORKSPACE_NOTE_TOP_K = 4;

/**
 * Search the active workspace's notes for material bearing on `query`.
 *
 * Returns `[]` when there is no active workspace — a conversation outside a
 * project consults nothing, rather than falling back to the whole vault, which
 * would reintroduce exactly the vault-wide index §4.7 rejected.
 */
export async function searchWorkspaceNotes(
  vault: WorkspaceVaultPort,
  workspaceRelpath: string,
  query: string,
  topK: number = WORKSPACE_NOTE_TOP_K
): Promise<WorkspaceNoteHit[]> {
  if (!workspaceRelpath || !query.trim()) return [];

  const entries = notesInWorkspace(vault.list(), workspaceRelpath);
  if (entries.length === 0) return [];

  const signature = workspaceSignature(entries);
  let cached = cache.get(workspaceRelpath);
  if (!cached || cached.signature !== signature) {
    cached = await buildIndex(vault, workspaceRelpath, entries, signature);
    cache.set(workspaceRelpath, cached);
  }

  return cached.service
    .search(workspaceRelpath, query, { topK })
    .map((hit) => ({
      path: cached!.paths[hit.pageNum] ?? "",
      score: hit.score,
      snippet: hit.snippet,
    }))
    .filter((hit) => hit.path);
}

async function buildIndex(
  vault: WorkspaceVaultPort,
  workspaceRelpath: string,
  entries: Array<{ path: string; mtime: number }>,
  signature: string
): Promise<CachedIndex> {
  const paths: string[] = [];
  const pages = [];
  for (const entry of entries) {
    const text = await vault.read(entry.path).catch(() => "");
    if (!text.trim()) continue;
    // The BM25 service indexes "pages"; a note is one page and its index is its
    // page number. Reusing it means one measured-fast implementation rather
    // than a second scorer to keep correct.
    paths.push(entry.path);
    pages.push({ pageNum: paths.length - 1, text });
  }
  const service = new PdfDocumentIndexService();
  // Bulk build — the 81 ms path, not the 26,881 ms per-page loop.
  service.upsertDocument(workspaceRelpath, pages);
  return { signature, paths, service };
}

/** Characters of each note included in the block. */
const SNIPPET_LIMIT = 1200;

/**
 * Render consulted notes as a context block.
 *
 * The note tells the model these are the reader's OWN words, because that
 * changes what a correct answer looks like: quoting the reader back to
 * themselves is duty 2 working, and presenting their draft thinking as
 * established fact is not.
 */
export function buildWorkspaceNotesBlock(hits: WorkspaceNoteHit[]): string {
  if (hits.length === 0) return "";
  const body = hits
    .map((hit) => {
      const text = hit.snippet.length > SNIPPET_LIMIT
        ? `${hit.snippet.slice(0, SNIPPET_LIMIT)}…`
        : hit.snippet;
      return `<note path="${escapeAttribute(hit.path)}">\n${text}\n</note>`;
    })
    .join("\n");
  return (
    `<workspace_notes note="Notes the reader wrote themselves, in the project ` +
    `they are working in. Surface what they already concluded when it bears on ` +
    `the question, and attribute it to them — these are their working notes, ` +
    `not established fact.">\n${body}\n</workspace_notes>`
  );
}

function escapeAttribute(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/** Re-exported so callers do not need a second import for the folder name. */
export { WORKSPACES_DIR };
