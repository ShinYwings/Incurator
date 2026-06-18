import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// Source-string contract test (project convention for Obsidian DOM UI, which
// can't render under the node vitest environment). Verifies the v0.3.1 trace
// panel renders route + evidence ids + prompt traces + insight candidates and
// degrades gracefully.
const source = readFileSync(join(__dirname, "incuratorQueryTrace.ts"), "utf-8");
const styles = readFileSync(join(__dirname, "../../styles.css"), "utf-8");

describe("incuratorQueryTrace v0.3.1 rendering", () => {
  it("renders when v0.3.1 trace fields are present (not just legacy trace)", () => {
    expect(source).toContain("const hasV031 = Boolean(");
    expect(source).toContain("if (!trace && !hasV031) return;");
  });

  it("has a dedicated v0.3.1 renderer invoked from the panel", () => {
    expect(source).toContain("renderV031Trace(body, result, app)");
    expect(source).toContain("function renderV031Trace(");
  });

  it("renders the route badge and QTR trace id", () => {
    expect(source).toContain("result.route");
    expect(source).toContain("incurator-trace-route-badge");
    expect(source).toContain("result.trace_id");
  });

  it("renders evidence id rows (spans, reports, memory paths, prompt traces)", () => {
    expect(source).toContain("result.source_span_ids");
    expect(source).toContain("result.community_report_ids");
    expect(source).toContain("result.memory_path_ids");
    expect(source).toContain("result.prompt_trace_ids");
  });

  it("surfaces insight candidates as provisional and shows warnings", () => {
    expect(source).toContain("result.insight_candidate_ids");
    expect(source).toContain("provisional");
    expect(source).toContain("result.warnings");
  });

  it("renders exact ContextService pack metadata, items, locators, and handles", () => {
    expect(source).toContain("result.context_pack");
    expect(source).toContain("function renderContextPack(");
    expect(source).toContain("incurator-trace-pack");
    expect(source).toContain("pack.pack_id");
    expect(source).toContain("pack.snapshot?.snapshot_id");
    expect(source).toContain("pack.budget");
    expect(source).toContain("pack.coverage");
    expect(source).toContain("pack.items");
    expect(source).toContain("item.expansion_handle");
    expect(source).toContain("item.verification_handle");
    expect(source).toContain("item.locator");
    expect(source).toContain("pack.next");
  });

  it("wires locator navigation for vault relpaths and external URIs", () => {
    expect(source).toContain("function locatorTarget(");
    expect(source).toContain("function openLocator(");
    expect(source).toContain("app.workspace.openLinkText");
    expect(source).toContain("window.open");
    expect(source).toContain("incurator-trace-pack-locator-link");
    expect(source).toContain("locator.locator_status === \"unavailable\"");
    expect(source).toContain("#^${blockId}");
    expect(source).toContain("linkpath");
  });

  it("jumps to the cited page for registered/vault PDFs via Obsidian's viewer", () => {
    // A vault PDF (source_kind === "vault_pdf", in-vault relpath, no external_uri)
    // opens in Obsidian and jumps to the cited page with the #page=N anchor.
    expect(source).toContain("source_kind");
    expect(source).toContain("vault_pdf");
    expect(source).toContain("#page=${page}");
    expect(source).toContain("app.workspace.openLinkText");
  });

  it("opens external Reference Mode PDFs in the plugin's external PDF viewer at the cited page", () => {
    // Reference Mode sources are not in the vault: relpath is only an in-vault
    // stub while external_uri is the real file. PDFs open in the plugin's
    // external PDF viewer at the cited page, never the stub.
    expect(source).toContain("EXTERNAL_PDF_VIEW_TYPE");
    expect(source).toContain("registerExternalPdfByPath");
    expect(source).toContain("currentPage");
    expect(source).toContain("external_pdf");
  });

  it("prefers external_uri over the in-vault stub for non-PDF references", () => {
    // For a non-PDF external reference, the system handler opens the real file;
    // the relpath stub must not win just because it is non-null.
    expect(source).toContain("locator.external_uri");
    expect(source).toContain("window.open");
    // external_uri branch is evaluated before the relpath/vault branch.
    expect(source.indexOf("const externalUri")).toBeLessThan(
      source.indexOf("if (relpath)")
    );
  });

  it("renders explicit expansion and verification handle controls", () => {
    expect(source).toContain("incurator-trace-pack-expand-btn");
    expect(source).toContain("incurator-trace-pack-verify-btn");
    expect(source).toContain("Expand");
    expect(source).toContain("Verify");
    expect(source).toContain("context:expand");
    expect(source).toContain("context:verify");
  });

  it("shows degraded or snapshot-conflict pack states explicitly", () => {
    expect(source).toContain("snapshot_conflict");
    expect(source).toContain("incurator-trace-pack-degraded");
    expect(source).toContain("pack.error_type === \"snapshot_conflict\"");
    expect(source).toContain("incurator-trace-pack-refetch-btn");
    expect(source).toContain("context:refetch");
    expect(source).toContain("snapshotConflictText");
  });

  it("styles pack actions and stale refetch controls without layout-shifting rows", () => {
    expect(styles).toContain(".incurator-trace-pack-handles");
    expect(styles).toContain(".incurator-trace-pack-stale-actions");
    expect(styles).toContain(".incurator-trace-pack-refetch-btn");
    expect(styles).toContain("min-height: 24px");
    expect(styles).toContain("overflow-wrap: anywhere");
  });

  it("degrades gracefully: each id row guards on presence", () => {
    expect(source).toContain("if (!ids?.length) return;");
  });
});
