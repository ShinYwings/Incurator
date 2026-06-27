import { execSync, spawn } from "child_process";
import { existsSync, readdirSync, readFileSync, statSync, rmSync } from "fs";
import { homedir } from "os";
import { join } from "path";
import type { LLMProvider } from "../types";

export interface CLICredential {
  type: "bearer";
  token: string;
  expiresAt?: number;
}

interface TokenCache {
  credential: CLICredential;
  expiresAt: number;
}

const AUTH_HELP: Record<LLMProvider, string> = {
  antigravity:
    'Install Antigravity CLI, run "agy", and complete the Google browser login flow.',
  claude:
    'Install Claude Code, run "claude", and complete the browser login flow.',
  openai:
    'Run "codex" and complete the ChatGPT browser login flow.',
  ollama: 'Start Ollama with "ollama serve" and pull a model with "ollama pull <model>".',
  deepseek:
    'Set DEEPSEEK_API_KEY in the Obsidian environment, shell profile, or backend config.',
};

const LOGIN_COMMANDS: Record<LLMProvider, string[]> = {
  antigravity: ["agy"],
  claude: ["claude", "auth", "login"],
  openai: ["codex", "login"],
  ollama: ["ollama"],
  deepseek: [],
};

export function buildGuiCliSearchPaths(home: string): string[] {
  const paths = [
    "/usr/local/bin",
    "/opt/homebrew/bin",
    "/bin",
    "/usr/bin",
    "/usr/sbin",
    "/sbin",
    home ? `${home}/.local/bin` : "",
    home ? `${home}/bin` : "",
    home ? `${home}/.gemini/bin` : "",
    home ? `${home}/.cargo/bin` : "",
    home ? `${home}/.npm-global/bin` : "",
    home ? `${home}/.bun/bin` : "",
    home ? `${home}/.volta/bin` : "",
  ].filter(Boolean);

  const nvmVersions = home ? `${home}/.nvm/versions/node` : "";
  try {
    for (const version of readdirSync(nvmVersions)) {
      const bin = join(nvmVersions, version, "bin");
      if (statSync(bin).isDirectory()) paths.push(bin);
    }
  } catch {
    // nvm is optional.
  }

  return Array.from(new Set(paths));
}


export class CLIAuthResolver {
  private cache: Partial<Record<LLMProvider, TokenCache>> = {};

  /**
   * Resolve a browser-CLI credential for the given provider.
   * Throws with a user-friendly message on failure.
   */
  async resolveCredential(provider: LLMProvider): Promise<CLICredential> {
    // Ollama is local and needs no authentication
    if (provider === "ollama") {
      return { type: "bearer", token: "" };
    }
    if (provider === "deepseek") {
      const token = process.env.DEEPSEEK_API_KEY || "";
      if (token.trim()) return { type: "bearer", token: token.trim() };
      throw new Error(`DeepSeek auth failed: DEEPSEEK_API_KEY is not set.\n\n${AUTH_HELP.deepseek}`);
    }

    // 1. Verify the CLI tool actually exists on the system before claiming we're authenticated
    const command = LOGIN_COMMANDS[provider][0];
    this.assertCommandAvailable(command, provider);

    // Check cache
    const cached = this.cache[provider];
    if (cached && Date.now() < cached.expiresAt) {
      return cached.credential;
    }

    let credential: CLICredential;

    switch (provider) {
      case "antigravity":
        credential = await this.getAntigravityCredential();
        this.cache[provider] = {
          credential,
          expiresAt: this.getCacheExpiry(credential, 5 * 60 * 1000),
        };
        break;

      case "claude":
        credential = this.getClaudeCredential();
        this.cache[provider] = {
          credential,
          expiresAt: this.getCacheExpiry(credential, 30 * 60 * 1000),
        };
        break;

      case "openai":
        credential = this.getOpenAICredential();
        this.cache[provider] = {
          credential,
          expiresAt: this.getCacheExpiry(credential, 30 * 60 * 1000),
        };
        break;

      default: {
        const _exhaustive: never = provider;
        throw new Error(`resolveCredential: unsupported provider "${_exhaustive}"`);
      }
    }

    return credential;
  }

  async resolveToken(provider: LLMProvider): Promise<string> {
    return (await this.resolveCredential(provider)).token;
  }

