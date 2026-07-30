import { describe, expect, it } from "vitest";
import {
  DEFAULT_SETTINGS,
  getDefaultModel,
  getModelOption,
  modelSupportsVision,
  normalizeModelEffort,
  normalizePluginModelEffort,
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
    expect(bundled.openai?.map((model) => model.id)).toEqual([
      "gpt-5.6-sol",
      "gpt-5.6-terra",
      "gpt-5.6-luna",
      "gpt-5.5",
    ]);
    expect(bundled.claude?.map((model) => model.id)).toEqual([
      "claude-sonnet-4-6",
      "claude-fable-5",
      "claude-opus-4-8",
      "claude-haiku-4-5",
    ]);
    expect(bundled.openai?.[0]).toMatchObject({
      contextWindow: 272000,
      efforts: ["low", "medium", "high", "xhigh", "max", "ultra"],
      defaultEffort: "low",
    });
    expect(bundled.claude?.[3]).toMatchObject({ efforts: [], defaultEffort: "" });
    expect(bundled.antigravity?.map((model) => model.id)).toContain(
      "claude-opus-4-6-thinking"
    );
    expect(
      getModelOption(
        bundled,
        "antigravity",
        "claude-opus-4-6-thinking"
      )
    ).toMatchObject({ efforts: [], defaultEffort: "" });
    expect(DEFAULT_SETTINGS.codexReasoningEffort).toBe("low");
    expect(DEFAULT_SETTINGS.claudeEffort).toBe("high");
  });

  it("normalizes effort by transition intent and clears no-effort models", () => {
    const option = {
      id: "sol",
      label: "Sol",
      supportsVision: true,
      efforts: ["low", "medium", "high"],
      defaultEffort: "low",
    };
    expect(normalizeModelEffort(option, "medium", false)).toBe("medium");
    expect(normalizeModelEffort(option, "medium", true)).toBe("low");
    expect(normalizeModelEffort(option, "invalid", false)).toBe("low");
    expect(normalizeModelEffort({ ...option, efforts: [], defaultEffort: "" }, "high", false)).toBe("");
  });

  it("normalizes the provider-specific persisted effort slot", () => {
    const bundled = getBundledModelCatalogue();
    const settings = {
      ...DEFAULT_SETTINGS,
      provider: "openai" as const,
      model: "gpt-5.6-sol",
      codexReasoningEffort: "medium" as const,
    };
    expect(normalizePluginModelEffort(settings, bundled, true)).toBe(true);
    expect(settings.codexReasoningEffort).toBe("low");

    settings.provider = "claude" as never;
    settings.model = "claude-haiku-4-5";
    settings.claudeEffort = "high";
    expect(normalizePluginModelEffort(settings, bundled, false)).toBe(true);
    expect(settings.claudeEffort).toBe("");
  });
});
