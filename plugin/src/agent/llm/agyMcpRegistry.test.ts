import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync, existsSync } from "fs";
import { tmpdir } from "os";
import { join } from "path";

vi.mock("obsidian", () => ({
  Notice: class { constructor(_m: string) {} },
  requestUrl: vi.fn(async () => ({ json: {} })),
}));

// LLMClient binds `homedir` at module load, so spying on it later does nothing —
// the first version of this file did exactly that, and the three "must be
// absent" assertions passed vacuously against a registry nothing had written.
const homeRef = vi.hoisted(() => ({ current: "" }));
vi.mock("os", async (importOriginal) => ({
  ...(await importOriginal<typeof import("os")>()),
  homedir: () => homeRef.current,
}));

import { LLMClient } from "./LLMClient";
import { DEFAULT_SETTINGS } from "../../types";

// `syncAgyMcpConfig` writes into `~/.gemini`, so these drive it against a
// throwaway home. The method is private; it is called directly rather than
// reimplemented, because what is under test IS that method.

let home: string;
let geminiDir: string;

beforeEach(() => {
  home = mkdtempSync(join(tmpdir(), "agy-home-"));
  geminiDir = join(home, ".gemini");
  homeRef.current = home;
});
afterEach(() => {
  vi.restoreAllMocks();
  rmSync(home, { recursive: true, force: true });
});

function sync(servers: Array<{ name: string; enabled: boolean }>): void {
  const client = new LLMClient(
    {
      ...DEFAULT_SETTINGS,
      provider: "antigravity",
      mcpServers: servers.map((s) => ({
        name: s.name, enabled: s.enabled, command: "echo", args: [s.name], env: {},
      })),
    } as never,
    {} as never,
  );
  (client as any).syncAgyMcpConfig();
}

/** The file agy actually reads. */
function registry(): Record<string, unknown> {
  const p = join(geminiDir, "config", "mcp_config.json");
  return existsSync(p) ? JSON.parse(readFileSync(p, "utf-8")).mcpServers : {};
}

describe("what Incurator registers in agy's MCP registry", () => {
  it("registers the servers it manages", () => {
    sync([{ name: "alpha", enabled: true }]);
    expect(Object.keys(registry())).toContain("alpha");
  });

  it("keeps a server the user registered with `agy mcp add`", () => {
    mkdirSync(join(geminiDir, "config"), { recursive: true });
    writeFileSync(
      join(geminiDir, "config", "mcp_config.json"),
      JSON.stringify({ mcpServers: { theirs: { command: "echo", args: ["hi"] } } })
    );

    sync([{ name: "alpha", enabled: true }]);

    expect(Object.keys(registry())).toContain("theirs");
  });

  it("removes a server the user DELETED from the plugin", () => {
    // The plugin's settings tab has a trash button (`mcpServers.splice`) and an
    // enabled toggle. Before this, neither reached the file agy reads: the write
    // was a union merge, so a deleted server stayed registered and callable
    // forever — `env` credentials included. It only became reachable when this
    // registry started being written at all; `settings.json` did replace
    // wholesale, but agy never read it, so nothing was live.
    sync([{ name: "alpha", enabled: true }, { name: "doomed", enabled: true }]);
    expect(Object.keys(registry())).toContain("doomed");

    sync([{ name: "alpha", enabled: true }]);

    expect(Object.keys(registry())).not.toContain("doomed");
    expect(Object.keys(registry())).toContain("alpha");
  });

  it("removes a server the user merely DISABLED", () => {
    sync([{ name: "alpha", enabled: true }]);
    sync([{ name: "alpha", enabled: false }]);
    expect(Object.keys(registry())).not.toContain("alpha");
  });

  it("prunes only its own retirements, never the user's servers", () => {
    mkdirSync(join(geminiDir, "config"), { recursive: true });
    writeFileSync(
      join(geminiDir, "config", "mcp_config.json"),
      JSON.stringify({ mcpServers: { theirs: { command: "echo", args: ["hi"] } } })
    );

    sync([{ name: "doomed", enabled: true }]);
    sync([]);

    const names = Object.keys(registry());
    expect(names).not.toContain("doomed");
    expect(names).toContain("theirs");
  });

  it("writes the same registration to the mirror agy also consults", () => {
    sync([{ name: "alpha", enabled: true }]);
    const mirror = JSON.parse(
      readFileSync(join(geminiDir, "antigravity", "mcp_config.json"), "utf-8")
    ).mcpServers;
    expect(Object.keys(mirror)).toContain("alpha");
  });
});

describe("the backend's own server survives a plugin turn (v0.73.2)", () => {
  it("does not delete a server the plugin never registered", () => {
    // `wiki config` / `wiki init` register the curator MCP server — the one
    // carrying vault search — into the same files. The settings.json write used
    // to replace `mcpServers` wholesale, which deleted it on every plugin turn.
    // Measured on a real session: the assistant had no vault-search tool, fell
    // back to shelling out to `rg`, and `command(wiki)` correctly refused it, so
    // the turn produced nothing at all.
    mkdirSync(geminiDir, { recursive: true });
    writeFileSync(
      join(geminiDir, "settings.json"),
      JSON.stringify({ mcpServers: { incurator: { command: "wiki", args: ["mcp"] } } })
    );

    sync([{ name: "incurator_fetch", enabled: true }]);

    const settings = JSON.parse(
      readFileSync(join(geminiDir, "settings.json"), "utf-8")
    ).mcpServers;
    expect(Object.keys(settings).sort()).toEqual(["incurator", "incurator_fetch"]);
  });

  it("still retires a server the plugin itself dropped, in settings.json too", () => {
    sync([{ name: "doomed", enabled: true }]);
    expect(
      Object.keys(
        JSON.parse(readFileSync(join(geminiDir, "settings.json"), "utf-8")).mcpServers
      )
    ).toContain("doomed");

    sync([]);

    expect(
      Object.keys(
        JSON.parse(readFileSync(join(geminiDir, "settings.json"), "utf-8")).mcpServers
      )
    ).not.toContain("doomed");
  });
});