  startLogin(provider: LLMProvider): void {
    if (provider === "ollama") {
      this.assertCommandAvailable("ollama", provider);
      this.launchInTerminal(["ollama", "serve"], "Ollama server");
      return;
    }
    if (provider === "deepseek") {
      throw new Error(AUTH_HELP.deepseek);
    }
    
    if (provider === "antigravity") {
      try {
        const credsPath = join(homedir(), ".gemini", "oauth_creds.json");
        const accountsPath = join(homedir(), ".gemini", "google_accounts.json");
        if (existsSync(credsPath)) rmSync(credsPath);
        if (existsSync(accountsPath)) rmSync(accountsPath);
      } catch { /* ignore */ }
    }

    this.invalidate(provider);
    const command = LOGIN_COMMANDS[provider];
    this.assertCommandAvailable(command[0], provider);
    this.launchInTerminal(command, `AI Agent ${provider} login`);
  }

  getAccountInfo(provider: LLMProvider): { email?: string; name?: string } {
    if (provider === "ollama") return { name: "Local (no account)" };
    if (provider === "deepseek") return { name: "API key configured" };

    if (provider === "antigravity") {
      // agy 1.0.5 keeps its account in the OS keychain (no readable creds file),
      // and has no `whoami` command, so we cannot reliably read the email. Only
      // report an account if a (legacy) readable creds file actually exists;
      // otherwise stay honest about it being a CLI-managed session.
      try {
        const credsPath = join(homedir(), ".gemini", "oauth_creds.json");
        if (existsSync(credsPath)) {
          const raw = readFileSync(credsPath, "utf-8");
          const data = JSON.parse(raw);
          if (data.id_token) {
            const claims = this.decodeJwtClaims(data.id_token);
            if (claims?.email) return { email: claims.email, name: claims.name };
          }
        }
      } catch { /* ignore */ }
      return { name: "agy CLI session" };
    }

    if (provider === "openai") {
      const pathsToCheck = [
        join(homedir(), ".config", "codex", "auth.json"),
        join(homedir(), ".codex", "auth.json"),
      ];
      for (const p of pathsToCheck) {
        if (existsSync(p)) {
          try {
            const raw = readFileSync(p, "utf-8");
            const data = JSON.parse(raw);
            const tokens = data.tokens;
            let idToken: string | undefined;
            if (typeof tokens === "object" && tokens !== null) {
              idToken = tokens.id_token;
            } else if (typeof tokens === "string") {
              idToken = tokens;
            }
            if (idToken) {
              const claims = this.decodeJwtClaims(idToken);
              if (claims) return { email: claims.email, name: claims.name || "Authenticated" };
            }
          } catch { /* ignore */ }
          break;
        }
      }
      return { name: "Authenticated" };
    }

    if (provider === "claude") {
      return { name: "Authenticated (CLI-managed)" };
    }

    return { name: "Unknown" };
  }

  /** Invalidate cached token, forcing re-fetch on next call */
  invalidate(provider: LLMProvider): void {
    delete this.cache[provider];
  }

  /**
   * Sign out / reset what the plugin can control for a provider, then drop the
   * cached credential. Returns a short note describing any limitation.
   *
   * The plugin only manages its own readable artifacts. CLI providers
   * (antigravity/claude/openai) keep their real session in their own
   * config/keychain, so a full sign-out may still require the provider CLI.
   */
  signOut(provider: LLMProvider): { ok: boolean; note: string } {
    this.invalidate(provider);

    if (provider === "ollama") {
      return { ok: true, note: "Ollama is local and needs no sign-out." };
    }
    if (provider === "deepseek") {
      // The key itself lives in plugin settings; the caller clears it. Nothing
      // to remove here beyond cache invalidation.
      return { ok: true, note: "Cleared the saved DeepSeek API key from plugin settings." };
    }

    if (provider === "antigravity") {
      const removed = this.removeFiles([
        join(homedir(), ".gemini", "oauth_creds.json"),
        join(homedir(), ".gemini", "google_accounts.json"),
        join(homedir(), ".incurator-obsidian-agent-cli", "agy-home", ".gemini", "oauth_creds.json"),
      ]);
      return {
        ok: true,
        note:
          (removed ? "Removed plugin-readable Antigravity credentials. " : "") +
          "agy may also hold a session in the OS keychain — run `agy` to fully sign out/in.",
      };
    }

    if (provider === "claude") {
      return {
        ok: true,
        note: "Cleared the cached Claude session. Claude Code manages its own login — run `claude` to fully sign out/in.",
      };
    }

    if (provider === "openai") {
      return {
        ok: true,
        note: "Cleared the cached Codex session. Codex manages its own login — run `codex` to fully sign out/in.",
      };
    }

    return { ok: true, note: "Cleared cached credentials." };
  }

