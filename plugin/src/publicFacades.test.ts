import { readFileSync } from "fs";
import { dirname, join, resolve } from "path";
import { fileURLToPath } from "url";
import {
  ScriptKind,
  ScriptTarget,
  createSourceFile,
  forEachChild,
  getCombinedModifierFlags,
  isClassDeclaration,
  isExportDeclaration,
  isFunctionDeclaration,
  isInterfaceDeclaration,
  isIdentifier,
  isNamedExports,
  isStringLiteral,
  isTypeAliasDeclaration,
  isVariableStatement,
  ModifierFlags,
} from "typescript";
import { describe, expect, it } from "vitest";

const pluginSrc = dirname(fileURLToPath(import.meta.url));

function exportedNames(relativePath: string): Set<string> {
  const path = join(pluginSrc, relativePath);
  const source = createSourceFile(
    path,
    readFileSync(path, "utf8"),
    ScriptTarget.Latest,
    true,
    ScriptKind.TS
  );
  const names = new Set<string>();

  forEachChild(source, (node) => {
    if (isExportDeclaration(node) && node.exportClause && isNamedExports(node.exportClause)) {
      for (const element of node.exportClause.elements) names.add(element.name.text);
      return;
    }
    if (
      isExportDeclaration(node) &&
      !node.exportClause &&
      node.moduleSpecifier &&
      isStringLiteral(node.moduleSpecifier) &&
      node.moduleSpecifier.text.startsWith(".")
    ) {
      const target = resolve(dirname(path), `${node.moduleSpecifier.text}.ts`);
      const relativeTarget = target.slice(pluginSrc.length + 1);
      for (const name of exportedNames(relativeTarget)) names.add(name);
      return;
    }
    if (!(getCombinedModifierFlags(node as never) & ModifierFlags.Export)) return;
    if (
      isClassDeclaration(node) ||
      isFunctionDeclaration(node) ||
      isInterfaceDeclaration(node) ||
      isTypeAliasDeclaration(node)
    ) {
      if (node.name) names.add(node.name.text);
      return;
    }
    if (isVariableStatement(node)) {
      for (const declaration of node.declarationList.declarations) {
        if (isIdentifier(declaration.name)) names.add(declaration.name.text);
      }
    }
  });
  return names;
}

function sourceText(relativePath: string): string {
  return readFileSync(join(pluginSrc, relativePath), "utf8");
}

describe("stable plugin public facades", () => {
  it("keeps the LLM client exports available from agent/llmClient", () => {
    expect([...exportedNames("agent/llmClient.ts")]).toEqual(expect.arrayContaining([
      "ADAPTERS",
      "LLMClient",
      "extractAntigravityAnswerFromStderr",
      "formatMcpToolResultForDisplay",
      "formatQuotaErrorMessage",
      "isAntigravityStatusLine",
      "isQuotaErrorMessage",
      "mapOpenAIFinishReason",
      "normalizeOpenAIContent",
      "sanitizeOpenAIMessages",
      "shouldInjectMcpTools",
    ]));
  });

  it("keeps chat-sidebar exports available from ui/chatSidebar", () => {
    const names = exportedNames("ui/chatSidebar.ts");
    expect([...names]).toEqual(expect.arrayContaining([
      "CHAT_VIEW_TYPE",
      "ChatSidebarView",
      "MultiEditProposal",
    ]));
  });

  it("keeps external-PDF exports available from ui/externalPdfView", () => {
    const names = exportedNames("ui/externalPdfView.ts");
    expect([...names]).toEqual(expect.arrayContaining([
      "EXTERNAL_PDF_CONTEXT_EVENT",
      "EXTERNAL_PDF_VIEW_TYPE",
      "ExternalPdfState",
      "ExternalPdfView",
    ]));
  });

  it("delegates ExternalPdfView implementation to the ui/pdf owner", () => {
    const source = sourceText("ui/externalPdfView.ts");
    expect(source).toContain('export * from "./pdf/ExternalPdfView";');
    expect(source).not.toContain("class ExternalPdfView");
  });
});
