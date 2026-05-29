export interface FileScrollPosition {
  scroll: number;
  line: number;
  ch: number;
  updatedAt: number;
}

export interface LastMarkdownScrollPosition extends FileScrollPosition {
  path: string;
}

export function normalizeFileScrollPosition(
  value: unknown
): FileScrollPosition | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  const scroll = readNonNegativeNumber(record.scroll);
  const line = readNonNegativeNumber(record.line);
  const ch = readNonNegativeNumber(record.ch);
  if (scroll === null || line === null || ch === null) return null;
  return {
    scroll,
    line,
    ch,
    updatedAt: readNonNegativeNumber(record.updatedAt) ?? 0,
  };
}

export function normalizeLastMarkdownScrollPosition(
  value: unknown
): LastMarkdownScrollPosition | null {
  if (!value || typeof value !== "object") return null;
  const record = value as Record<string, unknown>;
  if (typeof record.path !== "string" || !record.path) return null;
  const position = normalizeFileScrollPosition(record);
  return position ? { ...position, path: record.path } : null;
}

export function upsertFileScrollPosition(
  positions: Record<string, FileScrollPosition | { scroll: number; line: number; ch: number }>,
  path: string,
  position: Pick<FileScrollPosition, "scroll" | "line" | "ch">,
  maxEntries = 100,
  now = Date.now()
): Record<string, FileScrollPosition> {
  const normalized: Record<string, FileScrollPosition> = {};
  for (const [key, value] of Object.entries(positions || {})) {
    const parsed = normalizeFileScrollPosition(value);
    if (parsed) normalized[key] = parsed;
  }

  normalized[path] = {
    scroll: Math.max(0, position.scroll),
    line: Math.max(0, position.line),
    ch: Math.max(0, position.ch),
    updatedAt: now,
  };

  const entries = Object.entries(normalized).sort(
    (a, b) => b[1].updatedAt - a[1].updatedAt
  );
  return Object.fromEntries(entries.slice(0, maxEntries));
}

function readNonNegativeNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? value
    : null;
}
