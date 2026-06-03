import { describe, expect, it } from "vitest";
import {
  DEFAULT_SETTINGS,
  getDefaultModel,
  getModelOption,
  modelSupportsVision,
  type ModelCatalogue,
} from "../types";
import { getBundledModelCatalogue } from "./bundledModelCatalogue";

const catalogue: ModelCatalogue = {
  antigravity: [
    {
      id: "gemini-fast",
      label: "Gemini Fast",
      supportsVision: true,
    },
    {
      id: "gemini-think",
      label: "Gemini Think",
      supportsVision: true,
    },
  ],
};

describe("model catalogue helpers", () => {
  it("uses the backend catalogue shape for known models", () => {
    expect(getModelOption(catalogue, "antigravity", "gemini-fast")?.label).toBe(
      "Gemini Fast"
    );
  });

  it("picks the flash-tier backend default", () => {
    expect(getDefaultModel(catalogue, "antigravity")).toBe("gemini-fast");
  });

  it("treats custom models as vision-capable unless backend says otherwise", () => {
    expect(modelSupportsVision(catalogue, "antigravity", "custom-model")).toBe(true);
  });

  it("defaults Incurator imports to reference mode", () => {
    expect(DEFAULT_SETTINGS.incuratorDefaultImportMode).toBe("reference");
  });

  it("loads the backend models.json catalogue at plugin build time", () => {
    const bundled = getBundledModelCatalogue();
    expect(getDefaultModel(bundled, "antigravity")).toBe("gemini-3.5-flash");
    expect(bundled.openai?.some((model) => model.id === "gpt-5.5")).toBe(true);
  });
});
