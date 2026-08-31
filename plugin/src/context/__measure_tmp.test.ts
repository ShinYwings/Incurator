import { describe, it } from "vitest";
import { buildQuickQueryMessages } from "./quickQueryContext";
import type { ActiveContext, ContextRef } from "../types";

describe("measure realistic popover turn", () => {
  it("prints byte/char breakdown", () => {
    const selectedText =
      "As discussed in Section A4.2 (p580), the Jacobi eigenvalue algorithm " +
      "converges under mild conditions on the input matrix; see also Figure " +
      "19.1 for a visual comparison against the QR algorithm's convergence rate.";

    const pdfPageText = Array.from({ length: 40 })
      .map((_, i) => `Line ${i}: some representative body text from the current PDF page, discussing numerical linear algebra concepts and matrix decompositions in reasonable technical depth.`)
      .join("\n");

    const activeContext: ActiveContext = {
      viewType: "pdf",
      displayName: "Numerical Linear Algebra.pdf",
      filePath: "04_Resources/Numerical Linear Algebra.pdf",
      pdfPage: {
        pageNum: 210,
        documentName: "Numerical Linear Algebra.pdf",
        text: pdfPageText,
        outline: Array.from({ length: 15 }).map((_, i) => ({
          title: `${i + 1}.1 Some Chapter Heading ${i + 1}`,
          pageNum: 10 * (i + 1),
        })),
      },
    } as unknown as ActiveContext;

    const pinnedContextRefs: ContextRef[] = [
      {
        id: "pin1",
        type: "text",
        label: "My notes on eigenvalues",
        isPinned: true,
        includeInPrompt: true,
        content:
          "# Eigenvalues\n\nI previously noted that the Jacobi method is numerically stable for symmetric matrices. " +
          "Related to what Strang calls the 'rotation trick' in chapter 5. Need to revisit the convergence proof.".repeat(6),
      } as unknown as ContextRef,
    ];

    const vaultEvidenceBlock =
      "<vault_evidence>\n" +
      Array.from({ length: 5 })
        .map(
          (_, i) =>
            `<evidence_item source="02_Wiki/Linear Algebra Notes ${i}.md">\nSome retrieved passage about eigenvalue decomposition and its relation to PCA, item ${i}.\n</evidence_item>`
        )
        .join("\n") +
      "\n</vault_evidence>";

    const previousTurns = [
      { question: "이 제약이 무슨 뜻이야?", answer: "이 제약은 대칭 행렬에 대해서만 성립하는 수렴 조건을 의미합니다." },
      { question: "Figure 19.1은 뭘 보여줘?", answer: "QR 알고리즘과 Jacobi 알고리즘의 수렴 속도를 비교하는 그래프입니다." },
    ];

    const messages = buildQuickQueryMessages({
      selectedText,
      question: "이 제약이 무슨 뜻이야? 내가 쓴 다른 노트 중 관련된 게 있어?",
      provider: "claude",
      activeContext,
      previousTurns,
      pinnedContextRefs,
      vaultEvidenceBlock,
    });

    const system = messages[0].content as string;
    const user = messages[1].content as string;

    console.log("=== SYSTEM MESSAGE ===");
    console.log("length:", system.length);
    console.log("=== USER MESSAGE ===");
    console.log("length:", user.length);
    console.log("TOTAL:", system.length + user.length);

    function block(tagOpen: string, tagClose: string): number {
      const idx = user.indexOf(tagOpen);
      if (idx < 0) return 0;
      const end = user.indexOf(tagClose, idx);
      return end > idx ? end + tagClose.length - idx : 0;
    }

    const selectionLen = block("<primary_focus_selection>", "</primary_focus_selection>");
    const unresolvedLen = block("<unresolved_cross_references", "</unresolved_cross_references>");
    const backgroundLen = block("<quick_query_background>", "</quick_query_background>");
    const vaultLen = block("<vault_evidence>", "</vault_evidence>");
    const pinnedLen = block("<pinned_sources>", "</pinned_sources>");
    const followupLen = block("<quick_query_followups>", "</quick_query_followups>");
    const invariantsLen = block("<critical_invariants>", "</critical_invariants>");
    const questionLen = "Question: ".length + 30; // approx

    console.log("primary_focus_selection (document):", selectionLen);
    console.log("unresolved_cross_references (mostly instruction, note text):", unresolvedLen);
    console.log("quick_query_background (document):", backgroundLen);
    console.log("vault_evidence (document):", vaultLen);
    console.log("pinned_sources (document):", pinnedLen);
    console.log("quick_query_followups (conversation):", followupLen);
    console.log("critical_invariants (pure instruction):", invariantsLen);

    const UNRESOLVED_NOTE_LEN = 720; // approx, measured separately below
    console.log("");
    console.log("=== CLASSIFICATION ===");
    const pureInstruction = system.length + invariantsLen + UNRESOLVED_NOTE_LEN;
    const documentContent = selectionLen + backgroundLen + vaultLen + pinnedLen + followupLen + (unresolvedLen - UNRESOLVED_NOTE_LEN);
    console.log("Pure instruction prose (system + critical_invariants + unresolved-note):", pureInstruction);
    console.log("Document/evidence/conversation content:", documentContent);
    console.log("Ratio instruction:content =", (pureInstruction / documentContent).toFixed(2));
    console.log("Instruction as % of total turn:", ((pureInstruction / (pureInstruction + documentContent)) * 100).toFixed(1), "%");
  });
});
