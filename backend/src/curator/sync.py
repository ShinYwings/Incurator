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
from typing import Optional

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



def _find_changed_nodes(paths: cfg.WikiPaths) -> list[str]:
    """Return DAG node IDs whose file hash differs from the DB page-hash store."""
    db_hashes = db.get_page_hashes(paths.state_db)
    changed: list[str] = []
    for layer_dir, prefix in (
        (paths.contexts, f"{consts.PREFIX_L1}-"),
        (paths.atoms, f"{consts.PREFIX_L2}-"),
        (paths.concepts, f"{consts.PREFIX_L3}-"),
        (paths.synthesis, f"{consts.PREFIX_L4}-"),
    ):
        if not layer_dir.exists():
            continue
        layer_name = layer_dir.name
        for md_path in sorted(layer_dir.glob(f"{prefix}*.md")):
            rel_path = f"{layer_name}/{md_path.name}"
            stored = db_hashes.get(rel_path)
            if stored is None or stored != calculate_hash(md_path):
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

    for layer_dir in (paths.contexts, paths.atoms, paths.concepts, paths.synthesis):
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


def update_all_page_hashes(
    paths: cfg.WikiPaths,
    *,
    layer_dirs: tuple[Path, ...] | None = None,
) -> None:
    """Save current filesystem hashes for all or selected generated layers."""
    selected_dirs = layer_dirs or (
        paths.contexts,
        paths.atoms,
        paths.concepts,
        paths.synthesis,
    )
    current_paths: set[str] = set()
    for layer_dir in selected_dirs:
        if not layer_dir.exists():
            continue
        layer_name = layer_dir.name
        for md_path in sorted(layer_dir.glob("*.md")):
            rel_path = f"{layer_name}/{md_path.name}"
            current_paths.add(rel_path)
            db.update_page_hash(paths.state_db, rel_path, calculate_hash(md_path))
    selected_prefixes = tuple(f"{layer_dir.name}/" for layer_dir in selected_dirs)
    for rel_path in set(db.get_page_hashes(paths.state_db)) - current_paths:
        if rel_path.startswith(selected_prefixes):
            db.delete_page_hash(paths.state_db, rel_path)

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
    """Walk all SYN pages downward through CON -> ATM -> CTX, flag broken refs."""
    gaps: list[VerificationGap] = []
    exh_dir = paths.synthesis
    if not exh_dir.exists():
        return gaps

    for md_path in sorted(exh_dir.glob(f"{consts.PREFIX_L4}-*.md")):
        exh_id = md_path.stem
        if callbacks:
            callbacks.on_node_check(exh_id)
        fm = _read_fm(paths, exh_id)
        if fm is None:
            gaps.append(VerificationGap(consts.TYPE_L4, exh_id, "Synthesis file unreadable."))
            continue

        con_ids = _fm_links(fm, "concept_ids")
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
        for con_id in _fm_links(fm, "concept_ids"):
            if not con_id.startswith(f"{consts.PREFIX_L3}-"):
                continue
            if _read_fm(paths, con_id) is None:
                gaps.append(VerificationGap(
                    consts.TYPE_L3, con_id,
                    f"concept_ids entry in {node_id} does not exist."
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
        search_dirs = [(consts.LAYER_L4, f"{consts.PREFIX_L4}-", "concept_ids")]
    else:
        return gaps  # synthesis nodes have no downstream within the DAG

    for subdir, prefix, fm_field in search_dirs:
        d = paths.collections / subdir
        if not d.exists():
            continue
        for md_path in sorted(d.glob(f"{prefix}*.md")):
            child_id = md_path.stem
            child_fm = _read_fm(paths, child_id)
            if child_fm is None:
                continue
            if fm_field == "relations":
                refs = _concept_atom_ids(paths, child_id)
            else:
                refs = _fm_links(child_fm, fm_field)
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
    """Return SYN IDs whose concept_ids include concept_id."""
    if not paths.synthesis.exists():
        return []
    found: list[str] = []
    for md_path in sorted(paths.synthesis.glob(f"{consts.PREFIX_L4}-*.md")):
        fm = _read_fm(paths, md_path.stem)
        if fm and concept_id in _fm_links(fm, "concept_ids"):
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
    """Return Concept/Synthesis IDs affected by the given changed nodes.

    The scope is endpoint-aware:
    - dirty SYN: verify only that SYN
    - dirty CON: verify the CON and downstream SYN nodes, if any
    - dirty ATM: verify downstream CONs and their downstream SYN nodes
    - dirty CTX: verify downstream ATMs -> CONs -> SYNs

    Empty/None means global Mode C verification.
    """
    concept_ids: set[str] = set()
    synthesis_ids: set[str] = set()
    if not node_refs:
        return concept_ids, synthesis_ids

    def add_concept(con_id: str) -> None:
        if not con_id.startswith(f"{consts.PREFIX_L3}-"):
            return
        if (paths.concepts / f"{con_id}.md").exists():
            concept_ids.add(con_id)
        for syn_id in downstream_exhibitions_for_concept(paths, con_id):
            synthesis_ids.add(syn_id)

    def add_atom(atom_id: str) -> None:
        if not atom_id.startswith(f"{consts.PREFIX_L2}-"):
            return
        for con_id in downstream_concepts_for_atom(paths, atom_id):
            add_concept(con_id)

    for ref in node_refs:
        node_id = _node_id_from_ref(ref)
        layer = _layer_for_id(node_id)
        if layer == consts.TYPE_L4:
            if (paths.synthesis / f"{node_id}.md").exists():
                synthesis_ids.add(node_id)
        elif layer == consts.TYPE_L3:
            add_concept(node_id)
        elif layer == consts.TYPE_L2:
            add_atom(node_id)
        elif layer == consts.TYPE_L1:
            for atom_id in downstream_atoms_for_context(paths, node_id):
                add_atom(atom_id)

    return concept_ids, synthesis_ids


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

        elif gap.layer == consts.TYPE_L4 and "concept_ids is empty" in gap.message:
            exh_path = paths.synthesis / f"{gap.node_id}.md"
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
            page.frontmatter["concept_ids"] = concept_paths
            exh_path.write_text(page.to_markdown(), encoding="utf-8")
            modified += 1

    return modified


def repair_nested_frontmatter(paths: cfg.WikiPaths, callbacks: Optional[SyncCallbacks] = None) -> int:
    """Remove duplicate YAML frontmatter blocks accidentally embedded in bodies."""
    modified = 0
    for layer_dir in (paths.contexts, paths.atoms, paths.concepts, paths.synthesis):
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
    Phase 2: each SYN - can it be logically derived from its CON evidence?

    Gaps are returned with `reasoning` populated from the LLM response.
    """
    from .llm import LLMError

    # Load Curator persona for domain-context injection
    curator_persona = cfg.get_curator_persona(cfg.load_config(paths))
    domain_context = curator_persona.get("text", "")

    gaps: list[VerificationGap] = []
    blocked_node_ids = blocked_node_ids or set()
    target_concept_ids, target_synthesis_ids = _logical_scope_for_nodes(paths, target_node_ids)
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

    # Phase 2 — SYN <- CONs (if L4 exists)
    # Phase 1 con_results are passed as context so the LLM can factor in CON validity.
    if paths.synthesis.exists():
        if targeted:
            exhibition_files = [
                paths.synthesis / f"{exh_id}.md"
                for exh_id in sorted(target_synthesis_ids)
                if (paths.synthesis / f"{exh_id}.md").exists()
            ]
        else:
            exhibition_files = sorted(paths.synthesis.glob(f"{consts.PREFIX_L4}-*.md"))[:max_curations]
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
            con_ids = _fm_links(fm, "concept_ids")
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

            # Pass only Phase 1 results relevant to this SYN's concept_ids
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
                    message="Synthesis logic not fully derivable from its Concepts.",
                    reasoning=result.get("reasoning", response.strip()[:600]),
                ))

    return gaps


# ---------------------------------------------------------------------------
# Fix — regenerate pages with detected gaps
# ---------------------------------------------------------------------------


def fix_gaps(
    paths: cfg.WikiPaths,
    client,
    gaps: list[VerificationGap],
) -> SyncRepairResult:
    """Collect detected gaps for human/agent review.

    v0.3.1: L3 Concepts and the L4 Synthesis layer are DB-derived projections
    regenerated by the compile pipeline (`pipeline/synthesis.py`) and corrected via
    the insight/backprop lifecycle — not by in-place LLM rewrites during sync. So
    sync surfaces logical gaps for review rather than auto-regenerating pages.
    """
    result = SyncRepairResult()
    seen: set[tuple[str, str]] = set()

    for gap in gaps:
        key = (gap.layer, gap.node_id)
        if key in seen:
            continue
        seen.add(key)
        result.unfixable += 1
        result.needs_review.append(gap)

    return result



def apply_generative_backprop(paths, client, gaps, callbacks=None) -> list[str]:
    """Run generative backprop using the Multi-Agent architecture to extract insights and generate Atoms."""
    from . import backprop_agents as b_agents

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
            md_path = paths.synthesis / f"{gap.node_id}.md"

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
# Finalization — rebuild routing tables
# ---------------------------------------------------------------------------


def finalize_routing_tables(paths: cfg.WikiPaths) -> None:
    """Rebuild index.md, ledger.md, log.md, and overview.md.

    All four, since v0.70.0. This docstring named four files and the body wrote
    two: `ledger.md` and `overview.md` were only ever written by `wiki build`'s
    Phase D, so a user who corrected a source and ran `wiki sync` got a fresh
    `index.md` beside a `ledger.md` still reporting the previous build's counts —
    under a header reading "Auto-maintained by the Curator engine".

    Both writers are pure (directory globs, one COUNT query, a file write) with
    no LLM and no provider, which is why sync can call them.
    """
    import logging

    from . import ingest_llm
    from .db_sync import describe_recoverable_state

    # Refuse to overwrite these files with a false "empty vault" report.
    #
    # `update_ledger`/`update_overview` read the machine-local database, and
    # `db.connect` self-heals an empty schema into a missing one. So on a machine
    # whose `.cache/` was cleared — or after a vault rename, which re-keys the
    # cache — this would write "Last curated: never" and zero counts into files
    # headed "Auto-maintained by the Curator engine", destroying an accurate
    # report and persisting a wrong one where a human reads it.
    #
    # v0.69.2 added exactly this detection but wired it only into `wiki status`.
    recoverable = describe_recoverable_state(paths)
    if recoverable:
        logging.getLogger(__name__).warning(
            "Skipped rebuilding ledger.md/overview.md: the local database is "
            "empty while a sync journal is present, so the rebuilt files would "
            "report an empty vault. %s",
            recoverable,
        )
        page_writer.rebuild_index(paths, page_writer.today_iso())
        return

    today = page_writer.today_iso()
    page_writer.rebuild_index(paths, today)
    ingest_llm.update_ledger(paths)
    ingest_llm.update_overview(paths)
    page_writer.append_log_entry(
        paths,
        today,
        "sync",
        "Deductive verification pass",
        ["Routing tables rebuilt by wiki sync"],
    )
