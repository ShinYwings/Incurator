/**
 * Decide which option a model `<select>` should show for a stored value.
 *
 * The dashboard's bundled model catalogue only contains well-known models. When
 * the active backend model is a custom one (e.g. a local Ollama model like
 * `ollama::qwen2.5:3b`), its catalogue value won't match any option. Previously
 * the select silently fell back to `selectedIndex = 0` — the first catalogue
 * entry (Antigravity Gemini) — so the dashboard misreported the active model
 * even though the backend config (`wiki status`) was correct.
 *
 * This helper keeps the displayed value faithful to the stored config:
 *   - "select": the value matches an existing option → select it as-is.
 *   - "inject": the value is a real model missing from the catalogue → the
 *     caller should add it as its own option and select it.
 *   - "default": no usable stored value → caller falls back (index 0 / none).
 */
export function resolveModelSelectValue(
  optionValues: string[],
  current: string,
): { action: "select" | "inject" | "default"; value: string } {
  if (!current) return { action: "default", value: "" };
  if (optionValues.includes(current)) return { action: "select", value: current };
  const sep = current.indexOf("::");
  const model = (sep >= 0 ? current.slice(sep + 2) : current).trim();
  if (model) return { action: "inject", value: current };
  return { action: "default", value: "" };
}
