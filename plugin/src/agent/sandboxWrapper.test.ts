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

// G13-4 regression: provider-scoped write dirs
describe("provider-scoped sandbox dirs (G13-4)", () => {
  it("antigravity: only .gemini + .antigravity are writable, not .claude or .codex", () => {
    const p = buildMacosSeatbeltProfile(["/Vault"], "/home/u", "/tmpx", "antigravity");
    expect(p).toContain('(allow file-write* (subpath "/home/u/.gemini"))');
    expect(p).toContain('(allow file-write* (subpath "/home/u/.antigravity"))');
    expect(p).not.toContain('(subpath "/home/u/.claude")');
    expect(p).not.toContain('(subpath "/home/u/.codex")');
  });

  it("claude: only .claude is writable, not .gemini / .codex / .antigravity", () => {
    const p = buildMacosSeatbeltProfile(["/Vault"], "/home/u", "/tmpx", "claude");
    expect(p).toContain('(allow file-write* (subpath "/home/u/.claude"))');
    expect(p).not.toContain('(subpath "/home/u/.gemini")');
    expect(p).not.toContain('(subpath "/home/u/.codex")');
    expect(p).not.toContain('(subpath "/home/u/.antigravity")');
  });

  it("openai: only .codex is writable, not .gemini / .claude / .antigravity", () => {
    const p = buildMacosSeatbeltProfile(["/Vault"], "/home/u", "/tmpx", "openai");
    expect(p).toContain('(allow file-write* (subpath "/home/u/.codex"))');
    expect(p).not.toContain('(subpath "/home/u/.gemini")');
    expect(p).not.toContain('(subpath "/home/u/.claude")');
    expect(p).not.toContain('(subpath "/home/u/.antigravity")');
  });

  it("no provider → fallback includes all known dirs (backward compat)", () => {
    const p = buildMacosSeatbeltProfile(["/Vault"], "/home/u", "/tmpx");
    expect(p).toContain('(subpath "/home/u/.gemini")');
    expect(p).toContain('(subpath "/home/u/.claude")');
    expect(p).toContain('(subpath "/home/u/.codex")');
    expect(p).toContain('(subpath "/home/u/.antigravity")');
  });

  it("bwrap: claude provider scopes to only .claude", () => {
    const a = buildBwrapArgs(["/Vault"], "/home/u", "/tmpx", "claude");
    const joined = a.join(" ");
    expect(joined).toContain("--bind-try /home/u/.claude /home/u/.claude");
    expect(joined).not.toContain("--bind-try /home/u/.gemini");
    expect(joined).not.toContain("--bind-try /home/u/.codex");
  });

  it("ollama: no home dirs (principle of least privilege — ollama has no CLI home dir)", () => {
    const p = buildMacosSeatbeltProfile(["/Vault"], "/home/u", "/tmpx", "ollama");
    expect(p).not.toContain('(subpath "/home/u/.gemini")');
    expect(p).not.toContain('(subpath "/home/u/.claude")');
    expect(p).not.toContain('(subpath "/home/u/.codex")');
    expect(p).not.toContain('(subpath "/home/u/.antigravity")');
  });

  it("deepseek: no home dirs (principle of least privilege — deepseek has no CLI home dir)", () => {
    const p = buildMacosSeatbeltProfile(["/Vault"], "/home/u", "/tmpx", "deepseek");
    expect(p).not.toContain('(subpath "/home/u/.gemini")');
    expect(p).not.toContain('(subpath "/home/u/.claude")');
    expect(p).not.toContain('(subpath "/home/u/.codex")');
    expect(p).not.toContain('(subpath "/home/u/.antigravity")');
  });
});
