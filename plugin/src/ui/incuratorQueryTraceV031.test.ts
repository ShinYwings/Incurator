import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// Source-string contract test (project convention for Obsidian DOM UI, which
// can't render under the node vitest environment). Verifies the v0.3.1 trace
// panel renders route + evidence ids + prompt traces + insight candidates and
// degrades gracefully.
const source = readFileSync(join(__dirname, "incuratorQueryTrace.ts"), "utf-8");

describe("incuratorQueryTrace v0.3.1 rendering", () => {
  it("renders when v0.3.1 trace fields are present (not just legacy trace)", () => {
    expect(source).toContain("const hasV031 = Boolean(");
    expect(source).toContain("if (!trace && !hasV031) return;");
  });

  it("has a dedicated v0.3.1 renderer invoked from the panel", () => {
    expect(source).toContain("renderV031Trace(body, result)");
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

  it("degrades gracefully: each id row guards on presence", () => {
    expect(source).toContain("if (!ids?.length) return;");
  });
});
