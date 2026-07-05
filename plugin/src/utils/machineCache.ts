import { createHash } from "crypto";
import { realpathSync } from "fs";
import { join, resolve } from "path";

function canonicalPath(path: string): string {
  try {
    return realpathSync(path);
  } catch {
    return resolve(path);
  }
}

export function vaultMachineCacheDir(
  repoPath: string,
  vaultRoot: string
): string {
  const key = createHash("sha256")
    .update(canonicalPath(vaultRoot))
    .digest("hex")
    .slice(0, 16);
  return join(canonicalPath(repoPath), ".cache", "vaults", key);
}
