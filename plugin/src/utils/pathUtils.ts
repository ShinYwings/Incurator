/**
 * Infer the Incurator import destination from a co-open markdown note path.
 *
 * If `mdPath` is under `03_Notes/…`, the subfolder structure is mirrored
 * under `defaultDestination` and the note name (without extension) becomes
 * the final segment so the PDF lands alongside the note's resource folder.
 *
 * Example: 03_Notes/Vision/Foo.md → 04_Resources/Vision/Foo
 *
 * Falls back to `defaultDestination` when no 03_Notes path is supplied.
 */
export function inferIngestDestination(
  mdPath: string | undefined,
  defaultDestination: string
): string {
  const base = defaultDestination.replace(/\/+$/, "") || "04_Resources";
  if (!mdPath?.startsWith("03_Notes/")) return base;

  const withoutPrefix = mdPath.slice("03_Notes/".length);
  const segments = withoutPrefix.split("/").filter(Boolean);
  const noteName = segments.pop()?.replace(/\.[^.]+$/, "") || "";
  const folder = segments.join("/");
  return [base, folder, noteName].filter(Boolean).join("/");
}
