# Domain A — Authored Reference Extraction and Resolution

Date: 2026-07-30
Status: LOCKED FOR v0.39.0 PLAN REVIEW

## 1. Design Constraints from the Codebase

- Only registered visible Markdown source truth may emit authored topology.
  PDF/external attachment content and `.curator` projections are not note
  structure.
- Existing section extraction can omit pre-heading frontmatter and does not
  consistently retain exact character offsets. F9 must not trigger a broad
  L1 span redesign.
- Obsidian targets may omit `.md`, be source-relative or root-relative, include
  heading/block fragments, and use pipe display aliases.
- The resolver must never guess between duplicate basenames or aliases.
- Tags can occur in body text or YAML `tags`; aliases are metadata for target
  lookup, not edges.

## 2. Alternatives and Trade-offs

### A. Regex directly inside `compile.py`

Small initial diff, but mixes syntax, vault resolution, and publication in an
already central orchestration module. It is difficult to test masking and
ambiguity independently. Rejected.

### B. New general Markdown AST and note-native IR

Could model every Obsidian extension but adds a large parser/IR abstraction for
four required edge forms. It would exceed F9 and duplicate current ingestion
work. Rejected for this milestone.

### C. Focused deterministic extractor plus exact vault inventory

One module returns immutable normalized records. It handles the closed supported
syntax, masks false-positive regions, and delegates persistence to the existing
compiler transaction. Accepted.

## 3. Final Decision

Create a focused parser/resolver with these contracts:

```python
@dataclass(frozen=True)
class AuthoredEndpoint:
    entity_type: Literal["vault_note", "vault_asset", "tag"]
    canonical_key: str
    display_name: str

@dataclass(frozen=True)
class AuthoredRelation:
    source: AuthoredEndpoint
    target: AuthoredEndpoint
    relation_type: Literal[
        "links_to", "embeds", "tagged_with", "property_ref"
    ]
    source_span_ids: tuple[str, ...]

def extract_authored_topology(
    *,
    vault_root: Path,
    source_path: Path,
    text: str,
    visible_inventory: VaultInventory,
    source_spans: Sequence[SourceSpan],
) -> tuple[AuthoredRelation, ...]:
    ...
```

The inventory includes visible note/asset paths and Markdown aliases. Target
resolution returns exactly one canonical endpoint or `None`.

Normalization:

- strip pipe display text;
- strip `#heading` and `^block` fragments from endpoint identity;
- remove embed size decorations;
- normalize separators and vault-relative paths;
- case handling follows the exact filesystem inventory, not an invented global
  lowercase identity;
- normalize tags to one leading-free tag key while preserving nested `/`.

Mask fenced code, inline code, and comments before body extraction. Parse YAML
separately. Frontmatter wikilinks create `property_ref`; `tags` create
`tagged_with`; `aliases` only populate the resolver inventory.

## 4. Implementation Pseudocode

```python
def resolve_target(raw, source_path, inventory):
    target = strip_display_fragment_and_size(raw)
    if is_external(target) or escapes_root(target) or is_hidden(target):
        return None
    candidates = [
        inventory.exact_root(target),
        inventory.exact_relative(source_path.parent, target),
        inventory.unique_name_or_stem(target),
        inventory.unique_alias(target),
    ]
    for candidate in candidates:
        if candidate.is_exactly_one:
            return candidate.endpoint
        if candidate.is_ambiguous:
            return None
    return None

def extract(...):
    yaml_data, body = split_frontmatter(text)
    safe_body = mask_code_and_comments(body)
    refs = parse_closed_body_syntax(safe_body)
    refs += parse_closed_frontmatter_syntax(yaml_data)
    return sorted(set(resolve_or_drop(ref) for ref in refs if resolved))
```

Exact existing source spans may be attached where matching is deterministic.
Their absence does not convert authored structural presence into extracted KNU
support.
