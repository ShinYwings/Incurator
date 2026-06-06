/**
 * Pure helpers for the "diff artifact" feature (user report item 20).
 *
 * When the agent proposes code/Markdown edits, the chat keeps a compact pill and
 * the full change is written to a separate Markdown note as unified-diff blocks.
 * These helpers build that note's content/filename and contain no Obsidian
 * imports so they stay unit-testable.
 */

/**
 * Fixed vault folder for artifacts. It lives under `00_System/`, which is NOT
 * one of the ingested `raw_dirs` (02_Wiki/03_Notes/04_Resources/06_Archives), so
 * artifact notes are never picked up as Curator sources by `wiki add`.
 */
export const ARTIFACT_DIR = "00_System/Agent Diffs";

export interface EditArtifactProposal {
  filepath: string;
  search: string;
  replace: string;
}

export interface EditArtifactMeta {
  title: string;
  sessionId: string;
  created: Date;
}

const NEW_FILE_MARKER = "<<< NEW FILE >>>";

/**
 * Render a single proposal as a fenced ```diff block: every `search` line is a
 * removal (`-`), every `replace` line is an addition (`+`). A new-file proposal
 * (empty search or an explicit NEW FILE marker) renders as additions only.
 */
export function buildEditDiffBlock(search: string, replace: string): string {
  const isNewFile = search.trim() === "" || search.includes(NEW_FILE_MARKER);
  const lines: string[] = [];
  if (!isNewFile) {
    for (const line of search.split("\n")) lines.push(`-${line}`);
  }
  for (const line of replace.split("\n")) lines.push(`+${line}`);
  return "```diff\n" + lines.join("\n") + "\n```";
}

/**
 * Build the full artifact note: `agent-diff-artifact` frontmatter, a heading,
 * and one section per target file grouping that file's diff blocks.
 */
export function buildEditArtifactMarkdown(
  proposals: EditArtifactProposal[],
  meta: EditArtifactMeta
): string {
  const files: string[] = [];
  for (const p of proposals) {
    if (!files.includes(p.filepath)) files.push(p.filepath);
  }

  const frontmatter = [
    "---",
    "type: agent-diff-artifact",
    `created: ${meta.created.toISOString()}`,
    `session: ${meta.sessionId}`,
    "files:",
    ...files.map((f) => `  - ${f}`),
    "---",
  ].join("\n");

  const sections: string[] = [];
  for (const file of files) {
    const blocks = proposals
      .filter((p) => p.filepath === file)
      .map((p) => buildEditDiffBlock(p.search, p.replace));
    sections.push(`## ${file}\n\n${blocks.join("\n\n")}`);
  }

  const intro =
    "> Generated from a chat answer. Apply or review hunks via the chat's " +
    "**Review Diff** buttons, or copy them manually.";

  return (
    `${frontmatter}\n\n` +
    `# Proposed edits — ${meta.title}\n\n` +
    `${intro}\n\n` +
    `${sections.join("\n\n")}\n`
  );
}

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

/**
 * `YYYY-MM-DD_HHmm_<slug>.md`. The slug is the first target's basename (without
 * extension), sanitized to a filesystem-safe form; falls back to `edits`.
 */
export function buildEditArtifactFilename(
  proposals: EditArtifactProposal[],
  created: Date
): string {
  const date =
    `${created.getUTCFullYear()}-` +
    `${pad2(created.getUTCMonth() + 1)}-` +
    `${pad2(created.getUTCDate())}`;
  const time = `${pad2(created.getUTCHours())}${pad2(created.getUTCMinutes())}`;

  const first = proposals[0]?.filepath ?? "";
  const base = (first.split("/").pop() ?? "").replace(/\.[^.]+$/, "");
  const slug =
    base
      .replace(/[^A-Za-z0-9_]+/g, "-")
      .replace(/^-+|-+$/g, "") || "edits";

  return `${date}_${time}_${slug}.md`;
}
