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

  it("retrieves for PDF-focused turns whatever the L3 state is", () => {
    // This test used to assert the opposite — no vault query unless a focused
    // source had L3 complete — under the name "does not present PDF-focused
    // turns as concept-grounded before L3 completes". The concern was real and
    // the lever was wrong: L3 governs how an answer may be FRAMED, and this
    // function decides whether evidence is RETRIEVED.
    //
    // Measured on a live vault before changing it: `l3_status='done'` for 0 of
    // 44 sources (34 error, 2 pending, 8 skipped), so the condition could never
    // pass and the vault query never ran while any PDF tab was focused. And the
    // fetch does not need L3 — the same question returned `route: local` with 30
    // evidence items and 26 source spans while `community_report_ids` was 0.
    for (const statuses of [
      [{ state: "untracked" as const, l3Complete: false }],
      [{ state: "l1_ready" as const, l1Complete: true, l3Complete: false }],
      [{ state: "l3_ready" as const, l1Complete: true, l3Complete: true }],
    ]) {
      expect(
        shouldRunCuratorDomainQuery({
          query: "What does this paper conclude?",
          pdfFocused: true,
          pdfSourceStatuses: statuses,
        })
      ).toBe(true);
    }
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

describe("duty 2 — surfacing the reader's own notes (v0.62.3)", () => {
  it("runs the vault query for a KNOWLEDGE question about a selection", () => {
    // The failure this fixes. Selecting a passage and asking what else you wrote
    // about it is duty 2 itself, and the blanket selection rule turned off the
    // one retrieval that answers it. Measured live: the vault context fetch for
    // this exact question returns 30 evidence items across 6 sources —
    // Silhouette Based Reconstruction, EWA splatting, Auto Calibration and the
    // CUDA wiki among them — and the assistant surfaced none of them.
    expect(
      shouldRunCuratorDomainQuery({
        query: "이 제약이 무슨 뜻이야? 내가 쓴 다른 노트 중 관련된 게 있어?",
        userContextRefs: [ref({ type: "selection", filePath: "note.md" })],
      })
    ).toBe(true);
  });

  it("still skips the vault query for an EDIT command on a selection", () => {
    // What the original rule was actually protecting — its own test called these
    // "selected-context edits" and used exactly this example.
    for (const query of ["rewrite this", "fix the grammar here", "이거 다시 써줘", "translate this"]) {
      expect(
        shouldRunCuratorDomainQuery({
          query,
          userContextRefs: [ref({ type: "line-range", filePath: "note.md", lineStart: 1, lineEnd: 2 })],
        })
      ).toBe(false);
    }
  });

  it("runs the vault query with a PDF focused even when no source has L3", () => {
    // L3 governs how an answer may be FRAMED, not whether evidence may be
    // retrieved. Measured on the live vault: l3_status='done' for 0 of 44
    // sources (34 error, 2 pending, 8 skipped), so this condition could never
    // pass — with any PDF tab focused the vault query never ran. And the fetch
    // works without L3: the pack above came back `route: local` with
    // community_report_ids: 0 and 26 source spans.
    expect(
      shouldRunCuratorDomainQuery({
        query: "What else have I written about Plücker coordinates?",
        pdfFocused: true,
        pdfSourceStatuses: [{ state: "l1_ready", l1Complete: true, l3Complete: false }],
      })
    ).toBe(true);
  });
});
