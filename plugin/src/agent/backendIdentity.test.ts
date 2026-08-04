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
  });

  it("never reads installed package metadata at all", () => {
    const src = clientSource();
    // `record.version` is the metadata-derived field. The check must not touch
    // it — not as a gate, and not as a fallback: the backend already seeds
    // `build.backend_version` unconditionally, so a fallback here would only
    // reintroduce the dependency this release removed.
    expect(src).not.toContain("record.version");
  });

  it("reports an absent build identity instead of guessing one", () => {
    const src = clientSource();
    expect(src).toContain("did not report a build identity");
  });

  it("does not claim a mismatch when our own bundle states no expectation", () => {
    const src = clientSource();
    expect(src).toContain("if (!expectedBackendVersion) {");
  });

  it("names the backend launcher that actually answered", () => {
    const src = clientSource();
    expect(src).toContain("backendCommandLabel");
    expect(src).toContain("from ${this.backendCommandLabel}");
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
