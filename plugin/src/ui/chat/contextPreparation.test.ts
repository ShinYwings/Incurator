import { describe, expect, it, vi } from "vitest";

vi.mock("obsidian", () => ({
  ItemView: class {}, WorkspaceLeaf: class {}, MarkdownView: class {},
  Modal: class {}, SuggestModal: class {}, FuzzySuggestModal: class {},
  TFile: class {}, FileSystemAdapter: class {}, Plugin: class {},
  PluginSettingTab: class {}, Component: class {}, MarkdownRenderChild: class {},
  Notice: class {}, Menu: class {}, Setting: class {},
  setIcon: vi.fn(), moment: (value: string) => ({ format: () => value }),
}));
vi.mock("../externalPdfView", () => ({
  ExternalPdfView: class {}, EXTERNAL_PDF_VIEW_TYPE: "external-pdf", EXTERNAL_PDF_CONTEXT_EVENT: "pdf-context",
}));
vi.mock("../diffViewer", () => ({ DiffViewer: class {} }));
vi.mock("../externalPdfRegistry", () => ({ registerExternalPdf: vi.fn() }));
vi.mock("../../context/pdfReferenceContext", () => ({ resolveSelectionReferencesBlockAsync: vi.fn(async () => "explicit reference") }));

import { ChatSidebarView } from "./ChatSidebarView";
import { DEFAULT_SETTINGS } from "../../types";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function harness(tabs: any[] = []) {
  const fetchContext = vi.fn(async () => ({ ok: false }));
  const getPdfContext = vi.fn(async () => ({ pages: [], outline: [] }));
  const view: any = Object.create(ChatSidebarView.prototype);
  Object.assign(view, {
    plugin: { settings: { ...DEFAULT_SETTINGS }, },
    app: { workspace: { getActiveFile: () => ({ path: "01_Workspaces/Lab/note.md" }) } },
    incuratorStatusByPath: new Map(),
    getIncuratorClient: () => ({ available: true, fetchContext, getPdfContext }),
    getPromptIncludedTabs: () => tabs,
    contextWorkspacePath: () => "/vault/01_Workspaces/Lab",
    workspaceNotesFor: vi.fn(async () => "workspace notes"),
    setPrepareStatus: vi.fn(), logContextTiming: vi.fn(),
    toAbsolutePath: (path: string) => path,
    refStatusKey: () => "pdf", getOpenTabKey: () => "pdf",
    ensureIncuratorStatusForRef: vi.fn(async () => undefined),
  });
  return { view, fetchContext, getPdfContext };
}

describe("sidechat preparation scheduling", () => {
  it("skips automatic knowledge when off but retains explicit PDF references", async () => {
    const { view, fetchContext } = harness([{ label: "paper", isActive: true, viewType: "pdf", pdfPage: { text: "visible", pageNum: 1 } }]);
    const text = await view.buildIncuratorProviderContext({}, "Explain equation 4", undefined, false);
    expect(fetchContext).not.toHaveBeenCalled();
    expect(view.workspaceNotesFor).not.toHaveBeenCalled();
    expect(text).toContain("explicit reference");
  });

  it("starts evidence before a slow PDF read finishes and consults project notes once", async () => {
    const { view, fetchContext, getPdfContext } = harness([1, 2, 3].map((n) => ({
      label: `paper ${n}`, isActive: true, viewType: "pdf", filePath: `paper${n}.pdf`, pdfPage: { pageNum: 1 },
    })));
    const pdf = deferred<any>();
    getPdfContext.mockImplementation(() => pdf.promise);
    const pending = view.buildIncuratorProviderContext({}, "Explain geometry", undefined, true);
    await Promise.resolve();
    expect(fetchContext).toHaveBeenCalledTimes(1);
    expect(view.workspaceNotesFor).toHaveBeenCalledTimes(1);
    pdf.resolve({ pages: [], outline: [] });
    const text = await pending;
    expect(text.match(/workspace notes/g)).toHaveLength(1);
  });

  it("consults workspace notes in a markdown-only turn and defaults missing setting to on", async () => {
    const { view, fetchContext } = harness();
    delete view.plugin.settings.sidechatKnowledgeEnabled;
    const text = await view.buildIncuratorProviderContext({}, "Explain geometry");
    expect(fetchContext).toHaveBeenCalledTimes(1);
    expect(view.workspaceNotesFor).toHaveBeenCalledTimes(1);
    expect(text).toContain("workspace notes");
  });

  it("uses the captured note's workspace after the active tab changes", async () => {
    const { view, fetchContext } = harness();
    delete view.contextWorkspacePath;
    view.app.vault = { adapter: { getBasePath: () => "/vault" } };
    await view.buildIncuratorProviderContext({ filePath: "01_Workspaces/Original/note.md" }, "Explain geometry");
    expect(fetchContext).toHaveBeenCalledWith("Explain geometry", expect.objectContaining({
      workspacePath: "/vault/01_Workspaces/Original",
    }));
    expect(view.workspaceNotesFor).toHaveBeenCalledWith("Explain geometry", "01_Workspaces/Original");
  });

  it("observes failed optional reads while document work is pending", async () => {
    const { view, fetchContext, getPdfContext } = harness([{ label: "paper", isActive: true, viewType: "pdf", filePath: "paper.pdf", pdfPage: { pageNum: 1 } }]);
    const pdf = deferred<any>();
    getPdfContext.mockImplementation(() => pdf.promise);
    fetchContext.mockRejectedValue(new Error("retrieval offline"));
    view.workspaceNotesFor.mockRejectedValue(new Error("note offline"));
    const pending = view.buildIncuratorProviderContext({}, "Explain geometry", undefined, true);
    // Let both rejections settle before unblocking the independent document read.
    await new Promise((resolve) => setTimeout(resolve, 0));
    pdf.resolve({ pages: [], outline: [] });
    await expect(pending).resolves.toContain("explicit reference");
  });
});

describe("canonical edit review target", () => {
  it.each(["Research Notes/a.md", "/vault/Research Notes/a.md", "Research%20Notes/a.md"])(
    "opens review for %s when it resolves to the focused note",
    async (filepath) => {
      const { view } = harness();
      Object.assign(view, {
        getEditTargetContextForMessage: () => undefined,
        extractMultiEditProposals: () => [{ filepath, search: "old", replace: "new" }],
        resolveVaultFile: () => ({ path: "Research Notes/a.md" }),
        reviewFileEditProposals: vi.fn(async () => true),
      });
      view.app.workspace.getActiveViewOfType = () => ({ file: { path: "Research Notes/a.md" } });
      const msg = { content: "edit proposal" };
      await view.maybeAutoOpenDiff(msg);
      expect(view.reviewFileEditProposals).toHaveBeenCalledTimes(1);
      expect(msg).toMatchObject({ diffAutoOpened: true });
      await view.maybeAutoOpenDiff(msg);
      expect(view.reviewFileEditProposals).toHaveBeenCalledTimes(1);
    },
  );

  it("keeps review closed while a different note is focused", async () => {
    const { view } = harness();
    Object.assign(view, {
      getEditTargetContextForMessage: () => undefined,
      extractMultiEditProposals: () => [{ filepath: "/vault/a.md", search: "old", replace: "new" }],
      resolveVaultFile: () => ({ path: "a.md" }),
      reviewFileEditProposals: vi.fn(async () => true),
    });
    view.app.workspace.getActiveViewOfType = () => ({ file: { path: "b.md" } });
    await view.maybeAutoOpenDiff({ content: "edit proposal" });
    expect(view.reviewFileEditProposals).not.toHaveBeenCalled();
  });
});
