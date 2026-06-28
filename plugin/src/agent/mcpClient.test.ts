import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { join } from "path";
import { describe, expect, it } from "vitest";

function mcpSource(): string {
  const dir = fileURLToPath(new URL(".", import.meta.url));
  return readFileSync(join(dir, "mcpClient.ts"), "utf8");
}

describe("MCP process exit visibility (XC-4)", () => {
  it("surfaces a non-zero exit as a visible warning, keeps a clean exit gated", () => {
    const src = mcpSource();
    // Routing the exit log through the gated logger must NOT hide crashes:
    // a non-zero exit code logs at warn (always visible); a clean exit at debug.
    expect(src).toContain("if (code) {");
    expect(src).toContain(
      "logger.warn(`[MCP:${this.config.name}] exited with code ${code}`)"
    );
    expect(src).toContain(
      "logger.debug(`[MCP:${this.config.name}] exited with code ${code}`)"
    );
  });
});
