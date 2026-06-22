import { describe, expect, it } from "vitest";
import { shouldHandleDiffShortcut } from "./diffKeyGuard";

// Minimal fake elements with just the `.contains` used by the predicate.
const node = (children: unknown[]) => ({
  contains: (other: unknown) => children.includes(other),
});

describe("shouldHandleDiffShortcut", () => {
  // Real body satisfies body.ownerDocument.body === body; mirror that here.
  const body: { ownerDocument?: { body: unknown } } = {};
  body.ownerDocument = { body };
  const focusInEditor = { ownerDocument: { body } };
  const focusInToolbar = { ownerDocument: { body } };
  const focusInChat = { ownerDocument: { body } }; // an <input>, not <body>
  const cmEditor = node([focusInEditor]);
  const toolbar = node([focusInToolbar]);

  it("fires when focus is inside the diff editor", () => {
    expect(shouldHandleDiffShortcut(focusInEditor, cmEditor, toolbar)).toBe(true);
  });

  it("fires when focus is inside the toolbar", () => {
    expect(shouldHandleDiffShortcut(focusInToolbar, cmEditor, toolbar)).toBe(true);
  });

  it("does NOT fire when focus is in the chat input (the core bug)", () => {
    expect(shouldHandleDiffShortcut(focusInChat, cmEditor, toolbar, true)).toBe(false);
  });

  it("does NOT fire on body focus when the diff leaf is NOT active", () => {
    expect(shouldHandleDiffShortcut(body, cmEditor, toolbar, false)).toBe(false);
    expect(shouldHandleDiffShortcut(null, cmEditor, toolbar, false)).toBe(false);
  });

  it("DOES fire on body focus when the diff leaf is active (clicked a non-focusable region)", () => {
    expect(shouldHandleDiffShortcut(body, cmEditor, toolbar, true)).toBe(true);
    expect(shouldHandleDiffShortcut(null, cmEditor, toolbar, true)).toBe(true);
  });

  it("is safe when editor/toolbar refs are missing", () => {
    expect(shouldHandleDiffShortcut(focusInEditor, null, null)).toBe(false);
  });
});
