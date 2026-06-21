import { describe, expect, it } from "vitest";
import {
  buildBwrapArgs,
  buildMacosSeatbeltProfile,
  buildSandboxPlan,
} from "./sandboxWrapper";

describe("macOS seatbelt profile (v0.23.0)", () => {
  it("denies all writes then re-allows roots + the CLIs' OWN dirs + the temp dir", () => {
    const p = buildMacosSeatbeltProfile(["/Vault", "/Zotero"], "/home/u", "/tmpx");
    expect(p).toContain("(deny file-write*)");
    expect(p).toContain('(allow file-write* (subpath "/Vault"))');
    expect(p).toContain('(allow file-write* (subpath "/Zotero"))');
    // CLI agents' own state dirs MUST be writable or they crash at runtime.
    expect(p).toContain('(allow file-write* (subpath "/home/u/.gemini"))');
    expect(p).toContain('(allow file-write* (subpath "/home/u/.claude"))');
    expect(p).toContain('(allow file-write* (subpath "/home/u/.codex"))');
    // The user's specific temp dir, passed in (for libs that hit it directly).
    expect(p).toContain('(allow file-write* (subpath "/tmpx"))');
    // deny appears BEFORE the allow re-grants (order matters in seatbelt).
    expect(p.indexOf("(deny file-write*)")).toBeLessThan(p.indexOf('(subpath "/Vault")'));
  });

  it("does NOT grant broad ~/.config, ~/.cache, ~/Library/Caches, or /private roots", () => {
    const p = buildMacosSeatbeltProfile(["/Vault"], "/home/u", "/tmpx");
    expect(p).not.toContain('(subpath "/home/u/.config")'); // whole ~/.config
    expect(p).not.toContain('(subpath "/home/u/.cache")');  // whole ~/.cache
    expect(p).not.toContain('(subpath "/home/u/Library/Caches")');
    expect(p).not.toContain('(subpath "/private/var/folders")'); // every app/user temp
    expect(p).not.toContain('(subpath "/private/tmp")');
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
  it("read-only FS, rw-binds the allowed roots + the CLIs' own dirs + temp dir", () => {
    const a = buildBwrapArgs(["/Vault", "/Zotero"], "/home/u", "/tmpx");
    expect(a.slice(0, 3)).toEqual(["--ro-bind", "/", "/"]);
    expect(a).toContain("--die-with-parent");
    const joined = a.join(" ");
    expect(joined).toContain("--bind-try /Vault /Vault");
    expect(joined).toContain("--bind-try /Zotero /Zotero");
    expect(joined).toContain("--bind-try /tmpx /tmpx");
    expect(joined).toContain("--bind-try /home/u/.gemini /home/u/.gemini");
    // Scoped to the CLIs' own dirs — never the whole ~/.config / ~/.cache.
    expect(joined).not.toContain("--bind-try /home/u/.config /home/u/.config");
    expect(joined).not.toContain("/private/var/folders");
    expect(a[a.length - 1]).toBe("--"); // terminator before the CLI command
  });

  it("never re-binds /tmp (would destroy the tmpfs isolation)", () => {
    const a = buildBwrapArgs(["/Vault"], "/home/u", "/tmp");
    expect(a).toContain("--tmpfs");
    // /tmp is the host tmpdir here, but must NOT be --bind-try'd over the tmpfs.
    expect(a.join(" ")).not.toContain("--bind-try /tmp /tmp");
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
