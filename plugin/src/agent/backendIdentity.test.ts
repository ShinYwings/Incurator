import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { join } from "path";

/**
 * v0.42.0 backend-identity contract.
 *
 * Field origin: a stale Anaconda editable install answered `wiki` while
 * executing current repository code. Editable installs freeze
 * `importlib.metadata` at the version they were first installed at, so the
 * top-level `version` said 0.4.3 while `build.backend_version` correctly said
 * 0.41.0. Gating on the metadata version produced an "update needed" banner
 * that re-running setup could never clear.
 */

const clientSource = () =>
  readFileSync(join(__dirname, "incuratorClient.ts"), "utf8");
const mainSource = () =>
  readFileSync(join(__dirname, "..", "..", "main.ts"), "utf8");

describe("backend version identity", () => {
  it("gates on build.backend_version, not installed package metadata", () => {
    const src = clientSource();
    expect(src).toContain('readString(record.build, "backend_version")');
    // The pre-v0.42.0 shape assigned the metadata version unconditionally,
    // before any build-manifest value was consulted. That exact shape must be
    // gone; the metadata version may now only inform the message.
    expect(src).not.toMatch(
      /const version = record\.version;\s*\n\s*if \(typeof version === "string"\) \{\s*\n\s*this\.backendVersion = version;/
    );
  });

  it("falls back to the metadata version only when no build manifest is present", () => {
    const src = clientSource();
    expect(src).toContain("if (buildVersion) {");
    expect(src).toContain('} else if (typeof version === "string") {');
  });

  it("names the backend launcher that actually answered", () => {
    const src = clientSource();
    expect(src).toContain("backendCommandLabel");
    expect(src).toContain("from ${this.backendCommandLabel}");
  });

  it("explains a metadata/build divergence instead of leaving it mysterious", () => {
    const src = clientSource();
    expect(src).toContain("stale metadata, not stale code");
  });

  it("populates the launcher label from the resolved command", () => {
    const src = mainSource();
    expect(src).toContain("this.incuratorClient.backendCommandLabel = command");
  });
});

describe("backend command resolution never falls back to bare PATH", () => {
  /**
   * Regression guard for the failure this release documents: resolving the bare
   * name `wiki` uses the Obsidian process PATH (not the user's shell), where an
   * unrelated install can win. `resolveBackendCommand` must keep returning null
   * rather than handing a bare name to `spawn`.
   */
  it("returns null instead of the bare name", () => {
    const src = mainSource();
    expect(src).toContain('return command && command !== "wiki" ? command : null;');
  });

  it("refuses to spawn when the launcher is unresolved", () => {
    const src = mainSource();
    expect(src).toContain("Incurator backend command is unresolved");
  });

  it("auto-discovers the repo runtime venv launcher", () => {
    const src = mainSource();
    expect(src).toContain("resolveWikiBinary(repoPath)");
  });
});
