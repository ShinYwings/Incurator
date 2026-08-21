import { describe, expect, it } from "vitest";
import {
  buildActiveBackgroundContext,
  buildPrimarySelectionBlock,
  buildQuickQueryMessages,
} from "./quickQueryContext";
import { boundaryConstraints, POPOVER_PROFILE } from "./promptRegistry";
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
    // The recency anchor mentions the tag name in prose, so assert the actual
    // resolved block (identified by its closing tag) is not injected.
    expect(String(messages[1].content)).not.toContain("</resolved_cross_references>");
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
    // (v0.19.0: boundary text now sourced from the shared prompt registry.)
    expect(system).toContain("NO filesystem access");
    expect(system).toContain("Never list, browse, create, or execute files");
    expect(system).toContain("never invent folder, file, or directory names");
  });

  it("sources the popover boundary from the shared registry, not a hardcoded duplicate (v0.19.0)", () => {
    const messages = buildQuickQueryMessages({
      selectedText: "anything",
      question: "what?",
    });
    const system = String(messages[0].content);
    // The exact boundary string must match promptRegistry.boundaryConstraints
    // for the popover profile, proving both surfaces share one source of truth.
    expect(system).toContain(boundaryConstraints(POPOVER_PROFILE));
  });

  it("appends a read-only recency anchor LAST so its invariants get strongest attention (v0.19.0)", () => {
    const messages = buildQuickQueryMessages({
      selectedText: "Result 19.4",
      question: "summarize",
    });
    const user = String(messages[1].content);
    expect(user).toContain("<critical_invariants>");
    expect(user).toContain("read-only: do NOT output any ai-agent-edit blocks");
    // The anchor sits after the question (recency position).
    expect(user.indexOf("<critical_invariants>")).toBeGreaterThan(user.indexOf("Question:"));
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

  it("injects sidechat pinned context refs as background when provided (v0.53.2)", () => {
    const messages = buildQuickQueryMessages({
      selectedText: "camera projection matrix",
      question: "이 행렬의 수식은?",
      pinnedContextRefs: [
        {
          type: "file",
          label: "pinhole_camera.md",
          content: "# Pinhole Camera\nThe projection matrix P = K[R|t] maps 3D to 2D.",
          isPinned: true,
          filePath: "03_Notes/Vision/pinhole_camera.md",
        },
        {
          type: "pdf-page",
          label: "HZ.pdf p.154",
          content: "The camera matrix is a 3x4 matrix P = KR[I|-C].",
          isPinned: true,
          filePath: "04_Resources/References/HZ.pdf",
          pageNum: 154,
        },
      ],
    });

    const user = String(messages[1].content);
    // Pinned sources appear as background context in the user message.
    expect(user).toContain("<pinned_sources>");
    expect(user).toContain("pinhole_camera.md");
    expect(user).toContain("P = K[R|t]");
    expect(user).toContain("HZ.pdf p.154");
    expect(user).toContain("P = KR[I|-C]");
    expect(user).toContain("</pinned_sources>");
  });

  it("does not inject pinned sources block when none are provided", () => {
    const messages = buildQuickQueryMessages({
      selectedText: "some text",
      question: "explain",
    });

    const user = String(messages[1].content);
    expect(user).not.toContain("<pinned_sources>");
  });

  it("system prompt allows parametric fallback for popover (v0.53.2)", () => {
    const messages = buildQuickQueryMessages({
      selectedText: "camera projection",
      question: "수식 알려줘",
    });
    const system = String(messages[0].content);
    // The system prompt must allow the LLM to use general knowledge as a fallback.
    expect(system).toContain("general knowledge");
  });
});

describe("duty 2 — the popover surfaces the reader's own notes (v0.62.3)", () => {
  it("carries vault evidence into the turn and names it in the system prompt", () => {
    // The popover had NO vault retrieval on its path: it assembled from the
    // selection, the current file's outline, pinned refs and citation
    // resolution, and `IncuratorClient.curatorQuery` had zero callers anywhere.
    // Measured live, asking "내가 쓴 다른 노트 중 관련된 게 있어?" about a selected
    // passage returned only sections of the SAME note, while the vault held 21
    // published sources matching the topic.
    const block =
      '<vault_evidence query="Plücker" route="local">\n' +
      "03_Notes/Vision/Silhouette Based Reconstruction.md — Plücker line coords\n" +
      "</vault_evidence>";
    const messages = buildQuickQueryMessages({
      selectedText: "Dual Quadric Q*와 Plücker Line 사이의 대수적 손실",
      question: "내가 쓴 다른 노트 중 관련된 게 있어?",
      vaultEvidenceBlock: block,
    });
    const user = messages.find((m) => m.role === "user")!.content;
    const system = messages.find((m) => m.role === "system")!.content;

    expect(user).toContain("Silhouette Based Reconstruction.md");
    expect(user).toContain("<vault_evidence");
    // The block must not be silently present-but-unexplained: the model is told
    // what it is and to name the note, which is what duty 2 asks for.
    expect(system).toContain("<vault_evidence>");
    expect(system).toMatch(/own vault/i);
    expect(system).toMatch(/name the note/i);
  });

  it("omits the block entirely when there is no vault evidence", () => {
    const messages = buildQuickQueryMessages({
      selectedText: "some text",
      question: "what is this?",
    });
    expect(messages.find((m) => m.role === "user")!.content).not.toContain("<vault_evidence");
  });
});
