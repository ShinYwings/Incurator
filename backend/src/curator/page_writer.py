"""Page I/O utilities: frontmatter parsing, page writing, index/log updates.

This module handles the structural bookkeeping that does NOT need the LLM:
- Writing validated markdown pages to disk
- Parsing and updating YAML frontmatter
- Stripping LLM response noise (code fences, preamble)
- Rebuilding index.md from the current wiki/ contents
- Appending new entries to log.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from . import config as cfg
from . import constants as consts


# ---------------------------------------------------------------------------
# Frontmatter parsing
# ---------------------------------------------------------------------------


@dataclass
class ParsedPage:
    """A wiki page split into frontmatter and body."""

    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    is_invalid: bool = False
    invalid_error: str = ""

    def to_markdown(self) -> str:
        """Serialize back to a markdown string with YAML frontmatter."""
        if not self.frontmatter:
            return self.body
        fm_yaml = yaml.safe_dump(
            self.frontmatter,
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        ).strip()
        return f"---\n{fm_yaml}\n---\n\n{self.body.strip()}\n"


def parse_page(content: str) -> ParsedPage:
    """Split a markdown string into frontmatter + body."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", content, re.DOTALL)
    if not match:
        return ParsedPage(frontmatter={}, body=content)
    fm_text = match.group(1)
    body = match.group(2)
    try:
        fm = yaml.safe_load(fm_text) or {}
        if not isinstance(fm, dict):
            fm = {}
    except yaml.YAMLError as e:
        # Generic fallback repair for any unquoted wikilinks or wikilink lists in frontmatter
        lines = []
        for line in fm_text.splitlines():
            if ":" in line and "[[" in line and "]]" in line:
                key, rest = line.split(":", 1)
                links = re.findall(r"\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]", rest)
                if links:
                    if len(links) == 1 and rest.strip().startswith("[[") and rest.strip().endswith("]]"):
                        # Single wikilink: e.g. parent_source: [[01_Contexts/CTX-abc]]
                        line = f"{key}: '[[{links[0]}]]'"
                    else:
                        # Multiple wikilinks: e.g. dependencies: [[02_Atoms/ATM-abc]], [[02_Atoms/ATM-def]]
                        quoted_links = ", ".join(f"'[[{link}]]'" for link in links)
                        line = f"{key}: [{quoted_links}]"
            lines.append(line)
        fm_text_repaired = "\n".join(lines)
        try:
            fm = yaml.safe_load(fm_text_repaired) or {}
            if not isinstance(fm, dict):
                fm = {}
        except yaml.YAMLError:
            fm = {}
            return ParsedPage(frontmatter=fm, body=body, is_invalid=True, invalid_error=str(e))
    return ParsedPage(frontmatter=fm, body=body)


def read_page(path: Path) -> ParsedPage | None:
    """Read and parse a wiki page from disk. Returns None if missing."""
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return parse_page(content)


def extract_wikilink_targets(text: str) -> list[str]:
    """Return wikilink targets from markdown body text, without aliases."""
    targets: list[str] = []
    for raw in re.findall(r"\[\[([^\]]+?)\]\]", text or ""):
        target = raw.split("|", 1)[0].strip()
        if target:
            targets.append(target)
    return targets


def extract_relation_targets(body: str, *, prefix: str = "") -> list[str]:
    """Return wikilink targets listed in the terminal `## Relations` section."""
    match = re.search(
        r"(?ims)^##\s+Relations\s*$\n(?P<section>.*?)(?=^##\s+|\Z)",
        body or "",
    )
    if not match:
        return []
    targets = extract_wikilink_targets(match.group("section"))
    if prefix:
        targets = [target for target in targets if target.startswith(prefix)]
    return targets


# ---------------------------------------------------------------------------
# LLM response cleanup
# ---------------------------------------------------------------------------


