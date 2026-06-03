import modelsJson from "../../../backend/src/curator/data/models.json";
import type { ModelCatalogue, ModelOption } from "../types";

type BackendModel = {
  id?: unknown;
  label?: unknown;
  context_window?: unknown;
  supports_vision?: unknown;
  supports_thinking?: unknown;
  efforts?: unknown;
  default_effort?: unknown;
};

type BackendCatalogue = {
  providers?: Record<string, { models?: BackendModel[] }>;
};

const VALID_PROVIDERS = new Set(["antigravity", "claude", "openai", "ollama", "deepseek"]);

function normalizeModel(model: BackendModel): ModelOption | null {
  if (typeof model.id !== "string" || !model.id) return null;
  const efforts = Array.isArray(model.efforts)
    ? model.efforts.filter((effort): effort is string => typeof effort === "string")
    : [];
  const option: ModelOption = {
    id: model.id,
    label: typeof model.label === "string" && model.label ? model.label : model.id,
    supportsVision: model.supports_vision !== false,
    efforts,
    defaultEffort: typeof model.default_effort === "string" ? model.default_effort : "",
  };
  if (typeof model.context_window === "number") {
    option.contextWindow = model.context_window;
  }
  return option;
}

export function getBundledModelCatalogue(): ModelCatalogue {
  const raw = modelsJson as BackendCatalogue;
  const catalogue: ModelCatalogue = {};
  for (const [provider, info] of Object.entries(raw.providers || {})) {
    if (!VALID_PROVIDERS.has(provider)) continue;
    const models = (info.models || [])
      .map(normalizeModel)
      .filter((model): model is ModelOption => Boolean(model));
    if (models.length > 0) {
      catalogue[provider as keyof ModelCatalogue] = models;
    }
  }
  return catalogue;
}
