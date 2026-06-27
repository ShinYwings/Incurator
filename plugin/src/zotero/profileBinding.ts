import type { ZoteroImportProfile } from "../types";

const ZOTERO_PROFILE_FIELD = "zotero_profile";

function quoteYamlString(value: string): string {
  return JSON.stringify(value);
}

export function stampZoteroProfile(markdown: string, profileName: string): string {
  const name = profileName.trim();
  if (!name) return markdown;

  const fieldLine = `${ZOTERO_PROFILE_FIELD}: ${quoteYamlString(name)}`;
  const fieldPattern = new RegExp(`^${ZOTERO_PROFILE_FIELD}\\s*:`);
  // Preserve the document's existing line-ending style so CRLF notes (Windows)
  // are not silently rewritten to LF.
  const eol = markdown.includes("\r\n") ? "\r\n" : "\n";
  const prepend = `---${eol}${fieldLine}${eol}---${eol}${eol}${markdown}`;

  // Split on either LF or CRLF so frontmatter detection works regardless of the
  // note's line endings; rejoin with the detected EOL to round-trip exactly.
  const lines = markdown.split(/\r?\n/);
  // A YAML frontmatter block must open with a lone '---' on the first line.
  if (lines[0] !== "---") return prepend;

  // The close is the first *lone* '---' line — never a '---' that merely appears
  // inside a value or a body horizontal rule (which is what naive substring
  // scanning would wrongly match).
  const closeIndex = lines.indexOf("---", 1);
  if (closeIndex < 0) return prepend;

  const frontmatter = lines
    .slice(1, closeIndex)
    .filter((line) => !fieldPattern.test(line));
  frontmatter.push(fieldLine);
  // lines.slice(closeIndex) keeps the closing '---' and everything after it,
  // preserving body content exactly.
  return ["---", ...frontmatter, ...lines.slice(closeIndex)].join(eol);
}

export function resolveZoteroRefreshProfile(
  profiles: ZoteroImportProfile[],
  frontmatter: Record<string, unknown> | undefined
): ZoteroImportProfile | undefined {
  const stamped = frontmatter?.[ZOTERO_PROFILE_FIELD];
  if (typeof stamped === "string" && stamped.trim()) {
    const match = profiles.find((profile) => profile.name === stamped.trim());
    if (match) return match;
  }
  return profiles[0];
}