def strip_llm_noise(text: str) -> str:
    """Remove common LLM response artifacts from raw output.

    - Leading/trailing ```markdown or ``` fences
    - Explanatory preamble like 'Here is the page:'
    - Trailing commentary after the last frontmatter block
    """
    text = text.strip()

    # Some CLI adapters occasionally wrap the answer in a tool-call looking
    # prefix before the markdown fence, e.g. `update_topic(...)```markdown`.
    # If a fenced markdown page with frontmatter exists anywhere, trust that
    # inner page and discard the wrapper.
    embedded_fence = re.search(
        r"```(?:markdown|md|ya?ml)?\s*\n(---\s*\n.*?\n---\s*\n?.*?)\n```",
        text,
        re.DOTALL,
    )
    if embedded_fence:
        text = embedded_fence.group(1).strip()
    else:
        yamlish_fence = re.search(
            r"```(?:markdown|md|ya?ml)?\s*\n((?:id|type):\s+.*?\n---\s*\n?.*?)\n```",
            text,
            re.DOTALL,
        )
        if yamlish_fence:
            text = yamlish_fence.group(1).strip()

    # Remove outer code fences
    fence_match = re.match(
        r"^```(?:markdown|md|ya?ml)?\s*\n(.*?)\n```\s*$", text, re.DOTALL
    )
    if fence_match:
        text = fence_match.group(1).strip()

    # Some CLIs stream a page as ```yaml + markdown body, or emit two
    # complete pages in one response. Keep the first frontmatter page.
    text = re.sub(r"^```(?:markdown|md|ya?ml)?\s*\n(?=---\s*\n)", "", text, count=1)

    # Remove common preambles (only if they appear before the first ---)
    preamble_patterns = [
        r"^Here (?:is|'s) the (?:updated |new )?(?:markdown )?page:?\s*\n+",
        r"^Here (?:is|'s) the (?:updated |new )?page:?\s*\n+",
        r"^Sure[,.]?\s*here.*?:\s*\n+",
        r"^Okay[,.]?\s*here.*?:\s*\n+",
    ]
    for pattern in preamble_patterns:
        text = re.sub(pattern, "", text, count=1, flags=re.IGNORECASE)

    embedded_frontmatter = re.search(r"---\s*\n(?=id:\s+)", text)
    if embedded_frontmatter and embedded_frontmatter.start() > 0:
        text = text[embedded_frontmatter.start():].strip()

    if re.match(r"^---\s*\n", text):
        duplicate = re.search(r"\n```(?:markdown|md|ya?ml)?\s*\n---\s*\n", text)
        if duplicate:
            text = text[: duplicate.start()].rstrip()
        text = re.sub(r"\n```\s*$", "", text).strip()
    elif re.match(r"^(id|type):\s+", text):
        # LLMs sometimes omit the opening YAML delimiter but include the
        # closing one. Coerce this common near-miss into valid frontmatter so
        # layer contract enforcement can overwrite trusted fields.
        text = f"---\n{text}"

    return text.strip()


# ---------------------------------------------------------------------------
# Wikilink extraction
# ---------------------------------------------------------------------------


WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]*)?\]\]")

_VALID_CURATOR_LAYERS = frozenset(
    [consts.LAYER_L1, consts.LAYER_L2, consts.LAYER_L3, consts.LAYER_L4]
)
_LAYER_DIR_RE = re.compile(r"^\d{2}_")


def sanitize_wikilinks(content: str) -> str:
    """Remove wikilinks with placeholder IDs or non-existent curator layer paths.

    Strips links like [[03_Collections/...]], [[02_Atoms/ATM-...]],
    [[04_Resources/...]], and empty layer links such as [[01_Contexts/]].
    Leaves non-curator vault links untouched.
    """
    def _is_bad(inner: str) -> bool:
        target = inner.split("|", 1)[0].strip().lstrip("/")
        if "..." in target:
            return True
        if "/" in target:
            layer, rest = target.split("/", 1)
            if _LAYER_DIR_RE.match(layer) and layer not in _VALID_CURATOR_LAYERS:
                return True
            if layer in _VALID_CURATOR_LAYERS and not rest.strip().removesuffix(".md"):
                return True
        return False

    result = re.sub(
        r"\[\[([^\]]*)\]\]",
        lambda m: "" if _is_bad(m.group(1)) else m.group(0),
        content,
    )
    result = re.sub(r"(?m)^[ \t]*[-*+][ \t]*\n", "", result)
    return result


def extract_wikilinks(content: str) -> list[str]:
    """Find all [[wikilinks]] in a page. Returns the link targets (no brackets).

    E.g. '[[karpathy]] and [[entities/openai]]' → ['karpathy', 'entities/openai']
    """
    return [m.group(1).strip() for m in WIKILINK_RE.finditer(content)]


# ---------------------------------------------------------------------------
# Page writing
# ---------------------------------------------------------------------------


def write_page(path: Path, content: str) -> None:
    """Write a page to disk, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Ensure trailing newline
    if not content.endswith("\n"):
        content += "\n"
    path.write_text(content, encoding="utf-8")


def ensure_frontmatter_fields(page: ParsedPage, required: dict[str, Any]) -> ParsedPage:
    """Ensure the page has these frontmatter fields, adding defaults if missing.

    Does not overwrite existing values.
    """
    for key, default_value in required.items():
        if key not in page.frontmatter:
            page.frontmatter[key] = default_value
    return page


# ---------------------------------------------------------------------------
# index.md rebuild
# ---------------------------------------------------------------------------


INDEX_HEADER = """---
title: "Curator Index"
type: index
updated: {today}
---

# .curator/index.md — DAG Routing Table

