import { describe, expect, it, beforeEach } from "vitest";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { join } from "path";
import { buildGuiCliSearchPaths, CLIAuthResolver } from "./cliAuth";

function cliAuthSource(): string {
  const dir = fileURLToPath(new URL(".", import.meta.url));
  return readFileSync(join(dir, "cliAuth.ts"), "utf8");
}

describe("buildGuiCliSearchPaths", () => {
  it("includes common macOS GUI and Node manager binary locations", () => {
    const paths = buildGuiCliSearchPaths("/Users/example");
    expect(paths).toContain("/opt/homebrew/bin");
    expect(paths).toContain("/Users/example/.volta/bin");
    expect(paths).toContain("/Users/example/.bun/bin");
    expect(paths).toContain("/Users/example/.npm-global/bin");
  });
});

describe("getAccountInfo", () => {
  let resolver: CLIAuthResolver;
  beforeEach(() => { resolver = new CLIAuthResolver(); });
  
  it("returns Local for ollama", () => {
    expect(resolver.getAccountInfo("ollama").name).toBe("Local (no account)");
  });
  
  it("returns API key configured for deepseek", () => {
    expect(resolver.getAccountInfo("deepseek").name).toBe("API key configured");
  });
  
  it("returns CLI-managed for claude", () => {
    expect(resolver.getAccountInfo("claude").name).toBe("Authenticated (CLI-managed)");
  });

  it("claims the Antigravity account if readable, else falls back", () => {
    const info = resolver.getAccountInfo("antigravity");
    if (info.email !== undefined) {
      expect(typeof info.email).toBe("string");
    } else {
      expect(info.name).toBe("agy CLI session");
    }
  });
});

describe("signOut", () => {
  let resolver: CLIAuthResolver;
  beforeEach(() => { resolver = new CLIAuthResolver(); });

  // Note: signOut("antigravity") removes readable creds files from disk, so it is
  // intentionally not exercised here to avoid real filesystem side effects.
  it("reports success (no fs side effects) for these providers and never throws", () => {
    for (const p of ["ollama", "deepseek", "claude", "openai"] as const) {
      const result = resolver.signOut(p);
      expect(result.ok).toBe(true);
      expect(typeof result.note).toBe("string");
      expect(result.note.length).toBeGreaterThan(0);
    }
  });

  it("notes that CLI providers keep their own session", () => {
    expect(resolver.signOut("openai").note).toMatch(/codex/i);
    expect(resolver.signOut("claude").note).toMatch(/claude/i);
    expect(resolver.signOut("deepseek").note).toMatch(/key/i);
  });
});

describe("cliAuth source contract", () => {
  it("does not keep the unused normalizeExpiry helper (G17-3)", () => {
    expect(cliAuthSource()).not.toContain("normalizeExpiry(");
  });
});
