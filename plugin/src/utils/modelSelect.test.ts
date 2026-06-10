import { describe, expect, it } from "vitest";
import { resolveModelSelectValue } from "./modelSelect";

describe("resolveModelSelectValue", () => {
  const catalogue = [
    "antigravity::gemini-3-flash",
    "claude::claude-sonnet-4-6",
    "ollama::llama3",
  ];

  it("selects a value already present in the catalogue", () => {
    expect(resolveModelSelectValue(catalogue, "claude::claude-sonnet-4-6")).toEqual({
      action: "select",
      value: "claude::claude-sonnet-4-6",
    });
  });

  it("injects a custom model missing from the catalogue instead of snapping to index 0", () => {
    // The reported bug: ollama::qwen2.5:3b is a real active model not in the
    // bundled catalogue; it must be surfaced, not replaced by antigravity gemini.
    expect(resolveModelSelectValue(catalogue, "ollama::qwen2.5:3b")).toEqual({
      action: "inject",
      value: "ollama::qwen2.5:3b",
    });
  });

  it("falls back to default when there is no stored value", () => {
    expect(resolveModelSelectValue(catalogue, "")).toEqual({
      action: "default",
      value: "",
    });
  });

  it("falls back to default when a provider has no model component", () => {
    expect(resolveModelSelectValue(catalogue, "ollama::")).toEqual({
      action: "default",
      value: "",
    });
  });

  it("does not inject a whitespace-only model name", () => {
    expect(resolveModelSelectValue(catalogue, "ollama::   ")).toEqual({
      action: "default",
      value: "",
    });
  });
});
