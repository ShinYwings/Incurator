import { describe, expect, it, vi } from "vitest";

vi.mock("obsidian", () => ({
  AbstractInputSuggest: class {},
  Modal: class {},
  Notice: class {},
  Setting: class {},
  SuggestModal: class {
    inputEl = {
      value: "",
      dispatchEvent: () => true,
    };
    setPlaceholder() {}
    onOpen() {}
  },
  TFolder: class {},
  moment: () => ({ format: () => "" }),
}));

import {
  prioritizeZoteroItems,
  rememberRecentZoteroItem,
  ZoteroSearchModal,
  type ZoteroSearchResult,
  ZoteroWizardModal,
} from "./zoteroWizardModal";

function item(key: string): ZoteroSearchResult {
  return {
    key,
    title: key,
    itemType: "journalArticle",
    creators: [],
    date: "2026",
  };
}

describe("Zotero wizard helpers", () => {
  it("prioritizes recently imported Zotero items without dropping results", () => {
    const sorted = prioritizeZoteroItems(
      [item("C"), item("A"), item("B")],
      ["B", "A"]
    );

    expect(sorted.map((result) => result.key)).toEqual(["B", "A", "C"]);
  });

  it("keeps recent Zotero item keys as a bounded LRU", () => {
    const settings = { recentZoteroItems: ["A", "B", "C"] };

    rememberRecentZoteroItem(settings, "B", 3);
    expect(settings.recentZoteroItems).toEqual(["B", "A", "C"]);

    rememberRecentZoteroItem(settings, "D", 3);
    expect(settings.recentZoteroItems).toEqual(["D", "B", "A"]);
  });
});

describe("Zotero import modals", () => {
  it("loads the first saved profile when the wizard opens", () => {
    const wizard = new ZoteroWizardModal(
      {} as any,
      item("ITEM"),
      {} as any,
      {
        zoteroProfiles: [
          {
            name: "Papers",
            templatePath: "Templates/Paper.md",
            bibliographyStyle: "APA",
            outputFolder: "03_Notes",
            outputSubfolder: "{{ date | format('YYYY') }}",
            outputFilename: "{{ title }}",
            assetFolder: "05_Assets",
            assetSubfolder: "{{ citekey }}",
          },
        ],
      } as any,
      async () => {}
    ) as any;

    expect(wizard.selectedProfile).toBe("Papers");
    expect(wizard.templatePath).toBe("Templates/Paper.md");
    expect(wizard.outputFolder).toBe("03_Notes");
  });

  it("requests empty-query suggestions when the search modal opens", () => {
    vi.useFakeTimers();
    try {
      const modal = new ZoteroSearchModal(
        {} as any,
        {} as any,
        { zoteroBasePath: "~/Zotero", recentZoteroItems: [] } as any,
        async () => {}
      ) as any;
      const dispatchEvent = vi.spyOn(modal.inputEl, "dispatchEvent");

      modal.onOpen();
      vi.advanceTimersByTime(100);

      expect(modal.inputEl.value).toBe("");
      expect(dispatchEvent).toHaveBeenCalledWith(expect.any(Event));
    } finally {
      vi.useRealTimers();
    }
  });
});
