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
});
