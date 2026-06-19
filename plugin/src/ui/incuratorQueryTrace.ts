import type { App } from "obsidian";
import { fileURLToPath } from "url";
import type { CuratorContextItem, CuratorContextPack, CuratorQueryResult } from "../types";
import {
  EXTERNAL_PDF_VIEW_TYPE,
  type ExternalPdfState,
} from "./externalPdfView";
import { registerExternalPdfByPath } from "./externalPdfRegistry";
import { locatorTarget } from "./incuratorQueryTraceLocator";

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
  const hasV031 = Boolean(
    result.route ||
      result.trace_id ||
      result.source_span_ids?.length ||
      result.community_report_ids?.length ||
      result.synthesis_node_ids?.length ||
      result.memory_path_ids?.length ||
      result.prompt_trace_ids?.length ||
      result.insight_candidate_ids?.length ||
      result.context_pack
  );
  if (!trace && !hasV031) return;

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

  // ── Synthesis nodes row (shared L4) ──
  if (result.synthesis_node_ids?.length) {
    const synList = body.createDiv("incurator-trace-syn-rows");
    for (const synId of result.synthesis_node_ids.slice(0, 8)) {
      const row = synList.createDiv("incurator-trace-syn-row");
      row.createSpan({ text: "◆ ", cls: "incurator-trace-dot" });
      const link = row.createEl("a", { text: synId, cls: "incurator-trace-node-link" });
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const filePath = `.curator/Collections/04_Synthesis/${synId}.md`;
        const file = app.vault.getAbstractFileByPath(filePath);
        if (file) app.workspace.openLinkText(filePath, "", false);
      });
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
  renderV031Trace(body, result, app);
}

/** Render the v0.3.1 route + evidence + prompt-trace rows. Degrades gracefully:
 * each row renders only when its field is present. */
function renderV031Trace(body: HTMLElement, result: CuratorQueryResult, app: App): void {
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

  if (result.context_pack) {
    renderContextPack(body, result.context_pack, app);
  }
}

function renderContextPack(body: HTMLElement, pack: CuratorContextPack, app: App): void {
  const box = body.createDiv("incurator-trace-pack");
  const snapshotId = typeof pack.snapshot?.snapshot_id === "string" ? pack.snapshot.snapshot_id : "";
  const budget = pack.budget || {};
  const used = typeof budget.used_tokens === "number" ? budget.used_tokens : undefined;
  const limit = typeof budget.limit_tokens === "number" ? budget.limit_tokens : undefined;
  const coverage = pack.coverage || {};
  const sufficiency =
    typeof coverage.sufficiency === "string" ? coverage.sufficiency : undefined;

  const title = box.createDiv("incurator-trace-pack-title");
  title.createSpan({ text: "Context pack", cls: "incurator-trace-label" });
  if (pack.pack_id) title.createSpan({ text: ` ${pack.pack_id}`, cls: "incurator-trace-pack-id" });
  if (snapshotId) title.createSpan({ text: ` ${snapshotId}`, cls: "incurator-trace-snapshot-id" });
  if (used !== undefined && limit !== undefined) {
    title.createSpan({ text: ` budget ${used}/${limit}`, cls: "incurator-trace-budget" });
  }
  if (sufficiency) {
    title.createSpan({ text: ` ${sufficiency}`, cls: "incurator-trace-coverage" });
  }

  const degraded =
    pack.ok === false ||
    pack.operation === "snapshot_conflict" ||
    pack.error_type === "snapshot_conflict" ||
    pack.error === "snapshot_conflict" ||
    pack.error?.includes("snapshot_conflict");
  if (degraded) {
    const reason = pack.error_type || pack.error || "snapshot_conflict";
    box.createDiv({
      text: snapshotConflictText(pack, reason),
      cls: "incurator-trace-pack-degraded",
    });
    if (reason === "snapshot_conflict" || pack.resolution === "refetch_or_rebase") {
      const staleRow = box.createDiv("incurator-trace-pack-stale-actions");
      const refetch = staleRow.createEl("button", {
        text: "Refetch",
        cls: "incurator-trace-pack-refetch-btn",
      });
      refetch.addEventListener("click", () => {
        dispatchContextRefetch(staleRow, pack);
      });
    }
  }

  const items = pack.items || [];
  if (items.length) {
    const itemList = box.createDiv("incurator-trace-pack-items");
    for (const item of items.slice(0, 10)) {
      renderContextPackItem(itemList, item, app, pack);
    }
    if (items.length > 10) {
      itemList.createDiv({
        text: `${items.length - 10} more pack items omitted from panel`,
        cls: "incurator-trace-pack-more",
      });
    }
  }

  if (pack.next?.length) {
    const next = box.createDiv("incurator-trace-pack-next");
    next.createSpan({ text: `Omitted expansion handles (${pack.next.length}): `, cls: "incurator-trace-label" });
    next.createSpan({
      text: pack.next
        .slice(0, 8)
        .map((entry) => String(entry.handle || ""))
        .filter(Boolean)
        .join(", "),
      cls: "incurator-trace-ids",
    });
  }
}

