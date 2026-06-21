/**
 * OS-level sandbox wrapper for agentic CLI subprocesses (v0.23.0).
 *
 * Agentic CLIs — `agy` especially — ignore their own `--sandbox` flag (P0: under
 * `agy --sandbox` the agent still ran `echo > /tmp/file` and the file was created).
 * So we contain the subprocess with an OS sandbox generated from the allowed roots:
 *
 *   - macOS: `sandbox-exec -f <profile>` (Seatbelt). Validated to block writes
 *     outside the allowed roots, INCLUDING nested child processes (agy spawns
 *     nested shells). The profile DENIES `file-write*` everywhere except the vault,
 *     the Zotero roots, and the CLI's own runtime dirs (caches/tmp) — this stops
 *     file creation/modification (the reported exploit) without breaking the CLI.
 *   - Linux: `bwrap` (bubblewrap) — `--ro-bind / /` makes the whole filesystem
 *     read-only, then `--bind <root> <root>` re-grants read-write to each allowed
 *     root. If `bwrap` is absent the caller must refuse the agentic CLI and tell
 *     the user to install it.
 *
 * Reads are intentionally still allowed (denying user-data reads would break the
 * CLI's ability to read its own binaries/libs); the security-critical harm is
 * writes/creation, which this contains. This module is pure + unit-tested; the
 * actual subprocess spawning is done by the caller (`buildCliCommand`).
 */

export type SandboxPlatform = "darwin" | "linux" | string;

export interface SandboxPlan {
  /** Argv to PREPEND before the real CLI command. Empty = no OS wrapper applied. */
  prefix: string[];
  /** macOS only: a Seatbelt profile to write to a temp file before spawning. */
  profile?: string;
  /** True when this platform/toolchain cannot sandbox and the caller must refuse. */
  unavailable: boolean;
  /** User-facing reason/guidance when `unavailable` (e.g. install bubblewrap). */
  reason?: string;
}

/** Quote a path for a Seatbelt `(subpath ...)` literal. */
function sbQuote(p: string): string {
  return JSON.stringify(p); // valid for Seatbelt string literals
}

/**
 * macOS Seatbelt profile: allow everything, then DENY all writes except the allowed
 * roots + the CLI's necessary runtime write dirs. Validated containment pattern.
 */
export function buildMacosSeatbeltProfile(
  allowedRoots: string[],
  home: string = "",
  tmpdir: string = "",
): string {
  const roots = dedupe(allowedRoots.filter(nonEmpty));
  // Runtime dirs the CLI legitimately writes (caches, logs, temp). Without these
  // the CLI can fail to start. macOS `$TMPDIR` resolves under /private/var/folders.
  const runtime = [
    "/private/var/folders",
    "/private/tmp",
    tmpdir,
    home ? `${home}/.cache` : "",
    home ? `${home}/.config` : "",
    home ? `${home}/Library/Caches` : "",
  ].filter(nonEmpty);

  const writeRules = dedupe([...roots, ...runtime]).map(
    (r) => `  (allow file-write* (subpath ${sbQuote(r)}))`,
  );

  return [
    "(version 1)",
    "(allow default)",
    "(deny file-write*)",
    ...writeRules,
    '  (allow file-write-data (literal "/dev/null"))',
    '  (allow file-write-data (literal "/dev/dtracehelper"))',
    "",
  ].join("\n");
}

/** Linux bwrap binds: read-only whole FS, read-write only the allowed roots. */
export function buildBwrapArgs(allowedRoots: string[]): string[] {
  const roots = dedupe(allowedRoots.filter(nonEmpty));
  const args = [
    "--ro-bind", "/", "/",
    "--dev", "/dev",
    "--proc", "/proc",
    "--tmpfs", "/tmp",
    "--unshare-all",
    "--share-net",            // CLIs need network to reach their provider
    "--die-with-parent",
  ];
  for (const r of roots) {
    args.push("--bind", r, r); // re-grant read-write to each allowed root
  }
  args.push("--"); // end of bwrap args; the CLI command follows
  return args;
}

/**
 * Build the OS-sandbox plan for the current platform. `bwrapPath` is the resolved
 * path to `bwrap` (or "") so availability detection stays out of this pure function.
 */
export function buildSandboxPlan(args: {
  platform: SandboxPlatform;
  allowedRoots: string[];
  home?: string;
  tmpdir?: string;
  sandboxExecPath?: string; // resolved `sandbox-exec` path (macOS), or ""
  bwrapPath?: string;       // resolved `bwrap` path (linux), or ""
  profilePath?: string;     // temp file the caller will write the macOS profile to
}): SandboxPlan {
  const roots = dedupe((args.allowedRoots || []).filter(nonEmpty));
  if (roots.length === 0) {
    // No roots to scope to → refuse rather than sandbox to nothing (R4: never widen).
    return { prefix: [], unavailable: true, reason: "No allowed roots resolved; refusing to run an unsandboxed agentic CLI." };
  }

  if (args.platform === "darwin") {
    if (!args.sandboxExecPath || !args.profilePath) {
      return { prefix: [], unavailable: true, reason: "sandbox-exec unavailable on macOS." };
    }
    return {
      prefix: [args.sandboxExecPath, "-f", args.profilePath],
      profile: buildMacosSeatbeltProfile(roots, args.home, args.tmpdir),
      unavailable: false,
    };
  }

  if (args.platform === "linux") {
    if (!args.bwrapPath) {
      return {
        prefix: [],
        unavailable: true,
        reason: "bubblewrap (bwrap) is required to sandbox the agentic CLI on Linux. Install it: `sudo apt install bubblewrap` (or `sudo dnf install bubblewrap`).",
      };
    }
    return { prefix: [args.bwrapPath, ...buildBwrapArgs(roots)], unavailable: false };
  }

  // Windows / other: out of scope for this milestone.
  return { prefix: [], unavailable: true, reason: `OS sandbox not supported on '${args.platform}'.` };
}

function nonEmpty(s: string | undefined | null): s is string {
  return typeof s === "string" && s.trim().length > 0;
}

function dedupe(xs: string[]): string[] {
  return Array.from(new Set(xs));
}
