/** Preserve message identity: independent assistant items are not cumulative
 * snapshots. Only completed Codex items enter prose; agy supplies native deltas.
 * A final-file/result snapshot may extend the last item but must not repeat it. */
export class CliAnswerStream {
  text = "";
  error = "";
  private lastId = "";
  private lastText = "";
  private readonly completed = new Set<string>();

  constructor(private readonly provider: "openai" | "antigravity") {}

  reconcileFinal(text: string): string {
    if (!text || text.trim() === this.lastText.trim()) return "";
    const delta = text.startsWith(this.lastText) && this.lastText
      ? text.slice(this.lastText.length)
      : `${this.text ? "\n\n" : ""}${text}`;
    this.lastText = text;
    this.text += delta;
    return delta;
  }

  consume(line: string): { text: string; status?: string } {
    let event: any;
    try { event = JSON.parse(line); } catch { return { text: "" }; }
    if (!event || typeof event !== "object") return { text: "" };
    if (this.provider === "openai") {
      if (event.type === "turn.failed" || event.type === "error") {
        this.error = String(event.error?.message || event.message || "Codex turn failed");
      }
      const item = event.item || event.msg?.item || event.msg;
      if (!item || item.type !== "agent_message" || event.type === "item.started" || event.type === "item.updated") return { text: "" };
      const text = typeof item.text === "string" ? item.text : "";
      const id = String(item.id || `legacy-${this.completed.size}`);
      if (!text || this.completed.has(id)) return { text: "" };
      this.completed.add(id);
      this.lastId = id;
      this.lastText = text;
      const delta = `${this.text ? "\n\n" : ""}${text}`;
      this.text += delta;
      return { text: delta };
    }

    if (event.event === "result") {
      const result = event.result || {};
      if (result.status && result.status !== "SUCCESS") {
        this.error = String(result.error || `Antigravity turn ${result.status}`);
      }
      if (Array.isArray(result.denied_actions) && result.denied_actions.length) {
        this.error = `Antigravity denied required tools: ${JSON.stringify(result.denied_actions)}`;
      }
      return { text: this.reconcileFinal(typeof result.response === "string" ? result.response : "") };
    }
    const step = event.step_update;
    if (!step || typeof step !== "object") return { text: "" };
    if (step.step_type === "agent_response" && typeof step.text_delta === "string") {
      const id = String(step.step_index);
      const separator = this.text && id !== this.lastId ? "\n\n" : "";
      if (id !== this.lastId) this.lastText = "";
      this.lastId = id;
      this.lastText += step.text_delta;
      const delta = separator + step.text_delta;
      this.text += delta;
      return { text: delta };
    }
    const info = step.tool_info;
    return { text: "", status: info ? `Using tool: ${info.name || info.tool_name || step.step_type}` : undefined };
  }
}
