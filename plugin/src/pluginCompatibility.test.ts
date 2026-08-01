import { readFileSync } from "fs";
import { resolve } from "path";
import { describe, expect, it } from "vitest";

function readJson(path: string): Record<string, string> {
  return JSON.parse(readFileSync(resolve(process.cwd(), path), "utf8")) as Record<
    string,
    string
  >;
}

describe("Obsidian compatibility boundaries", () => {
  it("requires the atomic adapter API and retains the 1.0.x fallback", () => {
    const manifest = readJson("manifest.json");
    const versions = readJson("versions.json");

    expect(manifest.minAppVersion).toBe("1.1.0");
    expect(versions["0.39.2"]).toBe("1.0.0");
    expect(versions["0.40.0"]).toBe("1.1.0");
  });
});