function renderContextPackItem(
  parent: HTMLElement,
  item: CuratorContextItem,
  app: App,
  pack: CuratorContextPack
): void {
  const row = parent.createDiv("incurator-trace-pack-item");
  const heading = row.createDiv("incurator-trace-pack-item-heading");
  heading.createSpan({
    text: `${item.kind || "item"} ${item.record_id || ""}`.trim(),
    cls: "incurator-trace-pack-item-id",
  });
  if (item.truth_state || item.freshness_state) {
    heading.createSpan({
      text: ` truth=${item.truth_state || "unknown"} freshness=${item.freshness_state || "unknown"}`,
      cls: "incurator-trace-pack-state",
    });
  }

  const summary = item.summary || item.title || item.claim;
  if (summary) {
    row.createDiv({ text: summary, cls: "incurator-trace-pack-summary" });
  }

  if (item.locator) {
    const locatorRow = row.createDiv("incurator-trace-pack-locator");
    const target = locatorTarget(item.locator);
    if (target) {
      const link = locatorRow.createEl("a", {
        text: `Locator: ${target.label}`,
        cls: "incurator-trace-pack-locator-link",
      });
      link.addEventListener("click", (event) => {
        event.preventDefault();
        openLocator(app, item.locator!);
      });
    } else {
      locatorRow.setText(`Locator: ${compactJson(item.locator)}`);
    }
  }

  if (item.expansion_handle || item.verification_handle) {
    const handleRow = row.createDiv("incurator-trace-pack-handles");
    if (item.expansion_handle) {
      const expand = handleRow.createEl("button", {
        text: "Expand",
        cls: "incurator-trace-pack-expand-btn",
      });
      expand.addEventListener("click", () => {
        dispatchContextAction(handleRow, "context:expand", pack, item.expansion_handle!);
      });
    }
    if (item.verification_handle) {
      const verify = handleRow.createEl("button", {
        text: "Verify",
        cls: "incurator-trace-pack-verify-btn",
      });
      verify.addEventListener("click", () => {
        dispatchContextAction(handleRow, "context:verify", pack, item.verification_handle!);
      });
    }
  }
}

function compactJson(value: Record<string, unknown>): string {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function openLocator(app: App, locator: Record<string, unknown>): void {
  const target = locatorTarget(locator);
  if (!target) return;
  if (target.kind === "external_pdf") {
    void openExternalPdfLocator(app, target.linkpath, target.page);
    return;
  }
  if (target.kind === "external") {
    void openExternalReference(target.linkpath);
    return;
  }
  app.workspace.openLinkText(target.linkpath, "", false);
}

async function openExternalReference(linkpath: string): Promise<void> {
  const shell = getElectronShell();
  const localPath = localFilePath(linkpath);
  try {
    if (shell && localPath && shell.openPath) {
      const err = await shell.openPath(localPath);
      if (!err) return;
      console.warn("Electron shell.openPath failed; falling back to window.open", err);
    } else if (shell?.openExternal) {
      await shell.openExternal(linkpath);
      return;
    }
  } catch (err) {
    console.warn("Electron shell opener failed; falling back to window.open", err);
  }
  window.open(linkpath, "_blank", "noopener");
}

function localFilePath(linkpath: string): string | null {
  if (linkpath.startsWith("file://")) {
    try {
      return fileURLToPath(linkpath);
    } catch {
      return null;
    }
  }
  const hasScheme = /^[a-z][a-z0-9+.-]*:/i.test(linkpath);
  const isWindowsDrive = /^[a-zA-Z]:[\\/]/.test(linkpath);
  return hasScheme && !isWindowsDrive ? null : linkpath;
}

function getElectronShell(): {
  openPath?: (path: string) => Promise<string>;
  openExternal?: (url: string) => Promise<void>;
} | null {
  try {
    const electron = require("electron");
    if (electron?.shell) return electron.shell;
  } catch { /* noop */ }
  try {
    const remote = require("@electron/remote");
    if (remote?.shell) return remote.shell;
  } catch { /* noop */ }
  return null;
}

async function openExternalPdfLocator(
  app: App,
  filePath: string,
  page?: number
): Promise<void> {
  const base = registerExternalPdfByPath(filePath);
  const state: ExternalPdfState = page ? { ...base, currentPage: page } : base;
  const leaf = app.workspace.getLeaf("tab");
  await leaf.setViewState({ type: EXTERNAL_PDF_VIEW_TYPE, active: true, state });
  app.workspace.revealLeaf(leaf);
}

function dispatchContextAction(
  source: HTMLElement,
  action: "context:expand" | "context:verify",
  pack: CuratorContextPack,
  handle: string
): void {
  source.dispatchEvent(new CustomEvent(action, {
    bubbles: true,
    detail: {
      pack_id: pack.pack_id,
      snapshot_id: pack.snapshot?.snapshot_id,
      handle,
    },
  }));
}

function dispatchContextRefetch(source: HTMLElement, pack: CuratorContextPack): void {
  source.dispatchEvent(new CustomEvent("context:refetch", {
    bubbles: true,
    detail: {
      pack_id: pack.pack_id,
      expected_snapshot_id: pack.expected_snapshot_id,
      current_snapshot_id: pack.current_snapshot_id,
      resolution: pack.resolution,
    },
  }));
}

function snapshotConflictText(pack: CuratorContextPack, reason: string): string {
  if (reason !== "snapshot_conflict") return reason;
  const expected = pack.expected_snapshot_id ? ` expected=${pack.expected_snapshot_id}` : "";
  const current = pack.current_snapshot_id ? ` current=${pack.current_snapshot_id}` : "";
  return `snapshot_conflict${expected}${current}`;
}
