"""Deterministic authored-note topology compiler (Failure Atlas F9).

Parses a closed set of Obsidian-authored Markdown structures and returns an
immutable in-memory topology. Persistence is a separate operation so the caller
can join the existing compiler-generation publish transaction.
"""

from __future__ import annotations

import hashlib
import re
import string
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
    "empty_authored_topology",
    "extract_authored_topology",
    "is_markdown_path",
    "persist_authored_topology",
]

EntityType = Literal["vault_note", "vault_asset", "tag"]
RelationType = Literal["links_to", "embeds", "tagged_with", "property_ref"]

_TAG_RE = re.compile(r"(?<![\w/])#([^\s#.,;:!?()[\]{}'\"`<>]+)", re.UNICODE)
_URI_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_MARKDOWN_SUFFIXES = {".md", ".markdown"}
_MAX_MARKDOWN_PAREN_DEPTH = 32


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
    activated_relation_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class _LinkMatch:
    start: int
    end: int
    target: str
    embed: bool


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


def is_markdown_path(value: str | Path) -> bool:
    return Path(str(value)).suffix.casefold() in _MARKDOWN_SUFFIXES


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
        if is_markdown_path(path):
            _add_candidate(
                by_path_raw,
                PurePosixPath(relpath).with_suffix("").as_posix(),
                relpath,
            )
        _add_candidate(by_name_raw, path.name, relpath)
        _add_candidate(by_name_raw, path.stem, relpath)

        if not is_markdown_path(path):
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


