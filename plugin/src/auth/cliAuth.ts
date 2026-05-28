import { execSync, spawn } from "child_process";
import { readFileSync, existsSync, writeFileSync } from "fs";
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
};

const LOGIN_COMMANDS: Record<LLMProvider, string[]> = {
  antigravity: ["agy"],
  claude: ["claude", "auth", "login"],
  openai: ["codex", "login"],
};

const GEMINI_OAUTH_CLIENT_ID =
  "681255809395-oo8ft2oprdrnp9e3aqf6av3hmdib135j.apps.googleusercontent.com";
const GEMINI_OAUTH_CLIENT_SECRET = "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";

export class CLIAuthResolver {
  private cache: Partial<Record<LLMProvider, TokenCache>> = {};

  /**
   * Resolve a browser-CLI credential for the given provider.
   * Throws with a user-friendly message on failure.
   */
  async resolveCredential(provider: LLMProvider): Promise<CLICredential> {
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
    }

    return credential;
  }

  async resolveToken(provider: LLMProvider): Promise<string> {
    return (await this.resolveCredential(provider)).token;
  }

  startLogin(provider: LLMProvider): void {
    this.invalidate(provider);
    const command = LOGIN_COMMANDS[provider];
    this.assertCommandAvailable(command[0], provider);
    this.launchInTerminal(command, `AI Agent ${provider} login`);
  }

  /** Invalidate cached token, forcing re-fetch on next call */
  invalidate(provider: LLMProvider): void {
    delete this.cache[provider];
  }

  // ── Antigravity (agy) browser login ────────────────────────────

  private async getAntigravityCredential(): Promise<CLICredential> {
    // Antigravity CLI still stores OAuth creds at ~/.gemini/oauth_creds.json
    const credentialsPath = join(
      homedir(), ".gemini", "oauth_creds.json"
    );
    if (!existsSync(credentialsPath)) {
      throw new Error(
        `Antigravity auth failed: No Antigravity CLI browser-login credentials found at ${credentialsPath}.\n\n${AUTH_HELP.antigravity}`
      );
    }

    try {
      const raw = readFileSync(credentialsPath, "utf-8");
      const config = JSON.parse(raw) as {
        access_token?: string;
        refresh_token?: string;
        expiry_date?: number | string;
        token_type?: string;
        scope?: string;
        id_token?: string;
      };

      const currentCredential: CLICredential | null =
        config.access_token && typeof config.access_token === "string"
          ? {
              type: "bearer",
              token: config.access_token,
              expiresAt: this.normalizeExpiry(config.expiry_date),
            }
          : null;

      if (
        currentCredential &&
        (!currentCredential.expiresAt ||
          currentCredential.expiresAt > Date.now() + 60 * 1000)
      ) {
        return currentCredential;
      }

      if (!config.refresh_token) {
        throw new Error("Antigravity CLI credential is expired and has no refresh token.");
      }

      const refreshed = await this.refreshAntigravityCredential(config.refresh_token);
      const updatedConfig = {
        ...config,
        access_token: refreshed.access_token,
        token_type: refreshed.token_type || config.token_type || "Bearer",
        expiry_date: Date.now() + refreshed.expires_in * 1000,
        refresh_token: refreshed.refresh_token || config.refresh_token,
      };
      writeFileSync(credentialsPath, `${JSON.stringify(updatedConfig, null, 2)}\n`);

      return {
        type: "bearer",
        token: updatedConfig.access_token,
        expiresAt: this.normalizeExpiry(updatedConfig.expiry_date),
      };
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new Error(
        `Antigravity auth failed: ${msg}\n\n${AUTH_HELP.antigravity}`
      );
    }
  }

  // ── Claude (Claude Code browser login) ─────────────────────────

  private getClaudeCredential(): CLICredential {
    const credentialsPath = join(homedir(), ".claude", ".credentials.json");
    if (existsSync(credentialsPath)) {
      try {
        const raw = readFileSync(credentialsPath, "utf-8");
        const config = JSON.parse(raw) as {
          claudeAiOauth?: {
            accessToken?: string;
            expiresAt?: number | string;
          };
        };
        const token = config.claudeAiOauth?.accessToken;
        if (token && typeof token === "string" && token.length > 0) {
          const credential: CLICredential = {
            type: "bearer",
            token,
            expiresAt: this.normalizeExpiry(config.claudeAiOauth?.expiresAt),
          };
          this.assertFreshCredential("claude", credential);
          return credential;
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        throw new Error(
          `Claude auth failed: Could not read Claude Code credentials (${msg}).\n\n${AUTH_HELP.claude}`
        );
      }
    }

    throw new Error(
      `Claude auth failed: No Claude Code browser-login credentials found at ${credentialsPath}.\n\n${AUTH_HELP.claude}`
    );
  }

  // ── OpenAI (Codex / ChatGPT browser login) ─────────────────────

  private getOpenAICredential(): CLICredential {
    const authPath = join(homedir(), ".codex", "auth.json");
    if (existsSync(authPath)) {
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
      `OpenAI auth failed: No Codex browser-login credentials found at ${authPath}.\n\n${AUTH_HELP.openai}`
    );
  }

  private getCacheExpiry(credential: CLICredential, fallbackMs: number): number {
    const now = Date.now();
    if (credential.expiresAt && credential.expiresAt > now + 60 * 1000) {
      return credential.expiresAt - 60 * 1000;
    }
    return now + fallbackMs;
  }

  private async refreshAntigravityCredential(refreshToken: string): Promise<{
    access_token: string;
    expires_in: number;
    token_type?: string;
    refresh_token?: string;
  }> {
    const body = new URLSearchParams({
      client_id: GEMINI_OAUTH_CLIENT_ID,
      client_secret: GEMINI_OAUTH_CLIENT_SECRET,
      refresh_token: refreshToken,
      grant_type: "refresh_token",
    });

    const response = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body,
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(
        `Antigravity CLI token refresh failed (${response.status}): ${errorText.slice(0, 200)}`
      );
    }

    const json = (await response.json()) as {
      access_token?: string;
      expires_in?: number;
      token_type?: string;
      refresh_token?: string;
    };
    if (!json.access_token || !json.expires_in) {
      throw new Error("Antigravity CLI token refresh returned an invalid response.");
    }
    return {
      access_token: json.access_token,
      expires_in: json.expires_in,
      token_type: json.token_type,
      refresh_token: json.refresh_token,
    };
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

  private normalizeExpiry(value: number | string | undefined): number | undefined {
    if (typeof value === "number") {
      return value < 10_000_000_000 ? value * 1000 : value;
    }
    if (typeof value === "string" && value.length > 0) {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {
        return parsed < 10_000_000_000 ? parsed * 1000 : parsed;
      }
      const dateMs = Date.parse(value);
      if (Number.isFinite(dateMs)) return dateMs;
    }
    return undefined;
  }

  private decodeJwtExpiry(token: string): number | undefined {
    const [, payload] = token.split(".");
    if (!payload) return undefined;

    try {
      const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
      const padded = normalized.padEnd(
        normalized.length + ((4 - (normalized.length % 4)) % 4),
        "="
      );
      const parsed = JSON.parse(Buffer.from(padded, "base64").toString("utf-8")) as {
        exp?: number;
      };
      return typeof parsed.exp === "number" ? parsed.exp * 1000 : undefined;
    } catch {
      return undefined;
    }
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
