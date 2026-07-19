import { readFileSync } from "fs";
import { join } from "path";
import { fileURLToPath } from "url";
import { describe, expect, it } from "vitest";

describe("backend command boundary", () => {
  it("routes Zotero through the hidden plugin namespace", () => {
    const root = fileURLToPath(new URL("../../", import.meta.url));
    const source = readFileSync(join(root, "src/agent/incuratorClient.ts"), "utf8");

    expect(source).toContain("\"plugin\", \"zotero\", \"status\"");
    expect(source).toContain("\"plugin\", \"zotero\", \"init\"");
    expect(source).toContain("\"plugin\", \"zotero\", \"search\"");
    expect(source).toContain("\"plugin\", \"zotero\", \"metadata\"");
    expect(source).toContain("\"plugin\", \"zotero\", \"annotations\"");
    expect(source).toContain("\"plugin\", \"zotero\", \"resolve-pdf\"");
    expect(source).not.toContain("[\n      \"zotero\",");
  });

  it("constructs IncuratorClient with a backend JSON command runner", () => {
    const root = fileURLToPath(new URL("../../", import.meta.url));
    const source = readFileSync(join(root, "main.ts"), "utf8");
    const chatSidebar = readFileSync(join(root, "src/ui/chat/ChatSidebarView.ts"), "utf8");

    expect(source).toContain("this.runBackendJsonCommand.bind(this)");
    expect(chatSidebar).toContain("this.plugin.runBackendJsonCommand.bind(this.plugin)");
  });

  it("dashboard uses the shared backend command runner", () => {
    const root = fileURLToPath(new URL("../../", import.meta.url));
    const dashboard = readFileSync(join(root, "src/ui/incuratorDashboardModal.ts"), "utf8");

    expect(dashboard).toContain("this.plugin.runBackendCommand(cmdArgs)");
    expect(dashboard).not.toContain("require(\"child_process\").spawn");
  });

  it("routes source, PDF, query, and promote through hidden plugin commands first", () => {
    const root = fileURLToPath(new URL("../../", import.meta.url));
    const source = readFileSync(join(root, "src/agent/incuratorClient.ts"), "utf8");

    expect(source).toContain("\"plugin\", \"source\", \"status\"");
    expect(source).toContain("\"plugin\", \"version\"");
    expect(source).toContain("\"plugin\", \"source\", \"import\"");
    expect(source).toContain("\"plugin\", \"source\", \"register\"");
    expect(source).toContain("\"plugin\", \"source\", \"rebind\"");
    expect(source).toContain("\"plugin\", \"pdf\", \"context\"");
    expect(source).toContain("\"plugin\", \"pdf\", \"search\"");
    expect(source).toContain("\"plugin\", \"query\"");
    expect(source).toContain("\"plugin\", \"promote\"");
    expect(source).toContain("\"plugin\", \"zotero\", \"status\"");
    expect(source).toContain("\"plugin\", \"zotero\", \"init\"");
  });

  it("does not keep an Incurator MCP fallback inside the plugin-local client", () => {
    const root = fileURLToPath(new URL("../../", import.meta.url));
    const source = readFileSync(join(root, "src/agent/incuratorClient.ts"), "utf8");

    expect(source).not.toContain("MCPManager");
    expect(source).not.toContain("getIncuratorTools");
    expect(source).not.toContain("tryTool");
    expect(source).not.toContain("curator_get_version");
    expect(source).not.toContain("check_source_status");
    expect(source).not.toContain("search_curator");
  });

  it("installs plugin by copying pre-built files without running git pull or setup.sh", () => {
    const root = fileURLToPath(new URL("../../", import.meta.url));
    const source = readFileSync(join(root, "main.ts"), "utf8");

    // Copies pre-built plugin files from repo — does not re-run setup.sh or git pull
    expect(source).toContain("copyFileSync");
    expect(source).toContain("main.js");
    expect(source).not.toContain("git pull");
    expect(source).not.toContain('execAsync("./setup.sh"');
  });
});
