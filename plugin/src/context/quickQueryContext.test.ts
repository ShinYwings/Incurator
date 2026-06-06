import { describe, expect, it } from "vitest";
import {
  buildActiveBackgroundContext,
  buildPrimarySelectionBlock,
  buildQuickQueryMessages,
} from "./quickQueryContext";
import type { ActiveContext } from "../types";

describe("quick query context builder", () => {
  it("wraps selected text as the primary focus", () => {
    expect(buildPrimarySelectionBlock("Eq. (3)")).toBe(
      "<primary_focus_selection>\nEq. (3)\n</primary_focus_selection>"
    );
  });

  it("includes active Markdown content and heading outline as background", () => {
    const activeCtx: ActiveContext = {
      viewType: "markdown",
      filePath: "03_Notes/Vision/foo.md",
      displayName: "foo",
      fileContent: "# Chapter 1\nIntro\n## Section 4.2\nDetails",
    };

    const background = buildActiveBackgroundContext(activeCtx, {
      selectedText: "Section 4.2",
      maxBackgroundLength: 2000,
    });

    expect(background).toContain("<markdown_outline");
    expect(background).toContain("- Chapter 1");
    expect(background).toContain("  - Section 4.2");
    expect(background).toContain("<background_reference_only>");
    expect(background).toContain("03_Notes/Vision/foo.md");
  });

  it("includes PDF window and outline as background", () => {
    const activeCtx: ActiveContext = {
      viewType: "pdf",
      displayName: "paper.pdf",
      pdfPage: {
        pageNum: 7,
        text: "current page text",
        windowPages: [
          { pageNum: 6, text: "previous page" },
          { pageNum: 7, text: "current page text" },
        ],
        outline: [{ title: "Projective Geometry", pageNum: 4, level: 0 }],
      },
    };

    const background = buildActiveBackgroundContext(activeCtx, {
      selectedText: "dual absolute quadric",
      maxBackgroundLength: 2000,
    });

    expect(background).toContain("<pdf_window");
    expect(background).toContain("### Page 6");
    expect(background).toContain("<document_outline");
    expect(background).toContain("Projective Geometry p.4");
  });

  it("injects a resolved-cross-references block when the selection is a pointer", () => {
    const activeCtx: ActiveContext = {
      viewType: "pdf",
      displayName: "HZ.pdf",
      pdfPage: {
        pageNum: 468,
        text: "current page on auto-calibration",
        windowPages: [
          { pageNum: 468, text: "current page on auto-calibration" },
        ],
        outline: [
          { title: "A4.2 Symmetric and skew-symmetric matrices", pageNum: 604, level: 1 },
        ],
      },
    };

    const messages = buildQuickQueryMessages({
      selectedText: "see section A4.2 (p580) for Jacobi's algorithm",
      question: "이거 설명해줘",
      activeContext: activeCtx,
    });

    const user = String(messages[1].content);
    expect(user).toContain("<resolved_cross_references>");
    expect(user).toContain("A4.2");
    // Resolved references rank above the generic background.
    expect(user.indexOf("<resolved_cross_references>")).toBeLessThan(
      user.indexOf("<quick_query_background>")
    );
    // The system prompt teaches pointer-following behavior.
    expect(String(messages[0].content)).toContain("POINTER");
  });

  it("uses PDF page labels to resolve printed-page pointer selections", () => {
    const pageLabels = Array.from({ length: 604 }, (_, index) => String(index + 1000));
    pageLabels[603] = "580";
    const activeCtx: ActiveContext = {
      viewType: "pdf",
      displayName: "HZ.pdf",
      pdfPage: {
        pageNum: 468,
        text: "current page on auto-calibration",
        pageLabels,
        windowPages: [
          { pageNum: 468, text: "current page on auto-calibration" },
          { pageNum: 604, text: "Jacobi's algorithm diagonalizes a symmetric matrix." },
        ],
      },
    };

    const messages = buildQuickQueryMessages({
      selectedText: "see p580 for Jacobi's algorithm",
      question: "이거 설명해줘",
      activeContext: activeCtx,
    });

    const user = String(messages[1].content);
    expect(user).toContain('target_page="604"');
    expect(user).toContain("Jacobi's algorithm");
  });

  it("does not inject a resolved block for ordinary (non-pointer) selections", () => {
    const messages = buildQuickQueryMessages({
      selectedText: "The fundamental matrix has rank 2.",
      question: "무슨 뜻이야?",
    });
    expect(String(messages[1].content)).not.toContain("<resolved_cross_references>");
  });

  it("teaches that positional words mean within-document and forbids filesystem listing (item 19)", () => {
    const messages = buildQuickQueryMessages({
      selectedText: "Result 19.4",
      question: "문서 위쪽을 찾아줘",
    });
    const system = String(messages[0].content);
    // Positional intent stays inside the document, not the folder tree.
    expect(system).toContain("위쪽");
    expect(system).toContain("WITHIN the current document");
    // No filesystem access → must not list/invent folder or file names.
    expect(system).toContain("never list, browse, or invent folder names");
  });

  it("adds ephemeral popover follow-up turns without chat-sidebar history", () => {
    const messages = buildQuickQueryMessages({
      selectedText: "H is Sim(3)",
      question: "그럼 Q는?",
      previousTurns: [
        { question: "H가 뭐야?", answer: "H is a similarity transform." },
      ],
    });

    expect(messages).toHaveLength(2);
    expect(String(messages[0].content)).toContain("same popover");
    expect(String(messages[1].content)).toContain("<quick_query_followups>");
    expect(String(messages[1].content)).toContain("H is a similarity transform.");
    expect(String(messages[1].content)).toContain("<primary_focus_selection>");
  });
});
