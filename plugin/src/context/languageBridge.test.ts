import { describe, expect, it } from "vitest";
import { detectLanguage, inferQueryLanguageMetadata } from "./languageBridge";

describe("detectLanguage", () => {
  it("classifies major scripts deterministically", () => {
    expect(detectLanguage("What does this concept imply?")).toBe("English");
    expect(detectLanguage("이 논문의 핵심이 뭐야?")).toBe("Korean");
    expect(detectLanguage("这是什么概念?")).toBe("Chinese");
    expect(detectLanguage("この概念は何ですか")).toBe("Japanese");
    expect(detectLanguage("Что это за концепция?")).toBe("Russian");
  });

  it("defaults empty/unknown input to English", () => {
    expect(detectLanguage("")).toBe("English");
    expect(detectLanguage("   ")).toBe("English");
    expect(detectLanguage("123 456 ===")).toBe("English");
  });

  it("treats code-heavy English mixed with symbols as English", () => {
    expect(detectLanguage("rename src=\"05_Assets/Zotero Assets/zwicker2002ewa\"")).toBe("English");
  });
});

describe("inferQueryLanguageMetadata", () => {
  it("marks English as both working and final language", () => {
    expect(inferQueryLanguageMetadata("What does this concept imply?")).toEqual({
      inputLanguage: "English",
      englishQuery: "What does this concept imply?",
      finalOutputLanguage: "English",
    });
  });

  it("sets finalOutputLanguage equal to a detected non-English input language", () => {
    expect(inferQueryLanguageMetadata("이 논문의 핵심이 뭐야?")).toEqual({
      inputLanguage: "Korean",
      finalOutputLanguage: "Korean",
    });
    expect(inferQueryLanguageMetadata("这是什么概念?")).toEqual({
      inputLanguage: "Chinese",
      finalOutputLanguage: "Chinese",
    });
    expect(inferQueryLanguageMetadata("この概念は何ですか")).toEqual({
      inputLanguage: "Japanese",
      finalOutputLanguage: "Japanese",
    });
  });

  it("never carries a stale language: detection is per-call", () => {
    const ko = inferQueryLanguageMetadata("한국어 질문");
    const en = inferQueryLanguageMetadata("English question");
    expect(ko.finalOutputLanguage).toBe("Korean");
    expect(en.finalOutputLanguage).toBe("English");
  });
});
