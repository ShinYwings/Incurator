import { describe, expect, it } from "vitest";
import {
  buildBwrapArgs,
  buildMacosSeatbeltProfile,
  buildSandboxPlan,
} from "./sandboxWrapper";

describe("macOS seatbelt profile (v0.23.0)", () => {
  it("denies all writes then re-allows only the allowed roots + runtime dirs", () => {
    const p = buildMacosSeatbeltProfile(["/Vault", "/Zotero"], "/home/u", "/tmpx");
    expect(p).toContain("(deny file-write*)");
    expect(p).toContain('(allow file-write* (subpath "/Vault"))');
    expect(p).toContain('(allow file-write* (subpath "/Zotero"))');
    // Runtime write dirs the CLI needs so it doesn't break.
    expect(p).toContain('(allow file-write* (subpath "/private/var/folders"))');
    expect(p).toContain('(allow file-write* (subpath "/tmpx"))');
    expect(p).toContain('(allow file-write* (subpath "/home/u/.cache"))');
    // deny appears BEFORE the allow re-grants (order matters in seatbelt).
    expect(p.indexOf("(deny file-write*)")).toBeLessThan(p.indexOf('(subpath "/Vault")'));
  });

  it("drops empty/duplicate roots", () => {
    const p = buildMacosSeatbeltProfile(["/Vault", "", "/Vault", "  "]);
    const occurrences = p.split('(allow file-write* (subpath "/Vault"))').length - 1;
    expect(occurrences).toBe(1);
    expect(p).not.toContain('(subpath "")');
  });
});

describe("Linux bwrap args (v0.23.0)", () => {
  it("makes the FS read-only and re-binds only the allowed roots read-write", () => {
    const a = buildBwrapArgs(["/Vault", "/Zotero"]);
    expect(a.slice(0, 3)).toEqual(["--ro-bind", "/", "/"]);
    expect(a).toContain("--die-with-parent");
    // each root re-bound read-write
    const joined = a.join(" ");
    expect(joined).toContain("--bind /Vault /Vault");
    expect(joined).toContain("--bind /Zotero /Zotero");
    expect(a[a.length - 1]).toBe("--"); // terminator before the CLI command
  });
});

describe("buildSandboxPlan (v0.23.0)", () => {
  it("macOS → sandbox-exec prefix + profile", () => {
    const plan = buildSandboxPlan({
      platform: "darwin",
      allowedRoots: ["/Vault"],
      sandboxExecPath: "/usr/bin/sandbox-exec",
      profilePath: "/tmp/p.sb",
    });
    expect(plan.unavailable).toBe(false);
    expect(plan.prefix).toEqual(["/usr/bin/sandbox-exec", "-f", "/tmp/p.sb"]);
    expect(plan.profile).toContain("(deny file-write*)");
  });

  it("linux with bwrap → bwrap prefix", () => {
    const plan = buildSandboxPlan({
      platform: "linux",
      allowedRoots: ["/Vault"],
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
      profilePath: "/tmp/p.sb",
    });
    expect(plan.unavailable).toBe(true);
    expect(plan.reason).toContain("No allowed roots");
  });

  it("windows/other → unavailable (out of scope)", () => {
    const plan = buildSandboxPlan({ platform: "win32", allowedRoots: ["/Vault"] });
    expect(plan.unavailable).toBe(true);
  });
});
