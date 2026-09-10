import { describe, expect, it } from "vitest";
import { CliAnswerStream } from "./cliAnswerStream";

const edit = '```ai-agent-edit filepath="note.md"\n<<<< SEARCH\nold\n==== REPLACE\nnew\n>>>>\n```';
const codex = (id: string, text: string, type = "item.completed") =>
  JSON.stringify({ type, item: { id, type: "agent_message", text } });
const agy = (event: object) => JSON.stringify(event);

describe("native CLI answer stream integrity", () => {
  it.each(["progress ".repeat(70), "short progress"])("keeps final edits after independent progress messages", (progress) => {
    const stream = new CliAnswerStream("openai");
    expect(stream.consume(codex("first", progress)).text).toBe(progress);
    expect(stream.consume(codex("final", edit)).text).toBe(`\n\n${edit}`);
    expect(stream.reconcileFinal(edit)).toBe("");
    expect(stream.text).toBe(`${progress}\n\n${edit}`);
  });

  it("deduplicates item snapshots and extends a partial final file once", () => {
    const stream = new CliAnswerStream("openai");
    expect(stream.consume(codex("final", edit.slice(0, 30), "item.updated")).text).toBe("");
    stream.consume(codex("final", edit.slice(0, 50)));
    expect(stream.reconcileFinal(edit)).toBe(edit.slice(50));
    expect(stream.reconcileFinal(edit)).toBe("");
    expect(stream.text).toBe(edit);
  });

  it("does not confuse duplicate item completion with another item", () => {
    const stream = new CliAnswerStream("openai");
    stream.consume(codex("one", "same"));
    expect(stream.consume(codex("one", "same")).text).toBe("");
    expect(stream.consume(codex("two", "same")).text).toBe("\n\nsame");
  });

  it("keeps tool/error JSON out of answer prose", () => {
    const stream = new CliAnswerStream("openai");
    expect(stream.consume('{"type":"item.completed","item":{"type":"command_execution","text":"bad"}}').text).toBe("");
    stream.consume('{"type":"turn.failed","error":{"message":"provider failed"}}');
    expect(stream.text).toBe("");
    expect(stream.error).toContain("provider failed");
  });

  it("streams agy deltas immediately and reconciles result once", () => {
    const stream = new CliAnswerStream("antigravity");
    expect(stream.consume(agy({ event: "step_update", step_update: { step_index: 1, step_type: "agent_response", text_delta: "Equation " } })).text).toBe("Equation ");
    expect(stream.consume(agy({ event: "step_update", step_update: { step_index: 1, step_type: "agent_response", text_delta: "explained." } })).text).toBe("explained.");
    expect(stream.consume(agy({ event: "result", result: { status: "SUCCESS", response: "Equation explained." } })).text).toBe("");
    expect(stream.text).toBe("Equation explained.");
  });

  it("preserves agy partial answer and marks native failure", () => {
    const stream = new CliAnswerStream("antigravity");
    stream.consume(agy({ event: "step_update", step_update: { step_index: 1, step_type: "agent_response", text_delta: "Partial equation" } }));
    stream.consume(agy({ event: "result", result: { status: "ERROR", response: "Partial equation", error: "stream interrupted" } }));
    expect(stream.text).toBe("Partial equation");
    expect(stream.error).toBe("stream interrupted");
  });

  it("surfaces agy tool status and denied actions without turning them into prose", () => {
    const stream = new CliAnswerStream("antigravity");
    expect(stream.consume(agy({ event: "step_update", step_update: { step_type: "tool_call", tool_info: { name: "curator_fetch_context" } } })).status).toContain("curator_fetch_context");
    stream.consume(agy({ event: "result", result: { status: "SUCCESS", response: "", denied_actions: ["command"] } }));
    expect(stream.error).toContain("command");
    expect(stream.text).toBe("");
  });
});
