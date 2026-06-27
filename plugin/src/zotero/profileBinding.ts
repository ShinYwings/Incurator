import type { ZoteroImportProfile } from "../types";

const ZOTERO_PROFILE_FIELD = "zotero_profile";

function quoteYamlString(value: string): string {
  return JSON.stringify(value);
}

export function stampZoteroProfile(markdown: string, profileName: string): string {
  const name = profileName.trim();
  if (!name) return markdown;

  const fieldLine = `${ZOTERO_PROFILE_FIELD}: ${quoteYamlString(name)}`;
  if (!markdown.startsWith("---\n")) {
    return `---\n${fieldLine}\n---\n\n${markdown}`;
  }

  const closingIndex = markdown.indexOf("\n---", 4);
  if (closingIndex < 0) {
    return `---\n${fieldLine}\n---\n\n${markdown}`;
  }

  const frontmatter = markdown
    .slice(4, closingIndex)
    .split("\n")
    .filter((line) => !line.match(new RegExp(`^${ZOTERO_PROFILE_FIELD}\\s*:`)));
  frontmatter.push(fieldLine);
  return `---\n${frontmatter.join("\n")}${markdown.slice(closingIndex)}`;
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