> Auto-maintained by the Curator engine. Lists all pages by layer.
> Rebuilt after every ingest. DO NOT edit manually.
>
> Pipeline: L1 Collection & Summarization → L2 Selection & Atomization
>           → L3 Structuring & Value Addition → L4 Placement & Staging

"""


def _list_pages_in(directory: Path) -> list[tuple[str, str]]:
    """Return a sorted list of (slug, title) tuples for every .md page in
    the directory, skipping dotfiles.
    """
    if not directory.exists():
        return []
    out = []
    for page_path in sorted(directory.glob("*.md")):
        if page_path.name.startswith("."):
            continue
        parsed = read_page(page_path)
        title = page_path.stem
        if parsed and isinstance(parsed.frontmatter.get("title"), str):
            title = parsed.frontmatter["title"]
        out.append((page_path.stem, title))
    return out


def rebuild_index(paths: cfg.WikiPaths, today: str) -> None:
    """Rebuild .curator/index.md from the current Collections/ contents."""
    contexts    = _list_pages_in(paths.contexts)
    atoms       = _list_pages_in(paths.atoms)
    concepts    = _list_pages_in(paths.concepts)
    exhibitions = _list_pages_in(paths.exhibitions)

    lines = [INDEX_HEADER.format(today=today)]

    def _section(title: str, layer: str, pages: list[tuple[str, str]]) -> None:
        lines.append(f"## {title}\n")
        if not pages:
            lines.append("*No pages yet.*\n")
        else:
            for slug, page_title in pages:
                lines.append(f"- [[{layer}/{slug}|{page_title}]]")
            lines.append("")
        lines.append("")

    _section("L1 — Contexts (Collection & Summarization)",    consts.LAYER_L1,    contexts)
    _section("L2 — Atoms (Selection & Atomization)",          consts.LAYER_L2,       atoms)
    _section("L3 — Concepts (Structuring & Value Addition)",  consts.LAYER_L3,    concepts)
    _section("L4 — Exhibitions (Placement & Staging)",        consts.LAYER_L4, exhibitions)

    lines.append("---\n")
    lines.append(
        f"**Stats:** {len(contexts)} contexts · {len(atoms)} atoms · "
        f"{len(concepts)} concepts · {len(exhibitions)} exhibitions\n"
    )

    paths.index.parent.mkdir(parents=True, exist_ok=True)
    paths.index.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# log.md append
# ---------------------------------------------------------------------------


def append_log_entry(
    paths: cfg.WikiPaths,
    today: str,
    action: str,
    title: str,
    bullets: list[str],
) -> None:
    """Append a new entry to log.md.

    Format:
        ## [YYYY-MM-DD] action | title
        - bullet 1
        - bullet 2
    """
    import re
    import datetime

    if not paths.log.exists():
        paths.log.parent.mkdir(parents=True, exist_ok=True)
        paths.log.write_text(
            '---\ntitle: "Curator Log"\ntype: log\n---\n\n# .curator/log.md — Hash Registry\n\n',
            encoding="utf-8",
        )

    existing = paths.log.read_text(encoding="utf-8")
    if not existing.endswith("\n"):
        existing += "\n"
    if not existing.endswith("\n\n"):
        existing += "\n"

    entry_lines = [f"## [{today}] {action} | {title}", ""]
    for bullet in bullets:
        entry_lines.append(f"- {bullet}")
    entry_lines.append("")

    full_log = existing + "\n".join(entry_lines) + "\n"

    try:
        config = cfg.load_config(paths)
        retention = config.get("curate", {}).get("log_retention_days", 30)
    except Exception:
        retention = 30

    if retention:
        first_match = re.search(r"^##\s*\[", full_log, re.M)
        if first_match:
            header = full_log[:first_match.start()]
            body = full_log[first_match.start():]

            entry_starts = list(re.finditer(r"^##\s*\[(\d{4}-\d{2}-\d{2})\]", body, re.M))
            valid_entries = []
            today_dt = datetime.date.today()
            cutoff_dt = today_dt - datetime.timedelta(days=retention)

            for i, match in enumerate(entry_starts):
                date_str = match.group(1)
                try:
                    entry_dt = datetime.date.fromisoformat(date_str)
                except ValueError:
                    entry_dt = today_dt

                if entry_dt >= cutoff_dt:
                    start = match.start()
                    end = entry_starts[i + 1].start() if i + 1 < len(entry_starts) else len(body)
                    valid_entries.append(body[start:end].strip() + "\n")

            full_log = header.rstrip() + "\n\n" + "\n".join(valid_entries)
            if not full_log.endswith("\n"):
                full_log += "\n"

    paths.log.write_text(full_log, encoding="utf-8")



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def today_iso() -> str:
    """YYYY-MM-DD for the current local date."""
    return date.today().isoformat()
