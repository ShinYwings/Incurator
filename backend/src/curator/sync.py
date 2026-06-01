"""Deductive verification engine for the incurator v0.1.0 DAG.

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
from . import constants as consts

import json
import re
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Set

from . import config as cfg
from . import constants as consts
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


def _body_without_frontmatter(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].lstrip("\n")
    return text


def _hash_file_content(path: Path) -> str:
    """Hash markdown body content, excluding YAML frontmatter."""
    body = _body_without_frontmatter(path.read_text(encoding="utf-8"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _frontmatter_content_hash(path: Path) -> str | None:
    page = page_writer.read_page(path)
    if not page:
        return None
    value = page.frontmatter.get("content_hash")
    return str(value).strip() if value else None


def _find_changed_nodes(paths: cfg.WikiPaths) -> list[str]:
    """Return DAG node IDs whose body hash differs from frontmatter content_hash."""
    changed: list[str] = []
    for layer_dir, prefix in (
        (paths.contexts, f"{consts.PREFIX_L1}-"),
        (paths.atoms, f"{consts.PREFIX_L2}-"),
        (paths.concepts, f"{consts.PREFIX_L3}-"),
        (paths.exhibitions, f"{consts.PREFIX_L4}-"),
    ):
        if not layer_dir.exists():
            continue
        for md_path in sorted(layer_dir.glob(f"{prefix}*.md")):
            expected = _frontmatter_content_hash(md_path)
            if not expected or expected != _hash_file_content(md_path):
                changed.append(md_path.stem)
    return changed


def run_incremental_sync(paths: cfg.WikiPaths, client, config: dict) -> dict:
    """Fast v0.2.1 sync path: skip LLM verification when body hashes match."""
    changed = _find_changed_nodes(paths)
    affected = set(changed)
    if changed:
        try:
            from .ingest_orchestrator import _expand_downstream_via_sql

            affected = _expand_downstream_via_sql(paths, changed)
        except Exception:
            affected = set(changed)
    update_all_page_hashes(paths)
    finalize_routing_tables(paths)
    return {
        "mode": "incremental",
        "changed_nodes": changed,
        "affected_nodes": sorted(affected),
        "llm_required": bool(changed),
    }


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
        (f"{consts.PREFIX_L1}-", consts.LAYER_L1),
        (f"{consts.PREFIX_L2}-", consts.LAYER_L2),
        (f"{consts.PREFIX_L3}-", consts.LAYER_L3),
        (f"{consts.PREFIX_L4}-", consts.LAYER_L4),
    ):
        if node_id.startswith(prefix):
            return subdir
    return None


def _layer_for_id(node_id: str) -> Optional[str]:
    """Map an ID prefix to its layer name."""
    for prefix, layer in (
        (f"{consts.PREFIX_L1}-", consts.TYPE_L1),
        (f"{consts.PREFIX_L2}-", consts.TYPE_L2),
        (f"{consts.PREFIX_L3}-", consts.TYPE_L3),
        (f"{consts.PREFIX_L4}-", consts.TYPE_L4),
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
    for target in page_writer.extract_relation_targets(page.body, prefix=f"{consts.LAYER_L2}/"):
        atom_id = target.rsplit("/", 1)[-1]
        if atom_id.startswith(f"{consts.PREFIX_L2}-") and atom_id not in atom_ids:
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

    for md_path in sorted(exh_dir.glob(f"{consts.PREFIX_L4}-*.md")):
        exh_id = md_path.stem
        if callbacks:
            callbacks.on_node_check(exh_id)
        fm = _read_fm(paths, exh_id)
        if fm is None:
            gaps.append(VerificationGap(consts.TYPE_L4, exh_id, "Exhibition file unreadable."))
            continue

        con_ids = _fm_links(fm, "core_concepts")
        if not con_ids:
            gaps.append(VerificationGap(consts.TYPE_L4, exh_id, "core_concepts is empty or missing."))

        for con_id in con_ids:
            con_page = _read_node_page(paths, con_id)
            if con_page is None:
                gaps.append(VerificationGap(
                    consts.TYPE_L3, con_id,
                    f"Referenced by {exh_id} but page does not exist."
                ))
                continue

            atm_ids = _concept_atom_ids(paths, con_id)
            if not atm_ids:
                gaps.append(VerificationGap(consts.TYPE_L3, con_id, "Relations is empty or missing Atom links."))

            for atm_id in atm_ids:
                atm_fm = _read_fm(paths, atm_id)
                if atm_fm is None:
                    gaps.append(VerificationGap(
                        consts.TYPE_L2, atm_id,
                        f"Referenced by {con_id} but page does not exist."
                    ))
                    continue

                parent_links = _fm_links(atm_fm, "parent_source")
                for ctx_id in parent_links:
                    if not ctx_id.startswith(f"{consts.PREFIX_L1}-"):
                        continue
                    if _read_fm(paths, ctx_id) is None:
                        gaps.append(VerificationGap(
                            consts.TYPE_L1, ctx_id,
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

    if layer == consts.TYPE_L2:
        for ctx_id in _fm_links(fm, "parent_source"):
            if not ctx_id.startswith(f"{consts.PREFIX_L1}-"):
                continue
            if _read_fm(paths, ctx_id) is None:
                gaps.append(VerificationGap(
                    consts.TYPE_L1, ctx_id,
                    f"parent_source of {node_id} does not exist."
                ))

    elif layer == consts.TYPE_L3:
        for atm_id in _concept_atom_ids(paths, node_id):
            if not atm_id.startswith(f"{consts.PREFIX_L2}-"):
                continue
            if _read_fm(paths, atm_id) is None:
                gaps.append(VerificationGap(
                    consts.TYPE_L2, atm_id,
                    f"Dependency of {node_id} does not exist."
                ))
            else:
                gaps.extend(_trace_upstream(paths, atm_id, callbacks=callbacks))

    elif layer == consts.TYPE_L4:
        for con_id in _fm_links(fm, "core_concepts"):
            if not con_id.startswith(f"{consts.PREFIX_L3}-"):
                continue
            if _read_fm(paths, con_id) is None:
                gaps.append(VerificationGap(
                    consts.TYPE_L3, con_id,
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
    if layer == consts.TYPE_L1:
        search_dirs = [(consts.LAYER_L2, f"{consts.PREFIX_L2}-", "parent_source")]
    elif layer == consts.TYPE_L2:
        search_dirs = [(consts.LAYER_L3, f"{consts.PREFIX_L3}-", "relations")]
    elif layer == consts.TYPE_L3:
        search_dirs = [(consts.LAYER_L4, f"{consts.PREFIX_L4}-", "core_concepts")]
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
    for md_path in sorted(paths.concepts.glob(f"{consts.PREFIX_L3}-*.md")):
        if atom_id in _concept_atom_ids(paths, md_path.stem):
            found.append(md_path.stem)
    return found


def downstream_exhibitions_for_concept(paths: cfg.WikiPaths, concept_id: str) -> list[str]:
    """Return EXH IDs whose core_concepts include concept_id."""
    if not paths.exhibitions.exists():
        return []
    found: list[str] = []
    for md_path in sorted(paths.exhibitions.glob(f"{consts.PREFIX_L4}-*.md")):
        fm = _read_fm(paths, md_path.stem)
        if fm and concept_id in _fm_links(fm, "core_concepts"):
            found.append(md_path.stem)
    return found


def downstream_atoms_for_context(paths: cfg.WikiPaths, context_id: str) -> list[str]:
    """Return ATM IDs whose parent_source points to context_id."""
    if not paths.atoms.exists():
        return []
    found: list[str] = []
    for md_path in sorted(paths.atoms.glob(f"{consts.PREFIX_L2}-*.md")):
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
        if not con_id.startswith(f"{consts.PREFIX_L3}-"):
            return
        if (paths.concepts / f"{con_id}.md").exists():
            concept_ids.add(con_id)
        for exh_id in downstream_exhibitions_for_concept(paths, con_id):
            exhibition_ids.add(exh_id)

    def add_atom(atom_id: str) -> None:
        if not atom_id.startswith(f"{consts.PREFIX_L2}-"):
            return
        for con_id in downstream_concepts_for_atom(paths, atom_id):
            add_concept(con_id)

    for ref in node_refs:
        node_id = _node_id_from_ref(ref)
        layer = _layer_for_id(node_id)
        if layer == consts.TYPE_L4:
            if (paths.exhibitions / f"{node_id}.md").exists():
                exhibition_ids.add(node_id)
        elif layer == consts.TYPE_L3:
            add_concept(node_id)
        elif layer == consts.TYPE_L2:
            add_atom(node_id)
        elif layer == consts.TYPE_L1:
            for atom_id in downstream_atoms_for_context(paths, node_id):
                add_atom(atom_id)

    return concept_ids, exhibition_ids


def _body_atom_ids(page: page_writer.ParsedPage) -> list[str]:
    atom_ids: list[str] = []
    for target in page_writer.extract_wikilink_targets(page.body):
        target = target.removesuffix(".md")
        if target.startswith(f"{consts.LAYER_L2}/"):
            atom_id = target.rsplit("/", 1)[-1]
            if atom_id.startswith(f"{consts.PREFIX_L2}-") and atom_id not in atom_ids:
                atom_ids.append(atom_id)
    return atom_ids


def _body_context_ids(page: page_writer.ParsedPage) -> list[str]:
    context_ids: list[str] = []
    for target in page_writer.extract_wikilink_targets(page.body):
        target = target.removesuffix(".md")
        if target.startswith(f"{consts.LAYER_L1}/"):
            context_id = target.rsplit("/", 1)[-1]
            if context_id.startswith(f"{consts.PREFIX_L1}-") and context_id not in context_ids:
                context_ids.append(context_id)
    return context_ids


def _body_concept_paths(page: page_writer.ParsedPage) -> list[str]:
    concept_paths: list[str] = []
    for target in page_writer.extract_wikilink_targets(page.body):
        target = target.removesuffix(".md")
        if target.startswith(f"{consts.LAYER_L3}/"):
            concept_id = target.rsplit("/", 1)[-1]
            if concept_id.startswith(f"{consts.PREFIX_L3}-") and target not in concept_paths:
                concept_paths.append(target)
    return concept_paths


def repair_structural_gaps(paths: cfg.WikiPaths, gaps: list[VerificationGap], callbacks: Optional[SyncCallbacks] = None) -> int:
    """Apply deterministic DAG repairs for gaps with unambiguous local evidence."""
    modified = 0
    for gap in gaps:
        if callbacks:
            callbacks.on_node_check(gap.node_id)
        if gap.layer == consts.TYPE_L3 and "Relations is empty" in gap.message:
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
            relations = "\n".join(f"[[{consts.LAYER_L2}/{atom_id}]]" for atom_id in atom_ids)
            page.body = f"{page.body.rstrip()}\n\n## Relations\n{relations}\n"
            con_path.write_text(page.to_markdown(), encoding="utf-8")
            modified += 1
            if callbacks:
                callbacks.on_node_repair(gap.node_id, message="Restored missing ## Relations section")

        elif gap.layer == consts.TYPE_L4 and "core_concepts is empty" in gap.message:
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
                    concept_path = f"{consts.LAYER_L3}/{con_id}"
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

        # Filter out blocked concepts upfront; fire callbacks before parallel dispatch
        eligible: list[Path] = []
        for con_md in concept_files:
            if con_md.stem in blocked_node_ids:
                continue
            if callbacks:
                callbacks.on_node_check(con_md.stem)
            eligible.append(con_md)

        def _verify_one_concept(con_md: Path) -> tuple[dict, VerificationGap | None]:
            fm = _read_fm(paths, con_md.stem)
            if fm is None:
                return {}, None
            atm_ids = _concept_atom_ids(paths, con_md.stem)
            if not atm_ids:
                return {}, None
            if any(aid in blocked_node_ids for aid in atm_ids):
                return {}, None
            fragments_content = ""
            for aid in atm_ids:
                ap = page_writer.read_page(paths.atoms / f"{aid}.md")
                if ap:
                    fragments_content += f"\n### Atom {aid}\n{ap.body[:_FRAGMENT_BODY_CHARS]}\n"
            if not fragments_content:
                return {}, None
            con_page = page_writer.read_page(con_md)
            if not con_page:
                return {}, None
            messages = prompts.build_theme_logic_verify_messages(
                theme_content=_body_for_logic_check(
                    con_page.body, _THEME_BODY_CHARS, relation_prefix=f"{consts.LAYER_L2}/",
                ),
                fragments_content=fragments_content,
                domain_context=domain_context,
            )
            try:
                response = client.chat(messages, temperature=0.1)
            except LLMError:
                return {}, None
            result = _parse_verify_response(response, con_md.stem)
            gap = None
            if not result.get("valid", True):
                gap = VerificationGap(
                    layer=consts.TYPE_L3,
                    node_id=con_md.stem,
                    message="Concept logic not fully derivable from its Atoms.",
                    reasoning=result.get("reasoning", response.strip()[:600]),
                )
            return result, gap

        sync_cfg = cfg.load_config(paths).get("sync", {})
        max_workers = int(sync_cfg.get("max_parallel_verifications", 4))
        # Local models (Ollama) process one request at a time — parallelism only
        # wastes threads. Detect via duck-typing to avoid a circular import.
        primary = getattr(client, "providers", [client])[0]
        if type(primary).__name__ == "OllamaClient":
            max_workers = 1

        if max_workers <= 1 or len(eligible) <= 1:
            for con_md in eligible:
                result, gap = _verify_one_concept(con_md)
                if result:
                    con_results.append(result)
                if gap:
                    gaps.append(gap)
        else:
            with ThreadPoolExecutor(max_workers=min(max_workers, len(eligible))) as executor:
                future_to_md = {executor.submit(_verify_one_concept, con_md): con_md
                                for con_md in eligible}
                for future in as_completed(future_to_md):
                    result, gap = future.result()
                    if result:
                        con_results.append(result)
                    if gap:
                        gaps.append(gap)

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
                        f"{_body_for_logic_check(cp.body, _THEME_CONTENT_CHARS, relation_prefix=f'{consts.LAYER_L2}/')}\n"
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
                    relation_prefix=f"{consts.LAYER_L3}/",
                ),
                themes_content=themes_content,
                concept_verification_summary=relevant_con_results or None,
                domain_context=domain_context,
            )
            try:
                response = client.chat(messages, temperature=0.1)
            except LLMError:
                continue

            result = _parse_verify_response(response, exh_md.stem)
            if not result.get("valid", True):
                gaps.append(VerificationGap(
                    layer=consts.TYPE_L4,
                    node_id=exh_md.stem,
                    message="Exhibition logic not fully derivable from its Concepts.",
                    reasoning=result.get("reasoning", response.strip()[:600]),
                ))

    return gaps


# ---------------------------------------------------------------------------
# Fix — regenerate pages with detected gaps
# ---------------------------------------------------------------------------


def _regenerate_concept(paths: cfg.WikiPaths, client, con_id: str) -> bool:
    """[DEPRECATED] Concept is updated from Exhibition via propagate_upstream_from_exhibition.
    Bottom-up regeneration from Atoms is disabled to respect EXH as Source of Truth.
    """
    return False


def _regenerate_exhibition(paths: cfg.WikiPaths, client, exh_id: str) -> bool:
    """[DEPRECATED] Exhibition is the Source of Truth. 
    Manual or Insight-driven updates are the only allowed paths for changing L4.
    """
    return False


def _rebuild_downstream_from_fixed_node(paths: cfg.WikiPaths, client, layer: str, node_id: str) -> int:
    """[DEPRECATED] Forward-rebuild is disabled. 
    Changes now flow Top-Down from Exhibition to lower layers.
    """
    return 0
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
            if gap.layer == consts.TYPE_L3:
                ok = _regenerate_concept(paths, client, gap.node_id)
            elif gap.layer == consts.TYPE_L4:
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



def apply_generative_backprop(paths, client, gaps, callbacks=None) -> list[str]:
    """Run generative backprop using the Multi-Agent architecture to extract insights and generate Atoms."""
    import backend.src.curator.backprop_agents as b_agents

    evaluator = b_agents.TimePerformanceEvaluator()
    extractor = b_agents.InsightExtractor()
    synthesizer = b_agents.AtomSynthesizer()
    clustering = b_agents.ConceptClusteringAgent()
    workspace = b_agents.WorkspaceController()

    t_total = evaluator.start_timer("Total Generative Backprop")

    new_atoms = []

    for gap in gaps:
        if gap.layer not in [consts.TYPE_L3, consts.TYPE_L4] or not gap.reasoning:
            print(f"Skipping gap {gap.node_id}: layer={gap.layer}, reasoning={bool(gap.reasoning)}")
            continue

        print(f"Checking gap {gap.node_id} reasoning: {gap.reasoning}")

        # Removed external/absent filter to capture any logical gap from manual edits

        if gap.layer == consts.TYPE_L3:
            md_path = paths.concepts / f"{gap.node_id}.md"
        else:
            md_path = paths.exhibitions / f"{gap.node_id}.md"

        if not md_path.exists():
            continue

        page = page_writer.read_page(md_path)
        if not page:
            continue

        t_extract = evaluator.start_timer(f"Extract Insight ({gap.node_id})")
        insight = extractor.extract(client, page.body, gap.reasoning)
        evaluator.record_time(f"Extract Insight ({gap.node_id})", t_extract)

        if not insight:
            continue

        t_synth = evaluator.start_timer(f"Synthesize Atom ({gap.node_id})")
        new_atom_id = synthesizer.synthesize(paths, client, insight, gap.node_id)
        evaluator.record_time(f"Synthesize Atom ({gap.node_id})", t_synth)

        if new_atom_id:
            # Quality check
            t_eval = evaluator.start_timer(f"Critic Eval ({new_atom_id})")
            is_valid = evaluator.evaluate_atom_quality(new_atom_id, insight)
            evaluator.record_time(f"Critic Eval ({new_atom_id})", t_eval)

            if is_valid:
                new_atoms.append(new_atom_id)
                workspace.commit_and_update_routing(paths, new_atom_id)

    if new_atoms:
        t_cluster = evaluator.start_timer("L3 Concept Clustering")
        clustering.recluster(paths, client, new_atoms)
        evaluator.record_time("L3 Concept Clustering", t_cluster)

    evaluator.record_time("Total Generative Backprop", t_total)

    # Let's print the performance report if anything was processed
    if new_atoms:
        from rich.console import Console
        console = Console()
        evaluator.report(console)

    return new_atoms

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
    contexts_updated: list[str] = field(default_factory=list)
    feedback_required: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    llm_calls: int = 0
    timings_ms: dict[str, int] = field(default_factory=dict)
    source_propagation_skipped: bool = False
    target_concepts: list[str] = field(default_factory=list)


def propagate_upstream_from_exhibition(
    paths: cfg.WikiPaths,
    client,
    exh_id: str = "",
    insight: str = "",
    propagate_sources: bool = True,
    previous_exh_content: str = "",
) -> PropagationResult:
    """Unified backpropagation (hybrid static + dynamic) from EXH or Insight down to CTX.

    Workflow:
      1. Source discovery: Read Exhibition (L4) OR use provided Insight string.
      2. Reconcile Concepts (L3): Static links + Semantic Search.
      3. Reconcile Atoms (L2) and Contexts (L1) by default. Insight backprop
         should be rare, so consistency is favored over latency. L1 updates
         must preserve source truth and record derived corrections separately.
    """
    from . import search
    from .llm import LLMError
    from . import ingest_llm as _ingest
    import time as _time

    started_total = _time.monotonic()

    result = PropagationResult(
        exh_id=exh_id, concepts_updated=[], atoms_updated=[], contexts_updated=[], feedback_required=[], errors=[]
    )
    today = page_writer.today_iso()

    exh_page = None
    if exh_id:
        exh_path = paths.exhibitions / f"{exh_id}.md"
        exh_page = page_writer.read_page(exh_path)
    
    if not exh_page and not insight:
        result.errors.append(f"No source of truth (Exhibition {exh_id} not found and no insight provided)")
        return result

    # Determine source text for search and static links
    source_text = insight
    static_con_ids = []
    
    if exh_page:
        source_text = exh_page.to_markdown()
        static_con_ids = _fm_links(exh_page.frontmatter, "core_concepts")

    def _added_text(before: str, after: str) -> str:
        if not before:
            return after
        parsed_before = page_writer.parse_page(before)
        if parsed_before.frontmatter:
            before = parsed_before.to_markdown()
        before_lines = set(line.strip() for line in before.splitlines() if line.strip())
        added = [
            line.strip()
            for line in after.splitlines()
            if line.strip() and line.strip() not in before_lines
        ]
        return "\n".join(added)

    target_text = _added_text(previous_exh_content, source_text)
    if len(target_text.strip()) < 80:
        target_text = insight or source_text

    def _tokens(text: str) -> set[str]:
        stop = {
            "about", "after", "also", "and", "are", "because", "been", "but",
            "can", "from", "have", "into", "not", "original", "paper",
            "source", "that", "the", "this", "with",
        }
        return {
            token.lower()
            for token in re.findall(r"[A-Za-z][A-Za-z0-9+-]*", text)
            if len(token) > 2 and token.lower() not in stop
        }

    target_tokens = _tokens(target_text)
    
    # --- Step 1: L3 (Concepts) ---
    started_concepts = _time.monotonic()
    # Dynamic discovery for Concepts
    dynamic_con_ids = []
    try:
        search_results = search.query(
            paths,
            target_text,
            mode="hybrid",
            limit=5,
            rerank=False,
        )
        for hit in search_results.hits:
            if hit.score > 0.8 and hit.full_path.startswith(f"{consts.LAYER_L3}/"):
                cid = hit.full_path.rsplit("/", 1)[-1].removesuffix(".md")
                dynamic_con_ids.append(cid)
    except Exception:
        pass

    all_con_ids = sorted(list(set(static_con_ids + dynamic_con_ids)))
    if previous_exh_content and all_con_ids:
        ranked_con_ids: list[tuple[int, str]] = []
        dynamic_set = set(dynamic_con_ids)
        for con_id in all_con_ids:
            if not con_id.startswith(f"{consts.PREFIX_L3}-"):
                continue
            con_page = page_writer.read_page(paths.concepts / f"{con_id}.md")
            if con_page is None:
                continue
            con_tokens = _tokens(con_page.to_markdown())
            overlap = len(target_tokens & con_tokens)
            if con_id in dynamic_set:
                overlap += 5
            if overlap > 0:
                ranked_con_ids.append((overlap, con_id))
        ranked_con_ids.sort(key=lambda item: (-item[0], item[1]))
        selected = [con_id for _score, con_id in ranked_con_ids[:5]]
        if selected:
            all_con_ids = selected
    result.target_concepts = list(all_con_ids)

    concept_originals: dict[str, str] = {}
    concept_pages: dict[str, page_writer.ParsedPage] = {}
    valid_con_ids: list[str] = []
    for con_id in all_con_ids:
        if not con_id.startswith(f"{consts.PREFIX_L3}-"): continue
        con_path = paths.concepts / f"{con_id}.md"
        con_page = page_writer.read_page(con_path)
        if con_page is None: continue # Could happen if search index is stale
        concept_pages[con_id] = con_page
        concept_originals[con_id] = con_page.to_markdown()
        valid_con_ids.append(con_id)

    def _apply_updated_concept(con_id: str, updated_con: str) -> bool:
        con_page = concept_pages.get(con_id)
        con_original = concept_originals.get(con_id, "")
        if con_page is None or not con_original:
            return False
        updated_con = page_writer.strip_llm_noise(updated_con)
        if not updated_con or updated_con.strip() == con_original.strip():
            return False
        updated_con_page = _drop_nested_frontmatter_body(page_writer.parse_page(updated_con))
        updated_con_page.frontmatter = _merge_immutable_frontmatter(
            con_page.frontmatter, updated_con_page.frontmatter, {"id", "type", "name", "domain", "confidence_score"}
        )
        updated_con_page.frontmatter["last_updated"] = today
        (paths.concepts / f"{con_id}.md").write_text(updated_con_page.to_markdown(), encoding="utf-8")
        if con_id not in result.concepts_updated:
            result.concepts_updated.append(con_id)
        return True

    batch_outputs: dict[str, str] = {}
    batch_succeeded = False
    batch_attempted = len(valid_con_ids) > 1
    if batch_attempted:
        messages = prompts.build_batch_concept_update_from_exhibition_messages(
            exh_id=exh_id or "Insight",
            exh_content=source_text,
            concept_pages=[(con_id, concept_originals[con_id]) for con_id in valid_con_ids],
            today=today,
        )
        try:
            result.llm_calls += 1
            raw_batch = client.chat(messages, json_mode=True, temperature=0.2)
            batch_data = json.loads(raw_batch)
            raw_items = batch_data.get("concepts", []) if isinstance(batch_data, dict) else []
            if not isinstance(raw_items, list):
                raise ValueError("batch response field `concepts` is not a list")
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                con_id = str(item.get("id", ""))
                changed = bool(item.get("changed"))
                markdown = str(item.get("markdown", ""))
                if con_id in concept_originals and changed and markdown.strip():
                    batch_outputs[con_id] = markdown
            batch_succeeded = True
            for con_id, updated_con in batch_outputs.items():
                _apply_updated_concept(con_id, updated_con)
        except Exception as exc:
            result.errors.append(f"Batch CON update failed; falling back to individual updates: {exc}")
            batch_outputs = {}
            batch_succeeded = False

    for con_id in valid_con_ids:
        con_original = concept_originals[con_id]
        if batch_succeeded:
            updated_con = batch_outputs.get(con_id, con_original)
        else:
            messages = prompts.build_concept_update_from_exhibition_messages(
                exh_id=exh_id or "Insight", exh_content=source_text, con_id=con_id, con_content=con_original, today=today
            )
            try:
                result.llm_calls += 1
                updated_con = client.chat(messages, temperature=0.2)
                _apply_updated_concept(con_id, updated_con)
            except LLMError as e:
                result.errors.append(f"CON {con_id} update failed: {e}")
                continue

        if con_id not in result.concepts_updated:
            continue

        if not propagate_sources:
            result.source_propagation_skipped = True
            continue

        # --- Step 2: L2 (Atoms) ---
        static_atm_ids = _concept_atom_ids(paths, con_id)
        
        # Dynamic discovery for Atoms within this Concept
        dynamic_atm_ids = []
        try:
            con_text = updated_con if result.concepts_updated and con_id in result.concepts_updated else con_original
            search_results = search.query(
                paths,
                con_text,
                mode="hybrid",
                limit=5,
                rerank=False,
            )
            for hit in search_results.hits:
                if hit.score > 0.8 and hit.full_path.startswith(f"{consts.LAYER_L2}/"):
                    aid = hit.full_path.rsplit("/", 1)[-1].removesuffix(".md")
                    dynamic_atm_ids.append(aid)
        except Exception:
            pass

        all_atm_ids = sorted(list(set(static_atm_ids + dynamic_atm_ids)))
        updated_con_content = updated_con if con_id in result.concepts_updated else con_original

        for atm_id in all_atm_ids:
            if not atm_id.startswith(f"{consts.PREFIX_L2}-"): continue
            atm_path = paths.atoms / f"{atm_id}.md"
            atm_page = page_writer.read_page(atm_path)
            if atm_page is None: continue

            atm_original = atm_page.to_markdown()
            atom_changed = False
            messages = prompts.build_atom_update_from_concept_messages(
                con_id=con_id, con_content=updated_con_content, atm_id=atm_id, atm_content=atm_original, today=today
            )
            try:
                result.llm_calls += 1
                updated_atm = client.chat(messages, temperature=0.1)
                updated_atm = page_writer.strip_llm_noise(updated_atm)
                if updated_atm and updated_atm.strip() != atm_original.strip():
                    updated_atm_page = page_writer.parse_page(updated_atm)
                    updated_atm_page.frontmatter = _merge_immutable_frontmatter(
                        atm_page.frontmatter, updated_atm_page.frontmatter,
                        {"id", "type", "parent_source", "source_path", "claim_type", "confidence_score", "contradicts", "is_verified_by_human", "is_flagged_for_agent"}
                    )
                    updated_atm_page.frontmatter["last_updated"] = today
                    atm_path.write_text(updated_atm_page.to_markdown(), encoding="utf-8")
                    result.atoms_updated.append(atm_id)
                    atom_changed = True
            except LLMError as e:
                result.errors.append(f"ATM {atm_id} update failed: {e}")
                continue

            # --- Step 3: L1 (Contexts) ---
            # Reconcile L1 Context for this updated Atom
            if not atom_changed:
                continue
            parent_source = atm_page.frontmatter.get("parent_source")
            ctx_id = None
            if parent_source:
                from . import query as _q
                try:
                    ctx_id = _q._node_path_from_target(str(parent_source)).rsplit("/", 1)[-1]
                except Exception: pass
            
            if not ctx_id:
                # Search for L1
                try:
                    ctx_results = search.query(paths, atm_original, scope="contexts", limit=1)
                    if ctx_results.hits and ctx_results.hits[0].score > 0.8:
                        ctx_id = ctx_results.hits[0].full_path.rsplit("/", 1)[-1].removesuffix(".md")
                except Exception: pass

            if ctx_id:
                ctx_path = paths.contexts / f"{ctx_id}.md"
                ctx_page = page_writer.read_page(ctx_path)
                if ctx_page:
                    ctx_original = ctx_page.to_markdown()
                    # Use the new prompt added to prompts.py
                    messages = prompts.build_context_update_from_atom_messages(
                        atm_id=atm_id, atm_content=atm_original, ctx_id=ctx_id, ctx_content=ctx_original, today=today
                    )
                    try:
                        result.llm_calls += 1
                        updated_ctx = client.chat(messages, temperature=0.1)
                        updated_ctx = page_writer.strip_llm_noise(updated_ctx)
                        if updated_ctx and updated_ctx.strip() != ctx_original.strip():
                            ctx_path.write_text(updated_ctx, encoding="utf-8")
                            result.contexts_updated.append(ctx_id)
                    except Exception: pass
            else:
                # No L1 found -> Feedback
                result.feedback_required.append({
                    "atom_id": atm_id,
                    "insight": "Knowledge updated without verified source provenance."
                })

    result.timings_ms["concepts"] = int((_time.monotonic() - started_concepts) * 1000)
    result.timings_ms["total"] = int((_time.monotonic() - started_total) * 1000)
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


# ---------------------------------------------------------------------------
# Forward propagation: CON (L3) -> EXH (L4)
# ---------------------------------------------------------------------------

def propagate_downstream_to_exhibition(paths: cfg.WikiPaths, client, exh_id: str) -> bool:
    """Forward propagation: update an EXH to incorporate changes from its L3 Concepts.
    Uses EXHIBITION_SMART_UPDATE_PROMPT to merge new info without overwriting human edits.
    """
    from .llm import LLMError
    
    exh_path = paths.exhibitions / f"{exh_id}.md"
    exh_page = page_writer.read_page(exh_path)
    if not exh_page:
        return False
    
    con_ids = _fm_links(exh_page.frontmatter, "core_concepts")
    if not con_ids:
        return False
    
    # 1. Gather current content of all referenced concepts
    concepts_content = ""
    for cid in con_ids:
        cp = page_writer.read_page(paths.concepts / f"{cid}.md")
        if cp:
            concepts_content += f"\n### {cid}\n{cp.body}\n"
    
    if not concepts_content:
        return False
        
    # 2. Trigger Smart Update
    today = page_writer.today_iso()
    messages = prompts.build_exhibition_refinement_messages(
        exh_id=exh_id,
        existing_body=exh_page.body,
        updates=f"Updated Supporting Concepts:\n{concepts_content}"
    )
    
    try:
        updated_body = client.chat(messages, temperature=0.2)
        updated_body = page_writer.strip_llm_noise(updated_body)
        
        if updated_body and updated_body.strip() != exh_page.body.strip():
            exh_page.body = updated_body
            exh_page.frontmatter["last_updated"] = today
            exh_path.write_text(exh_page.to_markdown(), encoding="utf-8")
            return True
    except LLMError:
        pass
        
    return False


def find_dirty_exhibitions(paths: cfg.WikiPaths) -> list[str]:
    """Find EXH IDs where referenced CONs are newer than the EXH itself."""
    dirty = []
    exh_dir = paths.exhibitions
    if not exh_dir.exists():
        return dirty
        
    for exh_file in sorted(exh_dir.glob("EXH-*.md")):
        exh_id = exh_file.stem
        exh_fm = _read_fm(paths, exh_id)
        if not exh_fm: continue
        
        exh_time = exh_fm.get("last_updated", "1970-01-01")
        con_ids = _fm_links(exh_fm, "core_concepts")
        
        is_dirty = False
        for cid in con_ids:
            con_fm = _read_fm(paths, cid)
            if con_fm and con_fm.get("last_updated", "1970-01-01") > exh_time:
                is_dirty = True
                break
        
        if is_dirty:
            dirty.append(exh_id)
            
    return dirty
