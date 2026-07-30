# Domain A — Authored Parser and Resolver Review

Date: 2026-07-30
Status: LOCKED FOR REVIEW APPROVAL

## 1. Design Constraints from Code and Specs

- The syntax set remains wikilinks, embeds, inline internal Markdown
  links/images, body/YAML tags, and frontmatter wikilinks.
- Code and comments emit nothing, and masking must not create syntax.
- Resolution is exact and fail-closed; safe source-relative parent paths may
  resolve, but paths escaping the vault may not.
- `.md` and `.markdown` are both parsed as Markdown by the existing parser.

## 2. Alternatives and Trade-offs

- Keep the regexes: smallest diff, but cannot correctly handle variable closing
  fences, unclosed fences, balanced destinations, or escape state. Rejected.
- Add a full Markdown parser dependency: broad behavior and dependency surface
  for a closed feature. Rejected.
- Add focused scanners plus existing regexes for simple tokens: accepted.

## 3. Final Decision

- Preserve text length when masking.
- Scan fenced code and Markdown destinations deterministically.
- Filter escaped openers and invalid numeric-only tags.
- Use tri-state resolution and lexical inside-vault normalization.
- Centralize Markdown suffix recognition.

## 4. Implementation Pseudocode

```python
safe = mask_fences_preserving_length(body)
safe = mask_inline_code_preserving_length(safe)
safe = mask_comments_preserving_length(safe)
wiki_spans = scan_unescaped_wikilinks(safe)
markdown_spans = scan_balanced_inline_links(safe)
tag_text = blank_ranges(safe, wiki_spans + markdown_spans)
```
