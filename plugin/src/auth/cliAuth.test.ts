import { describe, expect, it } from "vitest";
import { buildGuiCliSearchPaths } from "./cliAuth";

describe("buildGuiCliSearchPaths", () => {
  it("includes common macOS GUI and Node manager binary locations", () => {
    const paths = buildGuiCliSearchPaths("/Users/example");
    expect(paths).toContain("/opt/homebrew/bin");
    expect(paths).toContain("/Users/example/.volta/bin");
    expect(paths).toContain("/Users/example/.bun/bin");
    expect(paths).toContain("/Users/example/.npm-global/bin");
  });
});
