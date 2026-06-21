/**
 * OS-level sandbox wrapper for agentic CLI subprocesses (v0.23.0).
 *
 * Agentic CLIs — `agy` especially — ignore their own `--sandbox` flag (P0: under
 * `agy --sandbox` the agent still ran `echo > /tmp/file` and the file was created).
 * So we contain the subprocess with an OS sandbox generated from the allowed roots:
 *
 *   - macOS: `sandbox-exec -p <profile>` (Seatbelt). The profile is passed INLINE on
 *     the command line (no temp file → no multi-vault / concurrent-call collision).
 *     It DENIES `file-write*` everywhere except the vault, the Zotero roots, the CLI
 *     agents' own state/config dirs, and runtime dirs — stopping file creation in the
 *     user's documents/vault-external space (the reported exploit) without breaking
 *     the CLI. Validated to block nested child processes (agy spawns nested shells).
 *   - Linux: `bwrap` — `--ro-bind / /` makes the whole filesystem read-only, then
 *     `--bind`/`--bind-try` re-grants read-write to the allowed roots AND the CLI's
 *     own config/cache dirs (else the CLI crashes with "Read-only file system").
 *     If `bwrap` is absent the caller must refuse the agentic CLI.
 *
 * Reads are intentionally still allowed (denying reads breaks the CLI's ability to
 * read its own binaries/libs); the security-critical harm is writes/creation. Pure +
 * unit-tested; the actual subprocess spawning is done by the caller (`buildCliCommand`).
 */

export type SandboxPlatform = "darwin" | "linux" | string;

export interface SandboxPlan {
  /** Argv to PREPEND before the real CLI command. Empty = no OS wrapper applied. */
  prefix: string[];
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
 * Writable dirs the CLI agents legitimately use (their own config/state/cache, plus
 * generic runtime/temp). Without these the CLI crashes trying to write its session
 * token / logs / state. These are CLI-internal locations, not the user's documents,
 * so allowing them does not enable the reported exploit (creating files in/around
 * the vault and searching the user's data).
 */
function cliRuntimeWriteDirs(home: string, tmpdir: string): string[] {
  const h = (d: string) => (home ? `${home}/${d}` : "");
  return [
    "/private/var/folders",
    "/private/tmp",
    tmpdir,
    // Agent CLI state/config dirs (agy→.gemini/.antigravity, claude→.claude,
    // codex→.codex) + XDG defaults. NOT ~/.incurator — plugin caches belong in the
    // project .cache/, and the plugin (not the sandboxed CLI) writes temp images,
    // which the CLI only READS (reads are allowed).
    h(".gemini"),
    h(".antigravity"),
    h(".claude"),
    h(".codex"),
    h(".config"),
    h(".cache"),
    h("Library/Caches"),
  ].filter(nonEmpty);
}

/**
 * macOS Seatbelt profile: allow everything, then DENY all writes except the allowed
 * roots + the CLI's own write dirs. Returned as a string to pass inline via `-p`.
 */
export function buildMacosSeatbeltProfile(
  allowedRoots: string[],
  home: string = "",
  tmpdir: string = "",
): string {
  const roots = dedupe(allowedRoots.filter(nonEmpty));
  const writeRules = dedupe([...roots, ...cliRuntimeWriteDirs(home, tmpdir)]).map(
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

/**
 * Linux bwrap binds: read-only whole FS, read-write only the allowed roots AND the
 * CLI's own config/cache dirs (else "Read-only file system" crashes). `--bind-try`
 * skips a source that doesn't exist instead of failing.
 */
export function buildBwrapArgs(allowedRoots: string[], home: string = "", tmpdir: string = ""): string[] {
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
    args.push("--bind", r, r); // allowed roots MUST exist → hard bind (read-write)
  }
  for (const d of cliRuntimeWriteDirs(home, tmpdir)) {
    if (d.startsWith("/private/")) continue; // macOS-only paths
    args.push("--bind-try", d, d); // CLI dirs may or may not exist → bind-try
  }
  args.push("--"); // end of bwrap args; the CLI command follows
  return args;
}

/**
 * Build the OS-sandbox plan for the current platform. `sandboxExecPath` / `bwrapPath`
 * are resolved executable paths (or "") so availability detection stays out of this
 * pure function. The macOS profile is passed inline via `-p` (no temp file).
 */
export function buildSandboxPlan(args: {
  platform: SandboxPlatform;
  allowedRoots: string[];
  home?: string;
  tmpdir?: string;
  sandboxExecPath?: string; // resolved `sandbox-exec` path (macOS), or ""
  bwrapPath?: string;       // resolved `bwrap` path (linux), or ""
}): SandboxPlan {
  const roots = dedupe((args.allowedRoots || []).filter(nonEmpty));
  if (roots.length === 0) {
    // No roots to scope to → refuse rather than sandbox to nothing (R4: never widen).
    return { prefix: [], unavailable: true, reason: "No allowed roots resolved; refusing to run an unsandboxed agentic CLI." };
  }

  if (args.platform === "darwin") {
    if (!args.sandboxExecPath) {
      return { prefix: [], unavailable: true, reason: "sandbox-exec unavailable on macOS." };
    }
    const profile = buildMacosSeatbeltProfile(roots, args.home, args.tmpdir);
    return { prefix: [args.sandboxExecPath, "-p", profile], unavailable: false };
  }

  if (args.platform === "linux") {
    if (!args.bwrapPath) {
      return {
        prefix: [],
        unavailable: true,
        reason: "bubblewrap (bwrap) is required to sandbox the agentic CLI on Linux. Install it: `sudo apt install bubblewrap` (or `sudo dnf install bubblewrap`).",
      };
    }
    return { prefix: [args.bwrapPath, ...buildBwrapArgs(roots, args.home, args.tmpdir)], unavailable: false };
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