def _blank_range(chars: list[str], start: int, end: int) -> None:
    for index in range(start, end):
        if chars[index] not in {"\n", "\r"}:
            chars[index] = " "


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and text[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _fenced_region_end(text: str, start: int) -> int | None:
    line_end = text.find("\n", start)
    if line_end < 0:
        line_end = len(text)
    line = text[start:line_end].rstrip("\r")
    opener = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
    if opener is None or (
        opener.group(1).startswith("`") and "`" in opener.group(2)
    ):
        return None

    marker = opener.group(1)[0]
    minimum = len(opener.group(1))
    cursor = min(line_end + 1, len(text))
    while cursor < len(text):
        candidate_end = text.find("\n", cursor)
        if candidate_end < 0:
            candidate_end = len(text)
        candidate = text[cursor:candidate_end].rstrip("\r")
        close = re.fullmatch(
            rf" {{0,3}}({re.escape(marker)}+)[ \t]*",
            candidate,
        )
        if close is not None and len(close.group(1)) >= minimum:
            return min(candidate_end + 1, len(text))
        cursor = min(candidate_end + 1, len(text))
    return len(text)


def _mask_body(text: str) -> str:
    chars = list(text)
    index = 0
    while index < len(text):
        if index == 0 or text[index - 1] == "\n":
            fenced_end = _fenced_region_end(text, index)
            if fenced_end is not None:
                _blank_range(chars, index, fenced_end)
                index = fenced_end
                continue
        if text.startswith("<!--", index):
            closing_start = text.find("-->", index + 4)
            end = len(text) if closing_start < 0 else closing_start + 3
            _blank_range(chars, index, end)
            index = end
            continue
        if text.startswith("%%", index):
            closing_start = text.find("%%", index + 2)
            end = len(text) if closing_start < 0 else closing_start + 2
            _blank_range(chars, index, end)
            index = end
            continue
        if text[index] != "`" or _is_escaped(text, index):
            index += 1
            continue
        run_end = index
        while run_end < len(text) and text[run_end] == "`":
            run_end += 1
        run_length = run_end - index
        cursor = run_end
        closing_end: int | None = None
        while cursor < len(text):
            if text[cursor] != "`":
                cursor += 1
                continue
            candidate_end = cursor
            while candidate_end < len(text) and text[candidate_end] == "`":
                candidate_end += 1
            if candidate_end - cursor == run_length:
                closing_end = candidate_end
                break
            cursor = candidate_end
        if closing_end is None:
            index = run_end
            continue
        _blank_range(chars, index, closing_end)
        index = closing_end
    return "".join(chars)


def _iter_wikilinks(text: str) -> Iterable[_LinkMatch]:
    index = 0
    while index < len(text) - 1:
        embed = text[index] == "!" and text.startswith("[[", index + 1)
        opening = index + 1 if embed else index
        if not text.startswith("[[", opening) or _is_escaped(text, opening):
            index += 1
            continue
        cursor = opening + 2
        while cursor < len(text) - 1:
            if text[cursor] in {"\n", "\r"}:
                break
            if text.startswith("]]", cursor) and not _is_escaped(text, cursor):
                yield _LinkMatch(
                    start=index if embed else opening,
                    end=cursor + 2,
                    target=text[opening + 2 : cursor],
                    embed=embed,
                )
                index = cursor + 2
                break
            cursor += 1
        else:
            index += 1
            continue
        if cursor >= len(text) - 1 or text[cursor] in {"\n", "\r"}:
            index += 1


def _iter_markdown_links(text: str) -> Iterable[_LinkMatch]:
    index = 0
    while index < len(text):
        if text[index] != "[" or _is_escaped(text, index):
            index += 1
            continue
        embed = index > 0 and text[index - 1] == "!" and not _is_escaped(text, index - 1)
        start = index - 1 if embed else index
        label_end = index + 1
        while label_end < len(text):
            if text[label_end] in {"\n", "\r"}:
                break
            if text[label_end] == "]" and not _is_escaped(text, label_end):
                break
            label_end += 1
        if (
            label_end >= len(text)
            or text[label_end] != "]"
            or label_end + 1 >= len(text)
            or text[label_end + 1] != "("
        ):
            index += 1
            continue

        target_start = label_end + 2
        cursor = target_start
        depth = 1
        while cursor < len(text):
            char = text[cursor]
            if char in {"\n", "\r"}:
                break
            if _is_escaped(text, cursor):
                cursor += 1
                continue
            elif char == "(":
                depth += 1
                if depth > _MAX_MARKDOWN_PAREN_DEPTH:
                    break
            elif char == ")":
                depth -= 1
                if depth == 0:
                    yield _LinkMatch(
                        start=start,
                        end=cursor + 1,
                        target=text[target_start:cursor],
                        embed=embed,
                    )
                    index = cursor + 1
                    break
            cursor += 1
        else:
            index += 1
            continue
        if cursor >= len(text) or depth != 0:
            index += 1


def _mask_matches(text: str, matches: Iterable[_LinkMatch]) -> str:
    chars = list(text)
    for match in matches:
        _blank_range(chars, match.start, match.end)
    return "".join(chars)


def _clean_markdown_target(raw: str) -> str:
    target = raw.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = re.sub(r"""\s+["'].*["']\s*$""", "", target)
    target = target.replace("\\ ", " ")
    cleaned: list[str] = []
    index = 0
    while index < len(target):
        if (
            target[index] == "\\"
            and index + 1 < len(target)
            and target[index + 1] in string.punctuation
        ):
            cleaned.append(target[index + 1])
            index += 2
            continue
        cleaned.append(target[index])
        index += 1
    return unquote("".join(cleaned)).strip()


def _clean_internal_target(raw: str) -> str:
    target = _clean_markdown_target(raw)
    target = target.split("|", 1)[0].strip()
    fragment_positions = [
        position for marker in ("#", "^")
        if (position := target.find(marker)) >= 0
    ]
    if fragment_positions:
        target = target[: min(fragment_positions)]
    return unicodedata.normalize("NFC", target.strip()).replace("\\", "/")


def _normalize_vault_path(base: PurePosixPath, target: str) -> str | None:
    parts = [] if target.startswith("/") else list(base.parts)
    for part in target.lstrip("/").split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    normalized = PurePosixPath(*parts).as_posix()
    return normalized if _is_visible_relpath(normalized) else None


def _resolve_stage(
    index: dict[str, tuple[str, ...]],
    key: str | None,
) -> tuple[bool, str | None]:
    if not key:
        return False, None
    candidates = index.get(key.casefold())
    if not candidates:
        return False, None
    return True, candidates[0] if len(candidates) == 1 else None


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
    if not target:
        return None

    source_parent = PurePosixPath(source_relpath).parent
    root_candidate = _normalize_vault_path(PurePosixPath(), target)
    relative_candidate = _normalize_vault_path(source_parent, target)
    target_parts = target.lstrip("/").split("/")
    if any(
        part.startswith(".") and part not in {".", ".."}
        for part in target_parts
    ):
        return None
    if ".." in target_parts and relative_candidate is None:
        return None

    for candidate_key in (root_candidate, relative_candidate):
        matched, resolved = _resolve_stage(inventory.by_path, candidate_key)
        if matched:
            return _endpoint_for_path(resolved) if resolved is not None else None

    basename = PurePosixPath(target).name
    matched, resolved = _resolve_stage(inventory.by_name, basename)
    if matched:
        return _endpoint_for_path(resolved) if resolved is not None else None

    matched, resolved = _resolve_stage(inventory.by_alias, target)
    if matched:
        return _endpoint_for_path(resolved) if resolved is not None else None
    return None


def _endpoint_for_path(relpath: str) -> AuthoredEndpoint:
    entity_type: EntityType = (
        "vault_note" if is_markdown_path(relpath)
        else "vault_asset"
    )
    return AuthoredEndpoint(entity_type=entity_type, canonical_key=relpath)


def _tag_values(value: Any) -> Iterable[str]:
    for raw in _flatten_strings(value):
        for tag in re.split(r"[\s,]+", raw):
            normalized = tag.strip().lstrip("#").casefold()
            if _is_valid_tag(normalized):
                yield normalized


def _is_valid_tag(tag: str) -> bool:
    return bool(tag) and any(
        not char.isdigit() for char in tag.replace("/", "")
    )


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
            for match in _iter_wikilinks(raw_value):
                target = _resolve_target(
                    inventory,
                    source_relpath=source_relpath,
                    raw_target=match.target,
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
    wikilinks = tuple(_iter_wikilinks(safe_body))
    markdown_links = tuple(_iter_markdown_links(safe_body))
    for match in wikilinks:
        target = _resolve_target(
            inventory,
            source_relpath=source_relpath,
            raw_target=match.target,
        )
        if target is not None:
            yield AuthoredRelation(
                source=source,
                target=target,
                relation_type="embeds" if match.embed else "links_to",
            )

    for match in markdown_links:
        target = _resolve_target(
            inventory,
            source_relpath=source_relpath,
            raw_target=match.target,
        )
        if target is not None:
            yield AuthoredRelation(
                source=source,
                target=target,
                relation_type="embeds" if match.embed else "links_to",
            )

    tag_body = _mask_matches(safe_body, (*wikilinks, *markdown_links))
    for tag_match in _TAG_RE.finditer(tag_body):
        if _is_escaped(tag_body, tag_match.start()):
            continue
        tag = tag_match.group(1).strip().lstrip("#").casefold()
        if _is_valid_tag(tag):
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
    if not is_markdown_path(normalized_source) or not _is_visible_relpath(
        normalized_source
    ):
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


def empty_authored_topology(source_relpath: str) -> AuthoredTopology:
    return AuthoredTopology(
        source=AuthoredEndpoint(
            entity_type="vault_note",
            canonical_key=_portable_relpath(source_relpath),
        )
    )


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
    prior_active_ids = {
        str(row[0])
        for row in conn.execute(
            "SELECT r.id FROM graph_relations r "
            "JOIN compiler_generations g ON g.id = r.generation_id "
            "WHERE r.edge_class = 'authored' AND g.source_id = ? "
            "AND r.lifecycle_status = 'active'",
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
        activated_relation_ids=tuple(sorted(current_ids - prior_active_ids)),
    )
