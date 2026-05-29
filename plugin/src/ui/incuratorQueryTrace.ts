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
  if (!trace && !exhId) return;

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
}
