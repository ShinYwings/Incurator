import { createHash } from "crypto";
import { describe, expect, it } from "vitest";

import { vaultMachineCacheDir } from "./machineCache";

describe("vaultMachineCacheDir", () => {
  it("places machine state under the repository cache using the vault hash", () => {
    const repo = process.cwd();
    const vault = process.cwd();
    const key = createHash("sha256").update(vault).digest("hex").slice(0, 16);

    expect(vaultMachineCacheDir(repo, vault)).toBe(
      `${repo}/.cache/vaults/${key}`
    );
  });
});