  private removeFiles(paths: string[]): boolean {
    let removed = false;
    for (const p of paths) {
      try {
        if (existsSync(p)) {
          rmSync(p);
          removed = true;
        }
      } catch {
        /* ignore */
      }
    }
    return removed;
  }

  // ── Antigravity (agy) browser login ────────────────────────────

  private async getAntigravityCredential(): Promise<CLICredential> {
    // Antigravity CLI manages its own keychain/token refresh.
    // We just check if the config directories exist to consider it initialized.
    const legacyPath = join(homedir(), ".gemini", "oauth_creds.json");
    const newPath = join(homedir(), ".antigravitycli");
    const configPath = join(homedir(), ".gemini", "config");
    
    if (existsSync(legacyPath) || existsSync(newPath) || existsSync(configPath)) {
      return {
        type: "bearer",
        token: "cli-managed-token",
        expiresAt: Date.now() + 30 * 24 * 60 * 60 * 1000, // Dummy expiry 30 days
      };
    }

    throw new Error(
      `Antigravity auth failed: No Antigravity CLI config found. Install Antigravity CLI, run "agy", and complete the browser login flow.\n\n${AUTH_HELP.antigravity}`
    );
  }

  // ── Claude (Claude Code browser login) ─────────────────────────

  private getClaudeCredential(): CLICredential {
    // Claude Code recently moved config to ~/.claude.json and handles its own OAuth flow.
    // If ~/.claude.json exists, or the legacy ~/.claude/.credentials.json exists,
    // we consider it initialized and return a dummy credential to satisfy the UI check.
    const legacyPath = join(homedir(), ".claude", ".credentials.json");
    const newPath = join(homedir(), ".claude.json");
    
    if (existsSync(legacyPath) || existsSync(newPath)) {
      return {
        type: "bearer",
        token: "cli-managed-token",
        expiresAt: Date.now() + 30 * 24 * 60 * 60 * 1000, // Dummy expiry 30 days
      };
    }

    throw new Error(
      `Claude auth failed: No Claude Code config found. Install Claude Code, run "claude", and complete the browser login flow.\n\n${AUTH_HELP.claude}`
    );
  }

  // ── OpenAI (Codex / ChatGPT browser login) ─────────────────────

