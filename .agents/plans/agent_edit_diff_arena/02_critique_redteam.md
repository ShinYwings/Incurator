# Critique on lead_architect's Edge-Hardening Proposal

Date: 2026-06-11 | Agent Persona: red_teamer (The Adversary)

## 1. Vulnerabilities & Flaws

**V1 — Tier 2 whitespace-normalized matching can silently corrupt semantically significant whitespace.** Markdown is whitespace-sensitive: indentation defines nested list items, 4-space = code block, and fenced code blocks must preserve exact spacing. If SEARCH normalizes intra-line whitespace and matches inside a fenced code block or a nested list, the replacement could splice the wrong span or break indentation. → **Mitigation demanded**: Tier 2 must be DISABLED inside fenced code regions, and must never be used to match a span that starts/ends mid-code-fence. Safer: drop Tier 2 entirely; Tier 1 (line-trim) + Tier 3 (anchored) cover the real-world LLM drift (indentation level) without the intra-line hazard. **Recommend removing Tier 2.**

**V2 — Auto-open diff (C) can hijack the user's editor / steal focus mid-typing.** `reviewAssistantEdit` opens the target leaf and mutates the editor with decorations. If the user is reading/editing another note, an async stream completing could yank a tab open or push decorations into the active editor. Worse: multiple proposals across files → multiple auto-opens. → **Mitigation**: auto-open ONLY if (a) exactly one target file, AND (b) that file is already the active MarkdownView OR no MarkdownView is focused; never call `getLeaf("tab")` to force-open during auto. For multi-file or background cases, keep the pill. Also: the `diffAutoOpened` guard must be per-message AND reset on session switch, or re-rendering history will re-open old diffs.

**V3 — Anchored tier (Tier 3) "exactly one candidate" is underspecified for repeated anchors.** If the first+last anchor lines recur (e.g. two functions both starting `## Notes` … ending `}`), the span between the FIRST first-anchor and the LAST last-anchor is huge and wrong, while "candidates" counting is ambiguous. → **Mitigation**: define candidate = minimal non-overlapping [firstAnchor_i, nextLastAnchorAfter_i]; if more than one such minimal span exists, return null. Add an explicit max-span guard (reject if matched span is > search length × 3 lines). Unit-test the recurring-anchor case.

**V4 — Disabling the artifact by default is a silent behavior change for existing users.** Someone relying on the `00_System/Agent Diffs/` trail loses it after update with no notice. → **Mitigation**: acceptable IF the setting remains and the CHANGELOG + setting description say "now off by default; the in-editor diff replaces it." Do NOT delete existing artifact files. Confirmed reversible — OK.

**V5 — `stripDanglingEditMarkers` could eat legitimate content.** A user's note legitimately discussing `>>>>` or `====` (e.g. documenting git conflict markers, or a horizontal rule `====`) would have those lines stripped from the RENDERED message. → **Mitigation**: only strip markers that are (a) on their own line AND (b) match the exact agent marker grammar (`<<<< SEARCH`, `==== REPLACE`, `>>>>` with optional trailing word) AND (c) appear OUTSIDE a fenced code block in the assistant message. Never mutate the stored `msg.content` used for copy — only the rendered HTML pass. This keeps "Copy as Markdown" faithful.

**V6 — Prompt-only scope fix (E) is the weakest link and will regress per-model.** The user explicitly noted behavior differs by model reasoning strength. A prompt rule won't make a weak model comply. → **Reality check**: accept it as best-effort, but ALSO add a defensive guard: if a single REPLACE body is larger than, say, the entire prior user request asked for AND equals/contains the full previous assistant answer verbatim, the apply path should warn ("This edit replaces a very large region — review carefully") rather than silently splicing. This is a cheap safety net independent of model quality. (Keep it a non-blocking warning, not a hard reject.)

**V7 — Three call sites "unified" but `reviewAssistantEdit` builds the diff differently** (whole-file `split/join`) than `applyInlineEdit` (single replaceRange). If the matcher returns a span but `reviewAssistantEdit` still uses `split(search)`, the fix is half-applied. → **Mitigation**: route `reviewAssistantEdit`'s modified-text construction through the SAME matcher (replace the `split/join` with matcher-driven splice) so preview == apply. This is the highest-value consistency fix and must be in P-core, not optional.

## 2. Suggested Alternatives (net)
- Drop Tier 2. Keep Tier 0/1/3 with explicit ambiguity + max-span guards.
- Gate auto-open hard (single file + active/no-focus only); per-message guard reset on session switch.
- Marker-strip only on rendered HTML, code-fence-aware, never on stored content.
- Add a non-blocking "large replacement" warning as a model-independent scope safety net.
- Make `reviewAssistantEdit` consume the unified matcher so preview and apply agree.
