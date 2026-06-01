import { describe, expect, it } from "vitest";
import {
  getDefaultModel,
  getModelOption,
  modelSupportsVision,
  type ModelCatalogue,
} from "../types";

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
});
