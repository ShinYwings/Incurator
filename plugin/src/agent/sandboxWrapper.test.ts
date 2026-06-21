import { describe, expect, it } from "vitest";
import {
  buildBwrapArgs,
  buildMacosSeatbeltProfile,
  buildSandboxPlan,
} from "./sandboxWrapper";

describe("macOS seatbelt profile (v0.23.0)", () => {
  it("denies all writes then re-allows roots + CLI state/runtime dirs", () => {
    const p = buildMacosSeatbeltProfile(["/Vault", "/Zotero"], "/home/u", "/tmpx");
    expect(p).toContain("(deny file-write*)");
    expect(p).toContain('(allow file-write* (subpath "/Vault"))');
    expect(p).toContain('(allow file-write* (subpath "/Zotero"))');
    // CLI agents' own state dirs MUST be writable or they crash at runtime.
    expect(p).toContain('(allow file-write* (subpath "/home/u/.gemini"))');
    expect(p).toContain('(allow file-write* (subpath "/home/u/.claude"))');
    expect(p).toContain('(allow file-write* (subpath "/home/u/.codex"))');
    expect(p).toContain('(allow file-write* (subpath "/home/u/.config"))');
    expect(p).toContain('(allow file-write* (subpath "/home/u/.cache"))');
    expect(p).toContain('(allow file-write* (subpath "/private/var/folders"))');
    expect(p).toContain('(allow file-write* (subpath "/tmpx"))');
    // deny appears BEFORE the allow re-grants (order matters in seatbelt).
    expect(p.indexOf("(deny file-write*)")).toBeLessThan(p.indexOf('(subpath "/Vault")'));
  });

  it("does NOT allow ~/.incurator (plugin caches belong in the project .cache/)", () => {
    const p = buildMacosSeatbeltProfile(["/Vault"], "/home/u", "/tmpx");
    expect(p).not.toContain('"/home/u/.incurator"');
  });

  it("drops empty/duplicate roots", () => {
    const p = buildMacosSeatbeltProfile(["/Vault", "", "/Vault", "  "]);
    const occurrences = p.split('(allow file-write* (subpath "/Vault"))').length - 1;
    expect(occurrences).toBe(1);
    expect(p).not.toContain('(subpath "")');
  });
});

describe("Linux bwrap args (v0.23.0)", () => {
  it("read-only FS, rw-binds the allowed roots AND the CLI config/cache dirs", () => {
    const a = buildBwrapArgs(["/Vault", "/Zotero"], "/home/u");
    expect(a.slice(0, 3)).toEqual(["--ro-bind", "/", "/"]);
    expect(a).toContain("--die-with-parent");
    const joined = a.join(" ");
    expect(joined).toContain("--bind /Vault /Vault");
    expect(joined).toContain("--bind /Zotero /Zotero");
    // CLI dirs use --bind-try (may not exist) so the CLI can write its own state.
    expect(joined).toContain("--bind-try /home/u/.gemini /home/u/.gemini");
    expect(joined).toContain("--bind-try /home/u/.config /home/u/.config");
    expect(joined).toContain("--bind-try /home/u/.cache /home/u/.cache");
    // macOS-only runtime paths are not bound on Linux.
    expect(joined).not.toContain("/private/var/folders");
    expect(a[a.length - 1]).toBe("--"); // terminator before the CLI command
  });
});

describe("buildSandboxPlan (v0.23.0)", () => {
  it("macOS → sandbox-exec -p with the profile inline (no temp file)", () => {
    const plan = buildSandboxPlan({
      platform: "darwin",
      allowedRoots: ["/Vault"],
      home: "/home/u",
      sandboxExecPath: "/usr/bin/sandbox-exec",
    });
    expect(plan.unavailable).toBe(false);
    expect(plan.prefix[0]).toBe("/usr/bin/sandbox-exec");
    expect(plan.prefix[1]).toBe("-p");
    expect(plan.prefix[2]).toContain("(deny file-write*)"); // profile passed inline
    expect(plan.prefix).toHaveLength(3); // no -f, no file path
  });

  it("linux with bwrap → bwrap prefix", () => {
    const plan = buildSandboxPlan({
      platform: "linux",
      allowedRoots: ["/Vault"],
      home: "/home/u",
      bwrapPath: "/usr/bin/bwrap",
    });
    expect(plan.unavailable).toBe(false);
    expect(plan.prefix[0]).toBe("/usr/bin/bwrap");
    expect(plan.prefix).toContain("--ro-bind");
  });

  it("linux WITHOUT bwrap → unavailable + install guidance (caller must refuse)", () => {
    const plan = buildSandboxPlan({ platform: "linux", allowedRoots: ["/Vault"], bwrapPath: "" });
    expect(plan.unavailable).toBe(true);
    expect(plan.reason).toContain("bubblewrap");
    expect(plan.prefix).toEqual([]);
  });

  it("empty allowed roots → unavailable (never run unsandboxed / never widen)", () => {
    const plan = buildSandboxPlan({
      platform: "darwin",
      allowedRoots: ["", "  "],
      sandboxExecPath: "/usr/bin/sandbox-exec",
    });
    expect(plan.unavailable).toBe(true);
    expect(plan.reason).toContain("No allowed roots");
  });

  it("windows/other → unavailable (out of scope)", () => {
    const plan = buildSandboxPlan({ platform: "win32", allowedRoots: ["/Vault"] });
    expect(plan.unavailable).toBe(true);
  });
});
