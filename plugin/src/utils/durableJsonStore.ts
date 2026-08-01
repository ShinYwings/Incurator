export interface VaultTextAdapter {
  exists(path: string): Promise<boolean>;
  read(path: string): Promise<string>;
  write(path: string, data: string): Promise<void>;
  rename(source: string, target: string): Promise<void>;
  remove(path: string): Promise<void>;
  process(path: string, update: (raw: string) => string): Promise<string>;
}

export type JsonObjectState =
  | { kind: "missing" }
  | { kind: "valid"; value: Record<string, unknown>; raw: string }
  | { kind: "corrupt"; raw: string; error: unknown }
  | { kind: "unreadable"; error: unknown };

export async function readJsonObjectState(
  adapter: VaultTextAdapter,
  path: string
): Promise<JsonObjectState> {
  try {
    if (!(await adapter.exists(path))) return { kind: "missing" };
  } catch (error) {
    return { kind: "unreadable", error };
  }

  let raw: string;
  try {
    raw = await adapter.read(path);
  } catch (error) {
    return { kind: "unreadable", error };
  }

  try {
    const value = JSON.parse(raw) as unknown;
    if (value === null || typeof value !== "object" || Array.isArray(value)) {
      throw new TypeError("durable JSON root must be an object");
    }
    return { kind: "valid", value: value as Record<string, unknown>, raw };
  } catch (error) {
    return { kind: "corrupt", raw, error };
  }
}

export async function atomicWriteVaultText(
  adapter: VaultTextAdapter,
  path: string,
  data: string
): Promise<void> {
  const slash = path.lastIndexOf("/");
  const directory = slash >= 0 ? path.slice(0, slash + 1) : "";
  const filename = slash >= 0 ? path.slice(slash + 1) : path;
  const tempPath = `${directory}.${filename}.tmp-${Date.now()}-${Math.random()
    .toString(36)
    .slice(2)}`;

  try {
    await adapter.write(tempPath, data);
    await adapter.rename(tempPath, path);
  } catch (error) {
    try {
      await adapter.remove(tempPath);
    } catch {
      // Preserve the original replacement error; the canonical file is intact.
    }
    throw error;
  }
}
