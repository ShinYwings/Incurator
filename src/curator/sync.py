"""Deductive verification engine for the InCurator v0.1.0 DAG.

Two entry points:

  run_mode_a(paths) → list[VerificationGap]
      Global reverse verification: walks all L4 Exhibitions back through
      L3 Concepts → L2 Atoms → L1 Contexts and flags any logical
      discontinuities (missing nodes, broken references).

  run_mode_b(paths, node_id) → list[VerificationGap]
      Targeted bidirectional propagation: from a given node (any layer),
      traces upstream to L1 and downstream to L4, collecting gaps.

Finalization:

  finalize_routing_tables(paths)
      Rebuilds index.md, ledger.md, log.md, and overview.md after any
      verification or update pass.
"""

from __future__ import annotations

import json
import re
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Set

from . import config as cfg
from . import db
from . import page_writer
from . import prompts


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


class SyncCallbacks:
    """Interface for progress reporting during sync operations."""

    def on_node_check(self, node_id: str):
        """Called before a node is verified."""
        pass

    def on_node_repair(self, node_id: str, rebuilt_count: int = 0, message: Optional[str] = None):
        """Called after a node has been successfully repaired."""
        pass


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class VerificationGap:
    """A logical discontinuity detected during verification."""
    layer: str       # 'context' | 'atom' | 'concept' | 'exhibition'
    node_id: str     # e.g. 'ATM-9f8e7d6c'
    message: str     # human-readable description of the gap
    reasoning: str = ""  # LLM explanation (Mode C only)


@dataclass
class SyncRepairResult:
    """Outcome of one automatic sync repair loop."""

    fixed: int = 0
    unfixable: int = 0
    rebuilt_downstream: int = 0
    fixed_nodes: list[str] = field(default_factory=list)
    needs_review: list[VerificationGap] = field(default_factory=list)

@dataclass
class ChangeReport:
    modified: list[str] = field(default_factory=list)  # wiki_path
    new: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    unchanged_count: int = 0

    def total_changes(self) -> int:
        return len(self.modified) + len(self.new) + len(self.deleted)


