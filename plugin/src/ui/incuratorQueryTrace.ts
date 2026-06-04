import type { App } from "obsidian";
import type { CuratorQueryResult } from "../types";

/**
 * Renders the "Sources & Trace" collapsible panel below a curator_query answer.
 * Appended to the assistant message element after streaming completes.
 */
export function renderCuratorQueryTrace(
  container: HTMLElement,
  result: CuratorQueryResult,
  app: App
): void {
  const trace = result.trace;
  const exhId = result.exhibition_id;
  const hasV031 = Boolean(
    result.route ||
      result.trace_id ||
      result.source_span_ids?.length ||
      result.community_report_ids?.length ||
      result.memory_path_ids?.length ||
      result.prompt_trace_ids?.length ||
      result.insight_candidate_ids?.length
  );
  if (!trace && !exhId && !hasV031) return;

  // Remove any pre-existing trace panel (in case of re-render)
  container.querySelector(".incurator-trace-panel")?.remove();

  const panel = container.createDiv("incurator-trace-panel");

  // ── Collapsible header ──
  const header = panel.createDiv("incurator-trace-header");
  const latencyText = trace ? ` (${trace.latency_ms}ms)` : "";
  header.setText(`▶ Sources & Trace${latencyText}`);
  header.setAttribute("aria-expanded", "false");
  header.style.cursor = "pointer";
  header.style.userSelect = "none";

  const body = panel.createDiv("incurator-trace-body");
  body.style.display = "none";

  header.addEventListener("click", () => {
    const expanded = header.getAttribute("aria-expanded") === "true";
    header.setAttribute("aria-expanded", expanded ? "false" : "true");
    header.setText(`${expanded ? "▶" : "▼"} Sources & Trace${latencyText}`);
    body.style.display = expanded ? "none" : "block";
  });

  // ── Matched concepts ──
  if (trace?.matched_concepts?.length) {
    const conceptList = body.createDiv("incurator-trace-concepts");
    for (const conId of trace.matched_concepts.slice(0, 8)) {
      const row = conceptList.createDiv("incurator-trace-concept-row");
      row.createSpan({ text: "● ", cls: "incurator-trace-dot" });
      const link = row.createEl("a", { text: conId, cls: "incurator-trace-node-link" });
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const filePath = `.curator/Collections/03_Concepts/${conId}.md`;
        const file = app.vault.getAbstractFileByPath(filePath);
        if (file) app.workspace.openLinkText(filePath, "", false);
      });
    }
  }

  // ── Exhibition row ──
  if (exhId) {
    const exhRow = body.createDiv("incurator-trace-exh-row");
    exhRow.createSpan({ text: "Exhibition: ", cls: "incurator-trace-label" });
    const exhLink = exhRow.createEl("a", { text: exhId, cls: "incurator-trace-node-link" });
    exhLink.addEventListener("click", (e) => {
      e.preventDefault();
      const filePath = `.curator/Collections/04_Exhibitions/${exhId}.md`;
      const file = app.vault.getAbstractFileByPath(filePath);
      if (file) app.workspace.openLinkText(filePath, "", false);
    });
    if (result.cache_hit) {
      exhRow.createSpan({ text: "  [cache hit ✓]", cls: "incurator-trace-cache-hit" });
    }
  }

  // ── l3_complete indicator ──
  if (trace) {
    const metaRow = body.createDiv("incurator-trace-meta");
    metaRow.createSpan({
      text: trace.l3_complete ? "L3 complete ✓" : "L3 partial",
      cls: trace.l3_complete ? "incurator-trace-l3-ok" : "incurator-trace-l3-partial",
    });
  }

  // ── v0.3.1 curation-native trace (route, evidence ids, prompt traces) ──
  renderV031Trace(body, result);
}

/** Render the v0.3.1 route + evidence + prompt-trace rows. Degrades gracefully:
 * each row renders only when its field is present. */
function renderV031Trace(body: HTMLElement, result: CuratorQueryResult): void {
  if (result.route) {
    const routeRow = body.createDiv("incurator-trace-route");
    routeRow.createSpan({ text: "Route: ", cls: "incurator-trace-label" });
    routeRow.createSpan({ text: result.route, cls: "incurator-trace-route-badge" });
    if (result.trace_id) {
      routeRow.createSpan({ text: `  ${result.trace_id}`, cls: "incurator-trace-qtr" });
    }
  }

  const idRow = (label: string, ids?: string[], max = 8): void => {
    if (!ids?.length) return;
    const row = body.createDiv("incurator-trace-idrow");
    row.createSpan({ text: `${label} (${ids.length}): `, cls: "incurator-trace-label" });
    row.createSpan({
      text: ids.slice(0, max).join(", ") + (ids.length > max ? " …" : ""),
      cls: "incurator-trace-ids",
    });
  };

  idRow("Source spans", result.source_span_ids);
  idRow("Community reports", result.community_report_ids);
  idRow("Memory paths", result.memory_path_ids);
  idRow("Prompt traces", result.prompt_trace_ids);

  if (result.insight_candidate_ids?.length) {
    const row = body.createDiv("incurator-trace-insights");
    row.createSpan({
      text: `Insight candidates (provisional): ${result.insight_candidate_ids.length}`,
      cls: "incurator-trace-insight-label",
    });
  }

  if (result.warnings?.length) {
    const row = body.createDiv("incurator-trace-warnings");
    for (const w of result.warnings.slice(0, 4)) {
      row.createDiv({ text: `⚠ ${w}`, cls: "incurator-trace-warning" });
    }
  }
}
