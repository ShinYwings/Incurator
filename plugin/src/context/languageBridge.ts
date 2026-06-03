export interface QueryLanguageMetadata {
  inputLanguage: string;
  englishQuery?: string;
  finalOutputLanguage: string;
}

interface ScriptRule {
  language: string;
  test: RegExp;
}

// Ordered by specificity. Kana is checked before Han so Japanese text that mixes
// Kana and Kanji is classified as Japanese rather than Chinese.
const SCRIPT_RULES: ScriptRule[] = [
  { language: "Korean", test: /[가-힣ᄀ-ᇿ㄰-㆏]/ },
  { language: "Japanese", test: /[぀-ゟ゠-ヿ]/ }, // Hiragana / Katakana
  { language: "Chinese", test: /[㐀-䶿一-鿿豈-﫿]/ }, // Han
  { language: "Russian", test: /[Ѐ-ӿ]/ }, // Cyrillic
  { language: "Greek", test: /[Ͱ-Ͽ]/ },
  { language: "Arabic", test: /[؀-ۿ]/ },
  { language: "Hebrew", test: /[֐-׿]/ },
  { language: "Hindi", test: /[ऀ-ॿ]/ }, // Devanagari
  { language: "Thai", test: /[฀-๿]/ },
];

/**
 * Deterministic, logic-level input-language detection by Unicode script ranges.
 * Runs fresh on every call (no persisted state). Latin / unknown text defaults
 * to English so a freshly detected English request always answers in English.
 */
export function detectLanguage(content: string): string {
  const text = (content || "").trim();
  if (!text) return "English";
  for (const rule of SCRIPT_RULES) {
    if (rule.test.test(text)) return rule.language;
  }
  return "English";
}

export function inferQueryLanguageMetadata(content: string): QueryLanguageMetadata {
  const text = (content || "").trim();
  const inputLanguage = detectLanguage(text);

  if (inputLanguage === "English") {
    return {
      inputLanguage: "English",
      englishQuery: text,
      finalOutputLanguage: "English",
    };
  }

  // Non-English: the backend computes english_query; the final answer targets
  // the freshly detected input language.
  return {
    inputLanguage,
    finalOutputLanguage: inputLanguage,
  };
}
