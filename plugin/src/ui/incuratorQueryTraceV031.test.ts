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
    expect(source).toContain("renderV031Trace(body, result, app, interactive)");
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

  // The pure open-target decision (vault/external/external_pdf, page anchors,
  // external_uri-over-stub precedence) is behaviorally covered in
  // incuratorQueryTraceLocator.test.ts. Here we only assert the trace panel
  // delegates to that module and wires the Obsidian/Electron open side-effects
  // that cannot render under the node vitest environment.
  it("delegates locator resolution to the pure locatorTarget module", () => {
    expect(source).toContain('from "./incuratorQueryTraceLocator"');
    expect(source).toContain("locatorTarget(locator)");
    expect(source).toContain("function openLocator(");
    expect(source).toContain("incurator-trace-pack-locator-link");
  });

  it("wires the vault/external/external-pdf open side-effects", () => {
    expect(source).toContain("app.workspace.openLinkText");
    expect(source).toContain("shell.openPath");
    expect(source).toContain("shell.openExternal");
    expect(source).toContain("window.open");
    expect(source).toContain("openExternalReference");
  });

  it("opens external Reference Mode PDFs in the plugin's external PDF viewer at the cited page", () => {
    // Reference Mode sources are not in the vault: relpath is only an in-vault
    // stub while external_uri is the real file. PDFs open in the plugin's
    // external PDF viewer at the cited page, never the stub.
    expect(source).toContain("EXTERNAL_PDF_VIEW_TYPE");
    expect(source).toContain("registerExternalPdfByPath");
    expect(source).toContain("currentPage");
    expect(source).toContain('target.kind === "external_pdf"');
  });

  it("renders explicit expansion and verification handle controls", () => {
    expect(source).toContain("incurator-trace-pack-expand-btn");
    expect(source).toContain("incurator-trace-pack-verify-btn");
    expect(source).toContain("Expand");
    expect(source).toContain("Verify");
    expect(source).toContain("context:expand");
    expect(source).toContain("context:verify");
  });

  it("renders per-item feedback controls (thumbs + report menu) that dispatch context:feedback", () => {
    expect(source).toContain("function renderItemFeedback(");
    expect(source).toContain("incurator-trace-pack-feedback-btn");
    expect(source).toContain("incurator-trace-pack-feedback-report");
    expect(source).toContain("👍");
    expect(source).toContain("👎");
    expect(source).toContain('"relevant"');
    expect(source).toContain('"irrelevant"');
    // The report menu carries the remaining single-item quality signals.
    expect(source).toContain('value: "incorrect"');
    expect(source).toContain('value: "stale"');
    expect(source).toContain('value: "insufficient"');
    expect(source).toContain('value: "duplicate"');
    expect(source).toContain("context:feedback");
    // Feedback carries the targeted item + reviewed spans, never mutating truth.
    expect(source).toContain("trace_id: pack.trace_id");
    expect(source).toContain("item_id: item.record_id");
    expect(source).toContain("reviewed_span_ids: item.source_span_ids");
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

  it("renders a 'Save to 02_Wiki' promote button only when onPromote is provided", () => {
    expect(source).toContain("opts?: { onPromote?: () => void; interactive?: boolean }");
    expect(source).toContain("if (opts?.onPromote) {");
    expect(source).toContain("Save to 02_Wiki");
    expect(source).toContain('promoteBtn.addEventListener("click", () => opts.onPromote?.())');
    expect(styles).toContain(".incurator-trace-promote-btn");
  });

  it("can render historical trace panels without mutating pack actions", () => {
    expect(source).toContain("const interactive = opts?.interactive !== false;");
    expect(source).toContain("renderContextPack(body, result.context_pack, app, interactive)");
    expect(source).toContain(
      'if (interactive && (reason === "snapshot_conflict" || pack.resolution === "refetch_or_rebase"))'
    );
    expect(source).toContain("if (interactive && (item.expansion_handle || item.verification_handle))");
    expect(source).toContain("if (interactive) {");
    expect(source).toContain("renderItemFeedback(row, item, pack);");
  });
});
