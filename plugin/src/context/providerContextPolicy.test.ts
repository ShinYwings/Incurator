import { describe, expect, it } from "vitest";
import type { ContextRef } from "../types";
import {
  hasPrimaryImageContext,
  shouldResolveLatestUserPdfReferences,
  shouldRunCuratorDomainQuery,
  shouldUseBackendPdfContext,
} from "./providerContextPolicy";

function ref(overrides: Partial<ContextRef>): ContextRef {
  return {
    type: "text",
    label: "context",
    content: "content",
    ...overrides,
  };
}

describe("providerContextPolicy", () => {
  it("treats an included user image or crop as primary image context", () => {
    const refs = [
      ref({ type: "image", imageBase64: "abc" }),
      ref({ type: "pdf-page", imageBase64: "def", includeInPrompt: false }),
    ];

    expect(hasPrimaryImageContext(refs)).toBe(true);
  });

  it("ignores excluded image context for backend gating", () => {
    const refs = [ref({ type: "image", imageBase64: "abc", includeInPrompt: false })];

    expect(hasPrimaryImageContext(refs)).toBe(false);
    expect(shouldUseBackendPdfContext({ query: "what is shown?", userContextRefs: refs })).toBe(true);
  });

  it("skips backend PDF context when the current user turn already carries a crop image", () => {
    const refs = [ref({ type: "pdf-page", imageBase64: "abc" })];

    expect(shouldUseBackendPdfContext({ query: "explain this crop", userContextRefs: refs })).toBe(false);
  });

  it("skips backend PDF context when the viewer already has local page/window text", () => {
    expect(
      shouldUseBackendPdfContext({
        query: "explain this page",
        hasLocalViewerContext: true,
      })
    ).toBe(false);
  });

  it("runs Curator domain query for ordinary workspace questions", () => {
    expect(
      shouldRunCuratorDomainQuery({ query: "What does the geometry concept imply?" })
    ).toBe(true);
  });

  it("does not run Curator domain query for selected-context edits or short follow-ups", () => {
    expect(
      shouldRunCuratorDomainQuery({
        query: "rewrite this",
        userContextRefs: [ref({ type: "line-range", filePath: "note.md", lineStart: 1, lineEnd: 2 })],
      })
    ).toBe(false);
    expect(shouldRunCuratorDomainQuery({ query: "다시" })).toBe(false);
  });

  it("does not present PDF-focused turns as concept-grounded before L3 completes", () => {
    expect(
      shouldRunCuratorDomainQuery({
        query: "What does this paper conclude?",
        pdfFocused: true,
        pdfSourceStatuses: [{ state: "untracked", l3Complete: false }],
      })
    ).toBe(false);
    expect(
      shouldRunCuratorDomainQuery({
        query: "What does this paper conclude?",
        pdfFocused: true,
        pdfSourceStatuses: [{ state: "l1_ready", l1Complete: true, l3Complete: false }],
      })
    ).toBe(false);
    expect(
      shouldRunCuratorDomainQuery({
        query: "What does this paper conclude?",
        pdfFocused: true,
        pdfSourceStatuses: [{ state: "l3_ready", l1Complete: true, l3Complete: true }],
      })
    ).toBe(true);
  });

  it("resolves latest-user references for the active PDF", () => {
    expect(
      shouldResolveLatestUserPdfReferences({
        target: {
          isActive: true,
          openTabKey: '["ai-agent-external-pdf","zotero:ACTIVE",5]',
          zoteroAttachmentKey: "ACTIVE",
        },
      })
    ).toBe(true);
  });

  it("resolves an inactive PDF only when primary user context identifies the same document", () => {
    const target = {
      isActive: false,
      openTabKey: '["ai-agent-external-pdf","zotero:MATCH",5]',
      filePath: "/references/paper.pdf",
      fileHash: "paper-hash",
      zoteroAttachmentKey: "MATCH",
    };

    expect(
      shouldResolveLatestUserPdfReferences({
        target,
        userContextRefs: [
          ref({
            type: "pdf-page",
            filePath: "/references/paper.pdf",
            pageNum: 3,
          }),
        ],
      })
    ).toBe(true);

    expect(
      shouldResolveLatestUserPdfReferences({
        target,
        userContextRefs: [
          ref({
            type: "pdf-page",
            zoteroAttachmentKey: "OTHER",
            filePath: "/references/other.pdf",
          }),
        ],
      })
    ).toBe(false);
  });

  it("does not let auto or pinned-background PDF refs establish turn focus", () => {
    const target = {
      isActive: false,
      openTabKey: '["ai-agent-external-pdf","zotero:BACKGROUND",5]',
      filePath: "/references/background.pdf",
      zoteroAttachmentKey: "BACKGROUND",
    };

    expect(
      shouldResolveLatestUserPdfReferences({
        target,
        userContextRefs: [
          ref({
            type: "pdf-page",
            sourceViewType: "auto",
            openTabKey: target.openTabKey,
            filePath: target.filePath,
          }),
          ref({
            type: "pdf-page",
            isPinned: true,
            openTabKey: target.openTabKey,
            filePath: target.filePath,
          }),
        ],
      })
    ).toBe(false);
  });
});