  private getOpenAICredential(): CLICredential {
    // Codex may store auth.json at ~/.config/codex/auth.json (Linux XDG) or ~/.codex/auth.json
    const pathsToCheck = [
      join(homedir(), ".config", "codex", "auth.json"),
      join(homedir(), ".codex", "auth.json"),
    ];

    let authPath: string | undefined;
    for (const p of pathsToCheck) {
      if (existsSync(p)) {
        authPath = p;
        break;
      }
    }

    if (authPath) {
      try {
        const raw = readFileSync(authPath, "utf-8");
        const config = JSON.parse(raw) as {
          tokens?: {
            access_token?: string;
          };
        };
        const token = config.tokens?.access_token;
        if (token && typeof token === "string" && token.length > 0) {
          const credential: CLICredential = {
            type: "bearer",
            token,
            expiresAt: this.decodeJwtExpiry(token),
          };
          this.assertFreshCredential("openai", credential);
          return credential;
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        throw new Error(
          `OpenAI auth failed: Could not read Codex credentials (${msg}).\n\n${AUTH_HELP.openai}`
        );
      }
    }

    throw new Error(
      `OpenAI auth failed: No Codex browser-login credentials found (checked ~/.config/codex/ and ~/.codex/).\n\n${AUTH_HELP.openai}`
    );
  }

  private getCacheExpiry(credential: CLICredential, fallbackMs: number): number {
    const now = Date.now();
    if (credential.expiresAt && credential.expiresAt > now + 60 * 1000) {
      return credential.expiresAt - 60 * 1000;
    }
    return now + fallbackMs;
  }



  private assertFreshCredential(
    provider: LLMProvider,
    credential: CLICredential
  ): void {
    if (credential.expiresAt && credential.expiresAt <= Date.now() + 60 * 1000) {
      throw new Error(
        `${provider} auth failed: Browser-login token is expired.\n\n${AUTH_HELP[provider]}`
      );
    }
  }

  private decodeJwtExpiry(token: string): number | undefined {
    const claims = this.decodeJwtClaims(token);
    return claims && typeof claims.exp === "number" ? claims.exp * 1000 : undefined;
  }

  private decodeJwtClaims(token: string): Record<string, any> | undefined {
    const parts = token.split(".");
    if (parts.length < 2) return undefined;
    const payload = parts[1];

    try {
      const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
      const padded = normalized.padEnd(
        normalized.length + ((4 - (normalized.length % 4)) % 4),
        "="
      );
      return JSON.parse(Buffer.from(padded, "base64").toString("utf-8"));
    } catch {
      return undefined;
    }
  }

  private getAugmentedEnv(): NodeJS.ProcessEnv {
    const home = process.env.HOME || process.env.USERPROFILE || "";
    const customPaths = buildGuiCliSearchPaths(home);

    const currentPath = process.env.PATH || "";
    const combinedPath = [...customPaths, currentPath].join(
      process.platform === "win32" ? ";" : ":"
    );

    return {
      ...process.env,
      PATH: combinedPath,
    };
  }

  private assertCommandAvailable(command: string, provider: LLMProvider): void {
    try {
      const checkCommand =
        process.platform === "win32"
          ? `where ${command}`
          : `command -v ${this.shellQuote(command)}`;
      execSync(checkCommand, {
        encoding: "utf-8",
        timeout: 5000,
        env: this.getAugmentedEnv(),
        stdio: ["ignore", "pipe", "pipe"],
      });
    } catch {
      throw new Error(
        `${provider} login failed: "${command}" CLI was not found on PATH.\n\n${AUTH_HELP[provider]}`
      );
    }
  }

  private launchInTerminal(command: string[], title: string): void {
    const commandText = command.map((part) => this.shellQuote(part)).join(" ");
    const script =
      `${commandText}; status=$?; echo; ` +
      `if [ $status -eq 0 ]; then echo "Login finished."; else echo "Login exited with status $status."; fi; ` +
      `echo "You can close this window."; read -r -p "Press Enter to close..."`;

    if (process.platform === "darwin") {
      this.spawnDetached("osascript", [
        "-e",
        `tell application "Terminal" to activate`,
        "-e",
        `tell application "Terminal" to do script ${this.appleScriptQuote(script)}`,
      ]);
      return;
    }

    if (process.platform === "win32") {
      this.spawnDetached("cmd.exe", [
        "/c",
        "start",
        title,
        "cmd.exe",
        "/k",
        command.join(" "),
      ]);
      return;
    }

    const terminal = this.findLinuxTerminal();
    if (!terminal) {
      throw new Error(
        `Could not find a terminal emulator to run: ${command.join(" ")}`
      );
    }

    this.spawnDetached(terminal.command, terminal.args(script));
  }

  private findLinuxTerminal():
    | { command: string; args: (script: string) => string[] }
    | null {
    const configuredTerminal = process.env.TERMINAL;
    if (configuredTerminal && this.commandExists(configuredTerminal)) {
      return {
        command: configuredTerminal,
        args: (script) => ["-e", "bash", "-lc", script],
      };
    }

    const candidates: Array<{
      command: string;
      args: (script: string) => string[];
    }> = [
      { command: "x-terminal-emulator", args: (script) => ["-e", "bash", "-lc", script] },
      { command: "gnome-terminal", args: (script) => ["--", "bash", "-lc", script] },
      { command: "konsole", args: (script) => ["-e", "bash", "-lc", script] },
      { command: "xfce4-terminal", args: (script) => ["--command", `bash -lc ${this.shellQuote(script)}`] },
      { command: "kitty", args: (script) => ["bash", "-lc", script] },
      { command: "alacritty", args: (script) => ["-e", "bash", "-lc", script] },
      { command: "wezterm", args: (script) => ["start", "--", "bash", "-lc", script] },
      { command: "xterm", args: (script) => ["-e", "bash", "-lc", script] },
    ];

    return candidates.find((candidate) => this.commandExists(candidate.command)) ?? null;
  }

  private commandExists(command: string): boolean {
    try {
      execSync(`command -v ${this.shellQuote(command)}`, {
        encoding: "utf-8",
        timeout: 5000,
        env: this.getAugmentedEnv(),
        stdio: ["ignore", "pipe", "pipe"],
      });
      return true;
    } catch {
      return false;
    }
  }

  private spawnDetached(command: string, args: string[]): void {
    const child = spawn(command, args, {
      detached: true,
      stdio: "ignore",
      windowsHide: false,
    });
    child.unref();
  }

  private shellQuote(value: string): string {
    return `'${value.replace(/'/g, `'\\''`)}'`;
  }

  private appleScriptQuote(value: string): string {
    return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
  }
}
