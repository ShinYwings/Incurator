import { describe, expect, it, beforeEach } from "vitest";
import { buildGuiCliSearchPaths, CLIAuthResolver } from "./cliAuth";

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

  it("does not claim a specific Antigravity account it cannot read", () => {
    // agy 1.0.5 hides creds in the keychain; we must not fabricate an account.
    const info = resolver.getAccountInfo("antigravity");
    expect(info.email).toBeUndefined();
    expect(info.name).toBe("agy CLI session");
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