def calculate_hash(path: Path) -> str:
    """Calculate SHA256 of file content."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_for_changes(paths: cfg.WikiPaths) -> ChangeReport:
    """Compare live filesystem against DB hashes to find changed pages."""
    report = ChangeReport()
    db_hashes = db.get_page_hashes(paths.state_db)
    seen_in_fs: set[str] = set()

    for layer_dir in (paths.contexts, paths.atoms, paths.concepts, paths.exhibitions):
        if not layer_dir.exists():
            continue
        
        layer_name = layer_dir.name
        for md_path in layer_dir.glob("*.md"):
            rel_path = f"{layer_name}/{md_path.name}"
            seen_in_fs.add(rel_path)
            
            current_hash = calculate_hash(md_path)
            old_hash = db_hashes.get(rel_path)
            
            if old_hash is None:
                report.new.append(rel_path)
            elif old_hash != current_hash:
                report.modified.append(rel_path)
            else:
                report.unchanged_count += 1
    
    # Any hashes in DB but NOT in FS are deleted
    for rel_path in db_hashes:
        if rel_path not in seen_in_fs:
            report.deleted.append(rel_path)
            
    return report


def update_all_page_hashes(paths: cfg.WikiPaths):
    """Save current filesystem hashes to DB."""
    for layer_dir in (paths.contexts, paths.atoms, paths.concepts, paths.exhibitions):
        if not layer_dir.exists():
            continue
        layer_name = layer_dir.name
        for md_path in sorted(layer_dir.glob("*.md")):
            rel_path = f"{layer_name}/{md_path.name}"
            db.update_page_hash(paths.state_db, rel_path, calculate_hash(md_path))

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _id_from_link(link: str) -> str:
    """'[[02_Atoms/ATM-abc12345]]' -> 'ATM-abc12345'."""
    s = link.strip()
    if s.startswith("[[") and s.endswith("]]"):
        s = s[2:-2]
    if "|" in s:
        s = s.split("|", 1)[0]
    if s.endswith(".md"):
        s = s[:-3]
    return s.rsplit("/", 1)[-1].strip()


def _subdir_for_id(node_id: str) -> Optional[str]:
    """Map an ID prefix to its Collections subdirectory."""
    for prefix, subdir in (
        ("CTX-", "01_Contexts"),
        ("ATM-", "02_Atoms"),
        ("CON-", "03_Concepts"),
        ("EXH-", "04_Exhibitions"),
    ):
        if node_id.startswith(prefix):
            return subdir
    return None


def _layer_for_id(node_id: str) -> Optional[str]:
    """Map an ID prefix to its layer name."""
    for prefix, layer in (
        ("CTX-", "context"),
        ("ATM-", "atom"),
        ("CON-", "concept"),
        ("EXH-", "exhibition"),
    ):
        if node_id.startswith(prefix):
            return layer
    return None


def _read_fm(paths: cfg.WikiPaths, node_id: str) -> Optional[dict]:
    """Read frontmatter for a node by ID. Returns None if the page is missing."""
    subdir = _subdir_for_id(node_id)
    if subdir is None:
        return None
    page_path = paths.collections / subdir / f"{node_id}.md"
    if not page_path.exists():
        return None
    parsed = page_writer.read_page(page_path)
    return parsed.frontmatter if parsed else None


def _read_node_page(paths: cfg.WikiPaths, node_id: str) -> Optional[page_writer.ParsedPage]:
    """Read a node page by ID. Returns None if the page is missing."""
    subdir = _subdir_for_id(node_id)
    if subdir is None:
        return None
    return page_writer.read_page(paths.collections / subdir / f"{node_id}.md")


def _fm_links(fm: dict, field: str) -> list[str]:
    """Extract a list of node IDs from a frontmatter link field."""
    raw = fm.get(field, [])
    if isinstance(raw, str):
        raw = [raw]
    elif not isinstance(raw, list):
        return []
    return [_id_from_link(v) for v in raw if isinstance(v, str) and v]


def _concept_atom_ids(paths: cfg.WikiPaths, con_id: str) -> list[str]:
    """Read Concept → Atom edges from the Concept `## Relations` section."""
    page = _read_node_page(paths, con_id)
    if page is None:
        return []
    atom_ids: list[str] = []
    for target in page_writer.extract_relation_targets(page.body, prefix="02_Atoms/"):
        atom_id = target.rsplit("/", 1)[-1]
        if atom_id.startswith("ATM-") and atom_id not in atom_ids:
            atom_ids.append(atom_id)
    return atom_ids


# ---------------------------------------------------------------------------
# Mode A — Global reverse verification
# ---------------------------------------------------------------------------


def run_mode_a(paths: cfg.WikiPaths, callbacks: Optional[SyncCallbacks] = None) -> list[VerificationGap]:
    """Walk all EXH pages downward through CON → ATM → CTX, flag broken refs."""
    gaps: list[VerificationGap] = []
    exh_dir = paths.exhibitions
    if not exh_dir.exists():
        return gaps

    for md_path in sorted(exh_dir.glob("EXH-*.md")):
        exh_id = md_path.stem
        if callbacks:
            callbacks.on_node_check(exh_id)
        fm = _read_fm(paths, exh_id)
        if fm is None:
            gaps.append(VerificationGap("exhibition", exh_id, "Exhibition file unreadable."))
            continue

        con_ids = _fm_links(fm, "core_concepts")
        if not con_ids:
            gaps.append(VerificationGap("exhibition", exh_id, "core_concepts is empty or missing."))

        for con_id in con_ids:
            con_page = _read_node_page(paths, con_id)
            if con_page is None:
                gaps.append(VerificationGap(
                    "concept", con_id,
                    f"Referenced by {exh_id} but page does not exist."
                ))
                continue

            atm_ids = _concept_atom_ids(paths, con_id)
            if not atm_ids:
                gaps.append(VerificationGap("concept", con_id, "Relations is empty or missing Atom links."))

            for atm_id in atm_ids:
                atm_fm = _read_fm(paths, atm_id)
                if atm_fm is None:
                    gaps.append(VerificationGap(
                        "atom", atm_id,
                        f"Referenced by {con_id} but page does not exist."
                    ))
                    continue

                parent_links = _fm_links(atm_fm, "parent_source")
                for ctx_id in parent_links:
                    if not ctx_id.startswith("CTX-"):
                        continue
                    if _read_fm(paths, ctx_id) is None:
                        gaps.append(VerificationGap(
                            "context", ctx_id,
                            f"Referenced by {atm_id} as parent_source but page does not exist."
                        ))

    return gaps


# ---------------------------------------------------------------------------
# Mode B — Targeted bidirectional propagation
# ---------------------------------------------------------------------------


def _trace_upstream(paths: cfg.WikiPaths, node_id: str, callbacks: Optional[SyncCallbacks] = None) -> list[VerificationGap]:
    """Trace from node_id toward L1, verifying each upstream link."""
    gaps: list[VerificationGap] = []
    layer = _layer_for_id(node_id)
    if layer is None:
        return gaps
    
    if callbacks:
        callbacks.on_node_check(node_id)

    fm = _read_fm(paths, node_id)
    if fm is None:
        gaps.append(VerificationGap(layer, node_id, "Node page does not exist."))
        return gaps

    if layer == "atom":
        for ctx_id in _fm_links(fm, "parent_source"):
            if not ctx_id.startswith("CTX-"):
                continue
            if _read_fm(paths, ctx_id) is None:
                gaps.append(VerificationGap(
                    "context", ctx_id,
                    f"parent_source of {node_id} does not exist."
                ))

    elif layer == "concept":
        for atm_id in _concept_atom_ids(paths, node_id):
            if not atm_id.startswith("ATM-"):
                continue
            if _read_fm(paths, atm_id) is None:
                gaps.append(VerificationGap(
                    "atom", atm_id,
                    f"Dependency of {node_id} does not exist."
                ))
            else:
                gaps.extend(_trace_upstream(paths, atm_id, callbacks=callbacks))

    elif layer == "exhibition":
        for con_id in _fm_links(fm, "core_concepts"):
            if not con_id.startswith("CON-"):
                continue
            if _read_fm(paths, con_id) is None:
                gaps.append(VerificationGap(
                    "concept", con_id,
                    f"core_concepts entry in {node_id} does not exist."
                ))
            else:
                gaps.extend(_trace_upstream(paths, con_id, callbacks=callbacks))

    return gaps


def _trace_downstream(paths: cfg.WikiPaths, node_id: str, callbacks: Optional[SyncCallbacks] = None) -> list[VerificationGap]:
    """Scan all collections for nodes that reference node_id, then go deeper."""
    gaps: list[VerificationGap] = []
    layer = _layer_for_id(node_id)
    if layer is None:
        return gaps
    
    if callbacks:
        callbacks.on_node_check(node_id)

    # Determine which layer(s) might reference this node and what field they use
    if layer == "context":
        search_dirs = [("02_Atoms", "ATM-", "parent_source")]
    elif layer == "atom":
        search_dirs = [("03_Concepts", "CON-", "relations")]
    elif layer == "concept":
        search_dirs = [("04_Exhibitions", "EXH-", "core_concepts")]
    else:
        return gaps  # exhibitions have no downstream within the DAG

    for subdir, prefix, field in search_dirs:
        d = paths.collections / subdir
        if not d.exists():
            continue
        for md_path in sorted(d.glob(f"{prefix}*.md")):
            child_id = md_path.stem
            child_fm = _read_fm(paths, child_id)
            if child_fm is None:
                continue
            if field == "relations":
                refs = _concept_atom_ids(paths, child_id)
            else:
                refs = _fm_links(child_fm, field)
            if node_id in refs:
                gaps.extend(_trace_downstream(paths, child_id, callbacks=callbacks))

    return gaps


def downstream_concepts_for_atom(paths: cfg.WikiPaths, atom_id: str) -> list[str]:
    """Return CON IDs whose Relations include atom_id."""
    if not paths.concepts.exists():
        return []
    found: list[str] = []
    for md_path in sorted(paths.concepts.glob("CON-*.md")):
        if atom_id in _concept_atom_ids(paths, md_path.stem):
            found.append(md_path.stem)
    return found


def downstream_exhibitions_for_concept(paths: cfg.WikiPaths, concept_id: str) -> list[str]:
    """Return EXH IDs whose core_concepts include concept_id."""
    if not paths.exhibitions.exists():
        return []
    found: list[str] = []
    for md_path in sorted(paths.exhibitions.glob("EXH-*.md")):
        fm = _read_fm(paths, md_path.stem)
        if fm and concept_id in _fm_links(fm, "core_concepts"):
            found.append(md_path.stem)
    return found


def downstream_atoms_for_context(paths: cfg.WikiPaths, context_id: str) -> list[str]:
    """Return ATM IDs whose parent_source points to context_id."""
    if not paths.atoms.exists():
        return []
    found: list[str] = []
    for md_path in sorted(paths.atoms.glob("ATM-*.md")):
        fm = _read_fm(paths, md_path.stem)
        if fm and context_id in _fm_links(fm, "parent_source"):
            found.append(md_path.stem)
    return found


def _node_id_from_ref(ref: str) -> str:
    """Return a node ID from a node ID, page path, or wikilink-ish reference."""
    stem = _id_from_link(ref)
    if stem.endswith(".md"):
        stem = stem[:-3]
    return stem


def _logical_scope_for_nodes(paths: cfg.WikiPaths, node_refs: list[str] | None) -> tuple[set[str], set[str]]:
    """Return Concept/Exhibition IDs affected by the given changed nodes.

    The scope is endpoint-aware:
    - dirty EXH: verify only that EXH
    - dirty CON: verify the CON and downstream EXHs, if any
    - dirty ATM: verify downstream CONs and their downstream EXHs
    - dirty CTX: verify downstream ATMs → CONs → EXHs

    Empty/None means global Mode C verification.
    """
    concept_ids: set[str] = set()
    exhibition_ids: set[str] = set()
    if not node_refs:
        return concept_ids, exhibition_ids

    def add_concept(con_id: str) -> None:
        if not con_id.startswith("CON-"):
            return
        if (paths.concepts / f"{con_id}.md").exists():
            concept_ids.add(con_id)
        for exh_id in downstream_exhibitions_for_concept(paths, con_id):
            exhibition_ids.add(exh_id)

    def add_atom(atom_id: str) -> None:
        if not atom_id.startswith("ATM-"):
            return
        for con_id in downstream_concepts_for_atom(paths, atom_id):
            add_concept(con_id)

    for ref in node_refs:
        node_id = _node_id_from_ref(ref)
        layer = _layer_for_id(node_id)
        if layer == "exhibition":
            if (paths.exhibitions / f"{node_id}.md").exists():
                exhibition_ids.add(node_id)
        elif layer == "concept":
            add_concept(node_id)
        elif layer == "atom":
            add_atom(node_id)
        elif layer == "context":
            for atom_id in downstream_atoms_for_context(paths, node_id):
                add_atom(atom_id)

    return concept_ids, exhibition_ids


def _body_atom_ids(page: page_writer.ParsedPage) -> list[str]:
    atom_ids: list[str] = []
    for target in page_writer.extract_wikilink_targets(page.body):
        target = target.removesuffix(".md")
        if target.startswith("02_Atoms/"):
            atom_id = target.rsplit("/", 1)[-1]
            if atom_id.startswith("ATM-") and atom_id not in atom_ids:
                atom_ids.append(atom_id)
    return atom_ids


def _body_context_ids(page: page_writer.ParsedPage) -> list[str]:
    context_ids: list[str] = []
    for target in page_writer.extract_wikilink_targets(page.body):
        target = target.removesuffix(".md")
        if target.startswith("01_Contexts/"):
            context_id = target.rsplit("/", 1)[-1]
            if context_id.startswith("CTX-") and context_id not in context_ids:
                context_ids.append(context_id)
    return context_ids


def _body_concept_paths(page: page_writer.ParsedPage) -> list[str]:
    concept_paths: list[str] = []
    for target in page_writer.extract_wikilink_targets(page.body):
        target = target.removesuffix(".md")
        if target.startswith("03_Concepts/"):
            concept_id = target.rsplit("/", 1)[-1]
            if concept_id.startswith("CON-") and target not in concept_paths:
                concept_paths.append(target)
    return concept_paths


def repair_structural_gaps(paths: cfg.WikiPaths, gaps: list[VerificationGap], callbacks: Optional[SyncCallbacks] = None) -> int:
    """Apply deterministic DAG repairs for gaps with unambiguous local evidence."""
    modified = 0
    for gap in gaps:
        if callbacks:
            callbacks.on_node_check(gap.node_id)
        if gap.layer == "concept" and "Relations is empty" in gap.message:
            con_path = paths.concepts / f"{gap.node_id}.md"
            page = page_writer.read_page(con_path)
            if page is None:
                continue
            page = _drop_nested_frontmatter_body(page)
            atom_ids = [
                atom_id for atom_id in _body_atom_ids(page)
                if (paths.atoms / f"{atom_id}.md").exists()
            ]
            if not atom_ids:
                continue
            relations = "\n".join(f"[[02_Atoms/{atom_id}]]" for atom_id in atom_ids)
            page.body = f"{page.body.rstrip()}\n\n## Relations\n{relations}\n"
            con_path.write_text(page.to_markdown(), encoding="utf-8")
            modified += 1
            if callbacks:
                callbacks.on_node_repair(gap.node_id, message="Restored missing ## Relations section")

        elif gap.layer == "exhibition" and "core_concepts is empty" in gap.message:
            exh_path = paths.exhibitions / f"{gap.node_id}.md"
            page = page_writer.read_page(exh_path)
            if page is None:
                continue
            page = _drop_nested_frontmatter_body(page)
            concept_paths = _body_concept_paths(page)
            atom_ids = _body_atom_ids(page)
            for context_id in _body_context_ids(page):
                for atom_id in downstream_atoms_for_context(paths, context_id):
                    if atom_id not in atom_ids:
                        atom_ids.append(atom_id)
            for atom_id in atom_ids:
                for con_id in downstream_concepts_for_atom(paths, atom_id):
                    concept_path = f"03_Concepts/{con_id}"
                    if concept_path not in concept_paths:
                        concept_paths.append(concept_path)
            concept_paths = [
                concept_path for concept_path in concept_paths
                if (paths.concepts / f"{concept_path.rsplit('/', 1)[-1]}.md").exists()
            ]
            if not concept_paths:
                continue
            page.frontmatter["core_concepts"] = concept_paths
            exh_path.write_text(page.to_markdown(), encoding="utf-8")
            modified += 1

    return modified


def repair_nested_frontmatter(paths: cfg.WikiPaths, callbacks: Optional[SyncCallbacks] = None) -> int:
    """Remove duplicate YAML frontmatter blocks accidentally embedded in bodies."""
    modified = 0
    for layer_dir in (paths.contexts, paths.atoms, paths.concepts, paths.exhibitions):
        if not layer_dir.exists():
            continue
        for md_path in sorted(layer_dir.glob("*.md")):
            page = page_writer.read_page(md_path)
            if page is None:
                continue
            
            if callbacks:
                callbacks.on_node_check(md_path.stem)
            
            before = page.body
            page = _drop_nested_frontmatter_body(page)
            if page.body != before:
                md_path.write_text(page.to_markdown(), encoding="utf-8")
                modified += 1
                if callbacks:
                    callbacks.on_node_repair(md_path.stem, message="Removed nested frontmatter from body")
    return modified


def run_mode_b(
    paths: cfg.WikiPaths, node_id: str, callbacks: Optional[SyncCallbacks] = None
) -> list[VerificationGap]:
    """Bidirectional verification centred on node_id."""
    gaps: list[VerificationGap] = []
    gaps.extend(_trace_upstream(paths, node_id, callbacks=callbacks))
    gaps.extend(_trace_downstream(paths, node_id, callbacks=callbacks))
    # Deduplicate while preserving order
    seen: set[tuple[str, str, str]] = set()
    unique: list[VerificationGap] = []
    for g in gaps:
        key = (g.layer, g.node_id, g.message)
        if key not in seen:
            seen.add(key)
            unique.append(g)
    return unique


# ---------------------------------------------------------------------------
# Mode C — LLM logical deduction verification
# ---------------------------------------------------------------------------

_THEME_BODY_CHARS = 6000
_FRAGMENT_BODY_CHARS = 2400
_THEME_CONTENT_CHARS = 4000
_CONCEPT_BATCH_SIZE = 3
_EXHIBITION_BATCH_SIZE = 2


def _body_for_logic_check(body: str, max_chars: int, *, relation_prefix: str = "") -> str:
    """Trim a page body for LLM verification without truncating DAG Relations."""
    if len(body) <= max_chars:
        return body
    trimmed = body[:max_chars].rsplit("\n", 1)[0].rstrip()
    targets = page_writer.extract_relation_targets(body, prefix=relation_prefix)
    if targets and "## Relations" not in trimmed:
        relations = "\n".join(f"[[{target}]]" for target in targets)
        trimmed = f"{trimmed}\n\n## Relations\n{relations}"
    return trimmed


def _merge_immutable_frontmatter(
    original_fm: dict,
    regenerated_fm: dict,
    immutable_keys: set[str],
) -> dict:
    merged = dict(regenerated_fm)
    for key in immutable_keys:
        if key in original_fm:
            merged[key] = original_fm[key]
    return merged


def _drop_nested_frontmatter_body(page: page_writer.ParsedPage) -> page_writer.ParsedPage:
    """Remove an accidental second frontmatter block from an LLM page body."""
    body = page.body.lstrip()
    if body.startswith("---\n"):
        nested = page_writer.parse_page(body)
        if nested.frontmatter or nested.body != body:
            page.body = nested.body
        else:
            match = re.match(r"^---\s*\n.*?\n---\s*\n?(.*)$", body, re.DOTALL)
            if match:
                page.body = match.group(1)
            else:
                heading = re.search(r"(?m)^#\s+", body)
                if heading:
                    page.body = body[heading.start():]
    return page


def _parse_verify_response(raw: str, node_id: str) -> dict:
    """Parse a JSON verify response. Returns {"id": node_id, "valid": bool, ...}.

    Falls back to text heuristic if JSON is malformed (e.g. older model or local LLM).
    """
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines and lines[-1].strip() == "```" else lines[1:])
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "valid" in data:
            data["id"] = node_id
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    # Fallback: plain-text "VALID"/"INVALID" heuristic
    valid = text.upper().startswith("VALID")
    result: dict = {"id": node_id, "valid": valid}
    if not valid:
        result["reasoning"] = text[:600]
    return result


def run_mode_c(
    paths: cfg.WikiPaths,
    client,
    *,
    blocked_node_ids: set[str] | None = None,
    target_node_ids: list[str] | None = None,
    max_themes: int = 20,
    max_curations: int = 10,
    callbacks: Optional[SyncCallbacks] = None,
) -> list[VerificationGap]:
    """LLM logical deduction verification — the core purpose of wiki sync.

    Phase 1: each CON — can it be logically derived from its Atom Relations?
    Phase 2: each EXH - can it be logically derived from its CON core_concepts?

    Gaps are returned with `reasoning` populated from the LLM response.
    """
    from .llm import LLMError

    # Load Curator persona for domain-context injection
    curator_persona = cfg.get_curator_persona(cfg.load_config(paths))
    domain_context = curator_persona.get("text", "")

    gaps: list[VerificationGap] = []
    blocked_node_ids = blocked_node_ids or set()
    target_concept_ids, target_exhibition_ids = _logical_scope_for_nodes(paths, target_node_ids)
    targeted = bool(target_node_ids)

    # Phase 1 — CON ← ATMs
    # con_results collects JSON verification outcomes to pass as context to Phase 2.
    con_results: list[dict] = []
    if paths.concepts.exists():
        if targeted:
            concept_files = [
                paths.concepts / f"{con_id}.md"
                for con_id in sorted(target_concept_ids)
                if (paths.concepts / f"{con_id}.md").exists()
            ]
        else:
            concept_files = sorted(paths.concepts.glob("CON-*.md"))[:max_themes]
        for con_md in concept_files:
            if con_md.stem in blocked_node_ids:
                continue
            if callbacks:
                callbacks.on_node_check(con_md.stem)
            fm = _read_fm(paths, con_md.stem)
            if fm is None:
                continue
            atm_ids = _concept_atom_ids(paths, con_md.stem)
            if not atm_ids:
                continue
            if any(aid in blocked_node_ids for aid in atm_ids):
                continue

            fragments_content = ""
            for aid in atm_ids:
                ap = page_writer.read_page(paths.atoms / f"{aid}.md")
                if ap:
                    fragments_content += f"\n### Atom {aid}\n{ap.body[:_FRAGMENT_BODY_CHARS]}\n"
            if not fragments_content:
                continue

            con_page = page_writer.read_page(con_md)
            if not con_page:
                continue

            messages = prompts.build_theme_logic_verify_messages(
                theme_content=_body_for_logic_check(
                    con_page.body,
                    _THEME_BODY_CHARS,
                    relation_prefix="02_Atoms/",
                ),
                fragments_content=fragments_content,
                domain_context=domain_context,
            )
            try:
                response = client.chat(messages, thinking=False, temperature=0.1)
            except LLMError:
                continue

            result = _parse_verify_response(response, con_md.stem)
            con_results.append(result)
            if not result.get("valid", True):
                gaps.append(VerificationGap(
                    layer="concept",
                    node_id=con_md.stem,
                    message="Concept logic not fully derivable from its Atoms.",
                    reasoning=result.get("reasoning", response.strip()[:600]),
                ))

    # Phase 2 — EXH ← CONs (if L4 exists)
    # Phase 1 con_results are passed as context so the LLM can factor in CON validity.
    if paths.exhibitions.exists():
        if targeted:
            exhibition_files = [
                paths.exhibitions / f"{exh_id}.md"
                for exh_id in sorted(target_exhibition_ids)
                if (paths.exhibitions / f"{exh_id}.md").exists()
            ]
        else:
            exhibition_files = sorted(paths.exhibitions.glob("EXH-*.md"))[:max_curations]
        if not exhibition_files:
            return gaps
        for exh_md in exhibition_files:
            if exh_md.stem in blocked_node_ids:
                continue
            if callbacks:
                callbacks.on_node_check(exh_md.stem)
            fm = _read_fm(paths, exh_md.stem)
            if fm is None:
                continue
            con_ids = _fm_links(fm, "core_concepts")
            if not con_ids:
                continue
            if any(cid in blocked_node_ids for cid in con_ids):
                continue

            themes_content = ""
            for cid in con_ids:
                cp = page_writer.read_page(paths.concepts / f"{cid}.md")
                if cp:
                    themes_content += (
                        f"\n### Concept {cid}\n"
                        f"{_body_for_logic_check(cp.body, _THEME_CONTENT_CHARS, relation_prefix='02_Atoms/')}\n"
                    )
            if not themes_content:
                continue

            exh_page = page_writer.read_page(exh_md)
            if not exh_page:
                continue

            # Pass only Phase 1 results relevant to this EXH's core_concepts
            relevant_con_results = [r for r in con_results if r.get("id") in con_ids]
            messages = prompts.build_curation_logic_verify_messages(
                curation_content=_body_for_logic_check(
                    exh_page.body,
                    _THEME_BODY_CHARS,
                    relation_prefix="03_Concepts/",
                ),
                themes_content=themes_content,
                concept_verification_summary=relevant_con_results or None,
                domain_context=domain_context,
            )
            try:
                response = client.chat(messages, thinking=False, temperature=0.1)
            except LLMError:
                continue

            result = _parse_verify_response(response, exh_md.stem)
            if not result.get("valid", True):
                gaps.append(VerificationGap(
                    layer="exhibition",
                    node_id=exh_md.stem,
                    message="Exhibition logic not fully derivable from its Concepts.",
                    reasoning=result.get("reasoning", response.strip()[:600]),
                ))

    return gaps


# ---------------------------------------------------------------------------
# Fix — regenerate pages with detected gaps
# ---------------------------------------------------------------------------


def _regenerate_concept(paths: cfg.WikiPaths, client, con_id: str) -> bool:
    """Mode C fix: rewrite a CON page using its existing Atom Relations."""
    from .llm import LLMError

    fm = _read_fm(paths, con_id)
    if fm is None:
        return False
    atm_ids = _concept_atom_ids(paths, con_id)
    if not atm_ids:
        return False

    atoms_content = ""
    for aid in atm_ids:
        ap = page_writer.read_page(paths.atoms / f"{aid}.md")
        if ap:
            atoms_content += f"\n### {aid}\n{ap.body}\n"
    if not atoms_content:
        return False

    today = page_writer.today_iso()
    messages = prompts.build_theme_page_messages(
        theme_id=con_id,
        name=fm.get("name", ""),
        domain=fm.get("domain", ""),
        fragment_ids=atm_ids,
        fragments_content=atoms_content,
        today=today,
    )
    try:
        response = client.chat(messages, thinking=False, temperature=0.3)
    except LLMError:
        return False

    response = page_writer.strip_llm_noise(response)
    regenerated = _drop_nested_frontmatter_body(page_writer.parse_page(response))
    regenerated.frontmatter = _merge_immutable_frontmatter(
        fm,
        regenerated.frontmatter,
        {
            "id",
            "type",
            "name",
            "domain",
            "confidence_score",
        },
    )
    regenerated.frontmatter.pop("dependencies", None)
    regenerated.frontmatter["last_updated"] = today
    relations = "\n".join(f"[[02_Atoms/{aid}]]" for aid in atm_ids)
    if "## Relations" in regenerated.body:
        regenerated.body = re.sub(
            r"(?is)(^##\s+Relations\s*$\n?).*?\Z",
            rf"\1\n{relations}\n",
            regenerated.body,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        regenerated.body = f"{regenerated.body.rstrip()}\n\n## Relations\n{relations}\n"

    con_path = paths.concepts / f"{con_id}.md"
    con_path.write_text(regenerated.to_markdown(), encoding="utf-8")
    return True


def _regenerate_exhibition(paths: cfg.WikiPaths, client, exh_id: str) -> bool:
    """Mode C fix: rewrite an EXH page using its existing CON core_concepts."""
    from .llm import LLMError

    fm = _read_fm(paths, exh_id)
    if fm is None:
        return False
    con_ids = _fm_links(fm, "core_concepts")
    if not con_ids:
        return False

    concepts_content = ""
    for cid in con_ids:
        cp = page_writer.read_page(paths.concepts / f"{cid}.md")
        if cp:
            concepts_content += f"\n### {cid}\n{cp.body}\n"
    if not concepts_content:
        return False

    today = page_writer.today_iso()
    try:
        confidence = float(fm.get("confidence_score", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5

    messages = prompts.build_curation_page_messages(
        curation_id=exh_id,
        topic=fm.get("topic", ""),
        theme_ids=con_ids,
        themes_content=concepts_content,
        confidence=confidence,
        today=today,
    )
    try:
        response = client.chat(messages, thinking=False, temperature=0.3)
    except LLMError:
        return False

    response = page_writer.strip_llm_noise(response)
    regenerated = _drop_nested_frontmatter_body(page_writer.parse_page(response))
    regenerated.frontmatter = _merge_immutable_frontmatter(
        fm,
        regenerated.frontmatter,
        {"id", "type", "topic", "core_concepts", "confidence_score"},
    )
    regenerated.frontmatter["last_updated"] = today

    exh_path = paths.exhibitions / f"{exh_id}.md"
    exh_path.write_text(regenerated.to_markdown(), encoding="utf-8")
    return True


def _rebuild_downstream_from_fixed_node(paths: cfg.WikiPaths, client, layer: str, node_id: str) -> int:
    """Forward-rebuild only downstream endpoints affected by a repaired node."""
    rebuilt = 0
    if layer == "exhibition":
        return 0
    if layer == "concept":
        for exh_id in downstream_exhibitions_for_concept(paths, node_id):
            if _regenerate_exhibition(paths, client, exh_id):
                rebuilt += 1
        return rebuilt
    if layer == "atom":
        for con_id in downstream_concepts_for_atom(paths, node_id):
            if _regenerate_concept(paths, client, con_id):
                rebuilt += 1
            rebuilt += _rebuild_downstream_from_fixed_node(paths, client, "concept", con_id)
        return rebuilt
    if layer == "context":
        for atm_id in downstream_atoms_for_context(paths, node_id):
            # L2 regeneration from L1/source is handled by wiki add today; mark
            # downstream rebuild through existing CON/EXH nodes when present.
            rebuilt += _rebuild_downstream_from_fixed_node(paths, client, "atom", atm_id)
        return rebuilt
    return 0


def fix_gaps(
    paths: cfg.WikiPaths,
    client,
    gaps: list[VerificationGap],
) -> SyncRepairResult:
    """Attempt to fix detected gaps and rebuild affected downstream endpoints.

    Mode C logical gaps (gap.reasoning set) → regenerate the affected page via LLM.
    Mode A/B structural gaps → leave for structural safe repair / review.
    """
    result = SyncRepairResult()
    seen: set[tuple[str, str]] = set()

    for gap in gaps:
        key = (gap.layer, gap.node_id)
        if key in seen:
            continue
        seen.add(key)

        if gap.reasoning:  # Mode C — logical deduction gap
            if gap.layer == "concept":
                ok = _regenerate_concept(paths, client, gap.node_id)
            elif gap.layer == "exhibition":
                ok = _regenerate_exhibition(paths, client, gap.node_id)
            else:
                ok = False
            if ok:
                result.fixed += 1
                result.fixed_nodes.append(gap.node_id)
                result.rebuilt_downstream += _rebuild_downstream_from_fixed_node(
                    paths, client, gap.layer, gap.node_id
                )
            else:
                result.unfixable += 1
                result.needs_review.append(gap)
        else:
            result.unfixable += 1
            result.needs_review.append(gap)

    return result


def repair_logical_gaps(
    paths: cfg.WikiPaths,
    client,
    *,
    blocked_node_ids: set[str] | None = None,
    target_node_ids: list[str] | None = None,
    max_iterations: int = 2,
    callbacks: Optional[SyncCallbacks] = None,
) -> tuple[list[VerificationGap], SyncRepairResult]:
    """Verify, repair logical gaps, and re-verify up to max_iterations."""
    aggregate = SyncRepairResult()
    remaining = run_mode_c(
        paths,
        client,
        blocked_node_ids=blocked_node_ids,
        target_node_ids=target_node_ids,
        callbacks=callbacks,
    )
    for _ in range(max_iterations):
        if not remaining:
            break
        repair = fix_gaps(paths, client, remaining)
        for node_id in repair.fixed_nodes:
            if callbacks:
                callbacks.on_node_repair(node_id, rebuilt_count=0) # rebuilt is handled in aggregate or fix_gaps but here we just mark the fixed one
        
        aggregate.fixed += repair.fixed
        aggregate.unfixable += repair.unfixable
        aggregate.rebuilt_downstream += repair.rebuilt_downstream
        aggregate.fixed_nodes.extend(repair.fixed_nodes)
        aggregate.needs_review.extend(repair.needs_review)
        if repair.fixed == 0 and repair.rebuilt_downstream == 0:
            break
        remaining = run_mode_c(
            paths,
            client,
            blocked_node_ids=blocked_node_ids,
            target_node_ids=target_node_ids,
            callbacks=callbacks,
        )
    aggregate.needs_review = remaining
    return remaining, aggregate


# ---------------------------------------------------------------------------
# Backward propagation — agent correction: EXH → CON → ATM
# ---------------------------------------------------------------------------


@dataclass
class PropagationResult:
    """Result of an upstream propagation pass triggered by an EXH correction."""
    exh_id: str
    concepts_updated: list[str]
    atoms_updated: list[str]
    errors: list[str]


def propagate_upstream_from_exhibition(
    paths: cfg.WikiPaths,
    client,
    exh_id: str,
) -> PropagationResult:
    """Propagate a human-corrected Exhibition upstream through CON → ATM.

    Flow:
      1. Read the corrected EXH page.
      2. For each CON in core_concepts:
         a. Call LLM to update the CON to be consistent with the corrected EXH.
         b. Write the updated CON.
         c. For each ATM in that CON's Relations:
            i.  Call LLM to update the ATM if it contradicts the updated CON.
            ii. Write the ATM only if the content actually changed.
      3. Return PropagationResult with lists of updated IDs.

    Non-fatal: individual LLM failures are captured in errors, not raised.
    """
    from .llm import LLMError

    result = PropagationResult(
        exh_id=exh_id, concepts_updated=[], atoms_updated=[], errors=[]
    )
    today = page_writer.today_iso()

    exh_path = paths.exhibitions / f"{exh_id}.md"
    exh_page = page_writer.read_page(exh_path)
    if exh_page is None:
        result.errors.append(f"Exhibition {exh_id} not found")
        return result

    exh_content = exh_page.to_markdown()
    con_ids = _fm_links(exh_page.frontmatter, "core_concepts")

    for con_id in con_ids:
        if not con_id.startswith("CON-"):
            continue
        con_path = paths.concepts / f"{con_id}.md"
        con_page = page_writer.read_page(con_path)
        if con_page is None:
            result.errors.append(f"Concept {con_id} not found")
            continue

        con_original = con_page.to_markdown()

        # Step 2a: update CON to be consistent with corrected EXH
        messages = prompts.build_concept_update_from_exhibition_messages(
            exh_id=exh_id,
            exh_content=exh_content,
            con_id=con_id,
            con_content=con_original,
            today=today,
        )
        try:
            updated_con = client.chat(messages, thinking=False, temperature=0.2)
        except LLMError as e:
            result.errors.append(f"CON {con_id} update failed: {e}")
            continue

        updated_con = page_writer.strip_llm_noise(updated_con)
        if not updated_con or updated_con.strip() == con_original.strip():
            continue  # LLM returned unchanged — skip

        updated_con_page = _drop_nested_frontmatter_body(page_writer.parse_page(updated_con))
        updated_con_page.frontmatter = _merge_immutable_frontmatter(
            con_page.frontmatter,
            updated_con_page.frontmatter,
            {"id", "type", "name", "domain", "confidence_score"},
        )
        updated_con_page.frontmatter["last_updated"] = today
        con_path.write_text(updated_con_page.to_markdown(), encoding="utf-8")
        result.concepts_updated.append(con_id)

        # Step 2c: update each ATM that this CON references
        updated_con_page = page_writer.read_page(con_path)
        atm_ids = _concept_atom_ids(paths, con_id)
        updated_con_content = updated_con_page.to_markdown() if updated_con_page else updated_con

        for atm_id in atm_ids:
            if not atm_id.startswith("ATM-"):
                continue
            atm_path = paths.atoms / f"{atm_id}.md"
            atm_page = page_writer.read_page(atm_path)
            if atm_page is None:
                result.errors.append(f"Atom {atm_id} not found")
                continue

            atm_original = atm_page.to_markdown()
            messages = prompts.build_atom_update_from_concept_messages(
                con_id=con_id,
                con_content=updated_con_content,
                atm_id=atm_id,
                atm_content=atm_original,
                today=today,
            )
            try:
                updated_atm = client.chat(messages, thinking=False, temperature=0.1)
            except LLMError as e:
                result.errors.append(f"ATM {atm_id} update failed: {e}")
                continue

            updated_atm = page_writer.strip_llm_noise(updated_atm)
            if not updated_atm or updated_atm.strip() == atm_original.strip():
                continue  # unchanged — skip

            updated_atm_page = page_writer.parse_page(updated_atm)
            updated_atm_page.frontmatter = _merge_immutable_frontmatter(
                atm_page.frontmatter,
                updated_atm_page.frontmatter,
                {
                    "id",
                    "type",
                    "parent_source",
                    "source_path",
                    "claim_type",
                    "confidence_score",
                    "contradicts",
                    "is_verified_by_human",
                    "is_flagged_for_agent",
                },
            )
            updated_atm_page.frontmatter["last_updated"] = today
            atm_path.write_text(updated_atm_page.to_markdown(), encoding="utf-8")
            result.atoms_updated.append(atm_id)

    return result


# ---------------------------------------------------------------------------
# Finalization — rebuild routing tables
# ---------------------------------------------------------------------------


def finalize_routing_tables(paths: cfg.WikiPaths) -> None:
    """Rebuild index.md, ledger.md, log.md, and overview.md."""
    today = page_writer.today_iso()
    page_writer.rebuild_index(paths, today)
    page_writer.append_log_entry(
        paths,
        today,
        "sync",
        "Deductive verification pass",
        ["Routing tables rebuilt by wiki sync"],
    )
