import { describe, expect, it, vi } from "vitest";
import { readFileSync } from "fs";
import { fileURLToPath } from "url";
import { join } from "path";

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
  sortProfilesByRecency,
  ZoteroSearchModal,
  type ZoteroSearchResult,
  ZoteroWizardModal,
} from "./zoteroWizardModal";
import type { ZoteroImportProfile } from "../types";

function wizardSource(): string {
  const dir = fileURLToPath(new URL(".", import.meta.url));
  return readFileSync(join(dir, "zoteroWizardModal.ts"), "utf8");
}

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

  it("orders import profiles most-recently-used first, unused last, stable (v0.21.0)", () => {
    const profile = (name: string, lastUsedAt?: number): ZoteroImportProfile => ({
      name,
      templatePath: "",
      outputFolder: "",
      outputSubfolder: "",
      outputFilename: "",
      assetFolder: "",
      assetSubfolder: "",
      bibliographyStyle: "",
      lastUsedAt,
    });
    const input = [
      profile("never-A"),
      profile("older", 100),
      profile("never-B"),
      profile("newest", 300),
    ];
    const sorted = sortProfilesByRecency(input);

    // used profiles newest→oldest, then unused profiles in their original order.
    expect(sorted.map((p) => p.name)).toEqual([
      "newest",
      "older",
      "never-A",
      "never-B",
    ]);
    // Operates on a copy: the input array order is not mutated.
    expect(input.map((p) => p.name)).toEqual([
      "never-A",
      "older",
      "never-B",
      "newest",
    ]);
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

  it("auto-loads the most-recently-used profile, not merely the first saved (v0.21.0)", () => {
    const baseProfile = (name: string, lastUsedAt?: number) => ({
      name,
      templatePath: `Templates/${name}.md`,
      bibliographyStyle: "APA",
      outputFolder: "03_Notes",
      outputSubfolder: "",
      outputFilename: "{{ title }}",
      assetFolder: "05_Assets",
      assetSubfolder: "{{ citekey }}",
      lastUsedAt,
    });
    const wizard = new ZoteroWizardModal(
      {} as any,
      item("ITEM"),
      {} as any,
      {
        // Stored insertion order puts "First" at index 0, but "Recent" was used
        // more recently, so the wizard must auto-select "Recent".
        zoteroProfiles: [baseProfile("First", 100), baseProfile("Recent", 999)],
      } as any,
      async () => {}
    ) as any;

    expect(wizard.selectedProfile).toBe("Recent");
    expect(wizard.templatePath).toBe("Templates/Recent.md");
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

  it("stamps the selected import profile into created/updated notes (G17-6)", () => {
    const source = wizardSource();

    expect(source).toContain("profileNameForNote");
    expect(source).toContain("stampZoteroProfile(");
  });
});
