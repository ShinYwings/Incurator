import { execFileSync, spawn } from "child_process";
import { homedir } from "os";
import { buildGuiCliSearchPaths } from "./cliAuth";

export interface GitHubAuthStatus {
  installed: boolean;
  authenticated: boolean;
  account?: string;
  message: string;
}

type ExecFileSync = typeof execFileSync;

function augmentedEnv(): NodeJS.ProcessEnv {
  const paths = buildGuiCliSearchPaths(homedir());
  const delimiter = process.platform === "win32" ? ";" : ":";
  const currentPath = process.env.PATH || "";
  return {
    ...process.env,
    PATH: [...paths, currentPath].join(delimiter),
  };
}

export function parseGitHubAuthStatus(
  stdout: string,
  stderr = "",
  exitCode = 0
): GitHubAuthStatus {
  const text = `${stdout}\n${stderr}`.trim();
  const account =
    text.match(/Logged in to .* as ([^\s]+)/)?.[1] ||
    text.match(/account ([^\s]+)/i)?.[1] ||
    "";
  if (exitCode === 0) {
    return {
      installed: true,
      authenticated: true,
      account: account || undefined,
      message: account ? `Logged in as ${account}` : "Logged in to GitHub",
    };
  }
  return {
    installed: true,
    authenticated: false,
    message: text || "GitHub CLI is not authenticated. Run gh auth login.",
  };
}

export function getGitHubAuthStatus(execFile: ExecFileSync = execFileSync): GitHubAuthStatus {
  try {
    const stdout = execFile("gh", ["auth", "status"], {
      encoding: "utf-8",
      env: augmentedEnv(),
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 10000,
    }) as string;
    return parseGitHubAuthStatus(stdout, "", 0);
  } catch (err: any) {
    if (err?.code === "ENOENT") {
      return {
        installed: false,
        authenticated: false,
        message: "GitHub CLI (gh) is not installed or not found on PATH.",
      };
    }
    return parseGitHubAuthStatus(
      String(err?.stdout || ""),
      String(err?.stderr || err?.message || ""),
      typeof err?.status === "number" ? err.status : 1
    );
  }
}

export interface GitHubAuthButtonState {
  /** Single toggle label: "Sign out" when authenticated, otherwise "Sign in". */
  label: "Sign in" | "Sign out";
  /** Which gh action the toggle should launch. */
  intent: "login" | "logout";
  /** Render as a call-to-action (sign in) vs. a warning (sign out). */
  cta: boolean;
  warning: boolean;
}

/**
 * Resolve the single Sign in / Sign out toggle shown in the GitHub Integration
 * settings row. When `gh` is authenticated the toggle signs out; otherwise it
 * signs in. The two states alternate so only one of them is ever visible.
 */
export function githubAuthButtonState(status: GitHubAuthStatus): GitHubAuthButtonState {
  if (status.installed && status.authenticated) {
    return { label: "Sign out", intent: "logout", cta: false, warning: true };
  }
  return { label: "Sign in", intent: "login", cta: true, warning: false };
}

export function startGitHubLogin(): void {
  launchDetached(["gh", "auth", "login"], "GitHub login");
}

export function startGitHubLogout(): void {
  launchDetached(["gh", "auth", "logout"], "GitHub logout");
}

function launchDetached(command: string[], title: string): void {
  if (process.platform === "darwin") {
    const script = command.map(shellQuote).join(" ");
    spawn(
      "osascript",
      [
        "-e",
        `tell application "Terminal" to activate`,
        "-e",
        `tell application "Terminal" to do script ${appleScriptQuote(script)}`,
      ],
      { detached: true, stdio: "ignore", env: augmentedEnv() }
    ).unref();
    return;
  }

  if (process.platform === "win32") {
    spawn("cmd.exe", ["/c", "start", title, "cmd.exe", "/k", command.join(" ")], {
      detached: true,
      stdio: "ignore",
      env: augmentedEnv(),
    }).unref();
    return;
  }

  const script = command.map(shellQuote).join(" ");
  const terminal = process.env.TERMINAL || "x-terminal-emulator";
  spawn(terminal, ["-e", "bash", "-lc", script], {
    detached: true,
    stdio: "ignore",
    env: augmentedEnv(),
  }).unref();
}

function shellQuote(value: string): string {
  return `'${value.replace(/'/g, `'\\''`)}'`;
}

function appleScriptQuote(value: string): string {
  return JSON.stringify(value);
}
