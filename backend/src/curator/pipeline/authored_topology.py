"""Deterministic authored-note topology compiler (Failure Atlas F9).

Parses a closed set of Obsidian-authored Markdown structures and returns an
immutable in-memory topology. Persistence is a separate operation so the caller
can join the existing compiler-generation publish transaction.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Literal
from urllib.parse import unquote

from .. import db, page_writer

__all__ = [
    "AuthoredEndpoint",
    "AuthoredPersistence",
    "AuthoredRelation",
    "AuthoredTopology",
    "extract_authored_topology",
    "persist_authored_topology",
]

EntityType = Literal["vault_note", "vault_asset", "tag"]
RelationType = Literal["links_to", "embeds", "tagged_with", "property_ref"]

_WIKILINK_RE = re.compile(r"(?P<embed>!)?\[\[(?P<target>[^\]\n]+)\]\]")
_MARKDOWN_LINK_RE = re.compile(
    r"(?P<embed>!)?\[(?P<label>[^\]\n]*)\]\((?P<target>[^)\n]+)\)"
)
_FENCED_CODE_RE = re.compile(
    r"(?ms)^[ \t]*(?P<fence>`{3,}|~{3,})[^\n]*\n.*?^[ \t]*(?P=fence)[ \t]*$"
)
_INLINE_CODE_RE = re.compile(r"(?s)(?P<fence>`+).*?(?P=fence)")
_HTML_COMMENT_RE = re.compile(r"(?s)<!--.*?-->")
_OBSIDIAN_COMMENT_RE = re.compile(r"(?s)%%.*?%%")
_TAG_RE = re.compile(r"(?<![\w/])#([^\s#.,;:!?()[\]{}'\"`<>]+)", re.UNICODE)
_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


@dataclass(frozen=True, order=True)
class AuthoredEndpoint:
    entity_type: EntityType
    canonical_key: str

    def __post_init__(self) -> None:
        normalized = unicodedata.normalize("NFC", self.canonical_key)
        if self.entity_type in {"vault_note", "vault_asset"}:
            normalized = PurePosixPath(
                normalized.replace("\\", "/").lstrip("/")
            ).as_posix()
        else:
            normalized = normalized.casefold()
        object.__setattr__(self, "canonical_key", normalized)

    @property
    def entity_id(self) -> str:
        return _stable_id("ENT", self.entity_type, self.canonical_key)


@dataclass(frozen=True, order=True)
class AuthoredRelation:
    source: AuthoredEndpoint
    target: AuthoredEndpoint
    relation_type: RelationType

    @property
    def relation_id(self) -> str:
        return _stable_id(
            "REL",
            self.source.entity_id,
            self.target.entity_id,
            self.relation_type,
        )


@dataclass(frozen=True)
class AuthoredTopology:
    source: AuthoredEndpoint
    relations: tuple[AuthoredRelation, ...] = ()


@dataclass(frozen=True)
class AuthoredPersistence:
    entity_ids: tuple[str, ...] = ()
    relation_ids: tuple[str, ...] = ()
    retired_relation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class _VaultInventory:
    root: Path
    relpaths: tuple[str, ...]
    by_path: dict[str, tuple[str, ...]]
    by_name: dict[str, tuple[str, ...]]
    by_alias: dict[str, tuple[str, ...]]


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "\0".join(parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(payload).hexdigest()[:16]}"


def _portable_relpath(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    return PurePosixPath(normalized.replace("\\", "/").lstrip("/")).as_posix()


def _is_visible_relpath(relpath: str) -> bool:
    parts = PurePosixPath(relpath).parts
    return bool(parts) and all(part not in {"", ".", ".."} and not part.startswith(".") for part in parts)


def _inside_root(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root)
    except (OSError, ValueError):
        return False
    return True


def _add_candidate(index: dict[str, set[str]], key: str, relpath: str) -> None:
    normalized = unicodedata.normalize("NFC", key).strip().casefold()
    if normalized:
        index.setdefault(normalized, set()).add(relpath)


def _flatten_strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _flatten_strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _flatten_strings(item)


def _build_inventory(root: Path) -> _VaultInventory:
    root = root.resolve()
    relpaths: list[str] = []
    by_path_raw: dict[str, set[str]] = {}
    by_name_raw: dict[str, set[str]] = {}
    by_alias_raw: dict[str, set[str]] = {}

    for path in sorted(root.rglob("*")):
        if not path.is_file() or not _inside_root(root, path):
            continue
        relpath = _portable_relpath(path.relative_to(root).as_posix())
        if not _is_visible_relpath(relpath):
            continue
        relpaths.append(relpath)
        _add_candidate(by_path_raw, relpath, relpath)
        if path.suffix.casefold() == ".md":
            _add_candidate(by_path_raw, relpath[:-3], relpath)
        _add_candidate(by_name_raw, path.name, relpath)
        _add_candidate(by_name_raw, path.stem, relpath)

        if path.suffix.casefold() != ".md":
            continue
        parsed = page_writer.read_page(path)
        if parsed is None or parsed.is_invalid:
            continue
        for alias in _flatten_strings(parsed.frontmatter.get("aliases")):
            _add_candidate(by_alias_raw, alias, relpath)

    def freeze(index: dict[str, set[str]]) -> dict[str, tuple[str, ...]]:
        return {key: tuple(sorted(values)) for key, values in index.items()}

    return _VaultInventory(
        root=root,
        relpaths=tuple(relpaths),
        by_path=freeze(by_path_raw),
        by_name=freeze(by_name_raw),
        by_alias=freeze(by_alias_raw),
    )


def _mask_body(text: str) -> str:
    masked = _FENCED_CODE_RE.sub("", text)
    masked = _INLINE_CODE_RE.sub("", masked)
    masked = _HTML_COMMENT_RE.sub("", masked)
    return _OBSIDIAN_COMMENT_RE.sub("", masked)


def _clean_markdown_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = re.sub(r"""\s+["'].*["']\s*$""", "", target)
    return unquote(target.replace("\\ ", " ")).strip()


def _clean_internal_target(raw: str) -> str:
    target = _clean_markdown_target(raw)
    target = target.split("|", 1)[0].strip()
    fragment_positions = [
        position for marker in ("#", "^")
        if (position := target.find(marker)) >= 0
    ]
    if fragment_positions:
        target = target[: min(fragment_positions)]
    return _portable_relpath(target.strip())


def _one(candidates: tuple[str, ...] | None) -> str | None:
    if not candidates or len(candidates) != 1:
        return None
    return candidates[0]


def _resolve_target(
    inventory: _VaultInventory,
    *,
    source_relpath: str,
    raw_target: str,
) -> AuthoredEndpoint | None:
    raw = _clean_markdown_target(raw_target)
    if (
        not raw
        or raw.startswith(("#", "^", "//"))
        or _URI_SCHEME_RE.match(raw)
    ):
        return None
    target = _clean_internal_target(raw)
    if not target or not _is_visible_relpath(target):
        return None

    source_parent = PurePosixPath(source_relpath).parent
    relative = (source_parent / target).as_posix()
    if not _is_visible_relpath(relative):
        return None

    for candidate_key in (target, relative):
        resolved = _one(inventory.by_path.get(candidate_key.casefold()))
        if resolved:
            return _endpoint_for_path(resolved)
        if PurePosixPath(candidate_key).suffix == "":
            resolved = _one(inventory.by_path.get(f"{candidate_key}.md".casefold()))
            if resolved:
                return _endpoint_for_path(resolved)

    basename = PurePosixPath(target).name
    resolved = _one(inventory.by_name.get(basename.casefold()))
    if resolved:
        return _endpoint_for_path(resolved)
    if PurePosixPath(basename).suffix == "":
        resolved = _one(inventory.by_name.get(f"{basename}.md".casefold()))
        if resolved:
            return _endpoint_for_path(resolved)

    resolved = _one(inventory.by_alias.get(target.casefold()))
    return _endpoint_for_path(resolved) if resolved else None


def _endpoint_for_path(relpath: str) -> AuthoredEndpoint:
    entity_type: EntityType = (
        "vault_note" if PurePosixPath(relpath).suffix.casefold() == ".md"
        else "vault_asset"
    )
    return AuthoredEndpoint(entity_type=entity_type, canonical_key=relpath)


def _tag_values(value: Any) -> Iterable[str]:
    for raw in _flatten_strings(value):
        for tag in re.split(r"[\s,]+", raw):
            normalized = tag.strip().lstrip("#").casefold()
            if normalized:
                yield normalized


def _frontmatter_relations(
    parsed: page_writer.ParsedPage,
    *,
    inventory: _VaultInventory,
    source: AuthoredEndpoint,
    source_relpath: str,
) -> Iterable[AuthoredRelation]:
    for tag in _tag_values(parsed.frontmatter.get("tags")):
        yield AuthoredRelation(
            source=source,
            target=AuthoredEndpoint(entity_type="tag", canonical_key=tag),
            relation_type="tagged_with",
        )

    for key, value in parsed.frontmatter.items():
        if str(key).casefold() in {"aliases", "tags"}:
            continue
        for raw_value in _flatten_strings(value):
            for match in _WIKILINK_RE.finditer(raw_value):
                target = _resolve_target(
                    inventory,
                    source_relpath=source_relpath,
                    raw_target=match.group("target"),
                )
                if target is not None:
                    yield AuthoredRelation(
                        source=source,
                        target=target,
                        relation_type="property_ref",
                    )


def _body_relations(
    body: str,
    *,
    inventory: _VaultInventory,
    source: AuthoredEndpoint,
    source_relpath: str,
) -> Iterable[AuthoredRelation]:
    safe_body = _mask_body(body)
    for match in _WIKILINK_RE.finditer(safe_body):
        target = _resolve_target(
            inventory,
            source_relpath=source_relpath,
            raw_target=match.group("target"),
        )
        if target is not None:
            yield AuthoredRelation(
                source=source,
                target=target,
                relation_type="embeds" if match.group("embed") else "links_to",
            )

    for match in _MARKDOWN_LINK_RE.finditer(safe_body):
        target = _resolve_target(
            inventory,
            source_relpath=source_relpath,
            raw_target=match.group("target"),
        )
        if target is not None:
            yield AuthoredRelation(
                source=source,
                target=target,
                relation_type="embeds" if match.group("embed") else "links_to",
            )

    tag_body = _WIKILINK_RE.sub("", safe_body)
    tag_body = _MARKDOWN_LINK_RE.sub("", tag_body)
    for match in _TAG_RE.finditer(tag_body):
        tag = match.group(1).strip().lstrip("#").casefold()
        if tag:
            yield AuthoredRelation(
                source=source,
                target=AuthoredEndpoint(entity_type="tag", canonical_key=tag),
                relation_type="tagged_with",
            )


def extract_authored_topology(
    vault_root: Path,
    source_relpath: str,
    text: str,
) -> AuthoredTopology:
    """Return exact, deduplicated authored topology for one visible Markdown note."""
    normalized_source = _portable_relpath(source_relpath)
    source = AuthoredEndpoint(
        entity_type="vault_note",
        canonical_key=normalized_source,
    )
    if not _is_visible_relpath(normalized_source):
        return AuthoredTopology(source=source)

    inventory = _build_inventory(vault_root)
    if normalized_source not in inventory.relpaths:
        return AuthoredTopology(source=source)

    parsed = page_writer.parse_page(text)
    relations = set(
        _frontmatter_relations(
            parsed,
            inventory=inventory,
            source=source,
            source_relpath=normalized_source,
        )
    )
    relations.update(
        _body_relations(
            parsed.body,
            inventory=inventory,
            source=source,
            source_relpath=normalized_source,
        )
    )
    return AuthoredTopology(source=source, relations=tuple(sorted(relations)))


def persist_authored_topology(
    db_path: Path,
    topology: AuthoredTopology,
    *,
    source_id: int,
    generation_id: str,
    conn: Any,
) -> AuthoredPersistence:
    """Reconcile one source's authored set inside its publish transaction."""
    prior_ids = {
        str(row[0])
        for row in conn.execute(
            "SELECT r.id FROM graph_relations r "
            "JOIN compiler_generations g ON g.id = r.generation_id "
            "WHERE r.edge_class = 'authored' AND g.source_id = ?",
            (source_id,),
        ).fetchall()
    }
    entity_ids: set[str] = set()
    current_ids: set[str] = set()

    for relation in topology.relations:
        for endpoint in (relation.source, relation.target):
            entity_ids.add(
                db.upsert_graph_entity(
                    db_path,
                    entity_id=endpoint.entity_id,
                    canonical_name=endpoint.canonical_key,
                    entity_type=endpoint.entity_type,
                    conn=conn,
                )
            )
        current_ids.add(
            db.upsert_graph_relation(
                db_path,
                relation_id=relation.relation_id,
                source_entity_id=relation.source.entity_id,
                target_entity_id=relation.target.entity_id,
                relation_type=relation.relation_type,
                assertion_source="source_states",
                confidence=1.0,
                edge_class="authored",
                lifecycle_status="provisional",
                topology_weight=1.0,
                generation_id=generation_id,
                conn=conn,
            )
        )

    retired_ids = sorted(prior_ids - current_ids)
    db.retire_graph_relations_on_connection(conn, retired_ids)

    return AuthoredPersistence(
        entity_ids=tuple(sorted(entity_ids)),
        relation_ids=tuple(sorted(current_ids)),
        retired_relation_ids=tuple(retired_ids),
    )
