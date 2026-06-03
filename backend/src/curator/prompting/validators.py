"""Prompt output validators.

Each validator has the uniform signature ``(raw, parsed, ctx) -> ValidationResult``
and is referenced by name from a ``PromptContract.validators`` tuple. The runner
runs them in order with a shared context dict; the implicit JSON-model parse is
handled by the runner before named validators run.

See ``docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.3.1.md`` §15.3.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping

from pydantic import BaseModel

from .contracts import ValidationResult

__all__ = ["VALIDATORS", "get_validator", "run_validators"]

Validator = Callable[[str, "BaseModel | None", Mapping[str, Any]], ValidationResult]

_WIKILINK = re.compile(r"\[\[([^\]\|#]+)")
# Instructions that would mutate read-only source truth.
_SOURCE_MUTATION = re.compile(
    r"(?:edit|write|overwrite|modify|rewrite|delete)\b[^\n]{0,40}?"
    r"(03_Notes|04_Resources|06_Archives)",
    re.IGNORECASE,
)


def _as_dict(parsed: BaseModel | None) -> dict[str, Any]:
    if parsed is None:
        return {}
    return parsed.model_dump()


def _walk(value: Any):
    """Yield every (key, value) pair found recursively in dict/list trees."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _iter_dicts(value: Any):
    """Yield every dict node in a dict/list tree (including nested in lists)."""
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from _iter_dicts(v)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_dicts(item)


def _collect_values(parsed: BaseModel | None, key: str) -> list[Any]:
    out: list[Any] = []
    for k, v in _walk(_as_dict(parsed)):
        if k == key:
            if isinstance(v, list):
                out.extend(v)
            else:
                out.append(v)
    return out


def validate_json_model(raw: str, parsed: BaseModel | None, ctx: Mapping[str, Any]) -> ValidationResult:
    if parsed is None:
        return ValidationResult.failed("output did not parse into the declared model")
    return ValidationResult.passed()


def validate_source_span_ids(raw: str, parsed: BaseModel | None, ctx: Mapping[str, Any]) -> ValidationResult:
    """Every cited source span id must be a real, known span id."""
    valid = set(ctx.get("valid_span_ids") or [])
    cited = [str(s) for s in _collect_values(parsed, "source_span_ids")]
    if not valid:
        # Nothing to validate against; treat as non-blocking but flag empties.
        return ValidationResult.passed()
    invented = sorted({s for s in cited if s and s not in valid})
    if invented:
        return ValidationResult.failed(
            f"output cites unknown source span ids: {invented}"
        )
    return ValidationResult.passed()


def validate_requires_source_spans(raw: str, parsed: BaseModel | None, ctx: Mapping[str, Any]) -> ValidationResult:
    """source_supported units must cite at least one span."""
    errors: list[str] = []
    for node in _iter_dicts(_as_dict(parsed)):
        if "source_span_ids" not in node:
            continue
        if node.get("truth_status", "source_supported") != "source_supported":
            continue
        if not node.get("source_span_ids"):
            name = node.get("canonical_name") or node.get("statement") or "<unit>"
            errors.append(f"source_supported unit has no source spans: {name!r}")
    return ValidationResult.passed() if not errors else ValidationResult(ok=False, errors=errors)


def validate_no_unknown_wikilinks(raw: str, parsed: BaseModel | None, ctx: Mapping[str, Any]) -> ValidationResult:
    allowed = ctx.get("allowed_targets")
    if not allowed:
        return ValidationResult.passed()
    allowed_set = set(allowed)
    invented = sorted(
        {m.group(1).strip() for m in _WIKILINK.finditer(raw)} - allowed_set
    )
    if invented:
        return ValidationResult.failed(f"output invents wikilinks: {invented}")
    return ValidationResult.passed()


def validate_no_source_truth_pollution(raw: str, parsed: BaseModel | None, ctx: Mapping[str, Any]) -> ValidationResult:
    match = _SOURCE_MUTATION.search(raw)
    if match:
        return ValidationResult.failed(
            f"output proposes mutating read-only source truth: {match.group(0)!r}"
        )
    return ValidationResult.passed()


def validate_confidence_range(raw: str, parsed: BaseModel | None, ctx: Mapping[str, Any]) -> ValidationResult:
    errors: list[str] = []
    for value in _collect_values(parsed, "confidence"):
        try:
            f = float(value)
        except (TypeError, ValueError):
            errors.append(f"confidence not numeric: {value!r}")
            continue
        if not 0.0 <= f <= 1.0:
            errors.append(f"confidence out of [0,1]: {f}")
    return ValidationResult.passed() if not errors else ValidationResult(ok=False, errors=errors)


def validate_relation_endpoints(raw: str, parsed: BaseModel | None, ctx: Mapping[str, Any]) -> ValidationResult:
    """Relation endpoints must be among declared entity names/ids in this output."""
    data = _as_dict(parsed)
    entities = data.get("entities") or []
    names = {e.get("canonical_name") for e in entities if isinstance(e, dict)}
    names |= {e.get("id") for e in entities if isinstance(e, dict)}
    relations = data.get("relations") or []
    errors: list[str] = []
    for rel in relations:
        if not isinstance(rel, dict):
            continue
        for end_key in ("source", "target", "source_entity", "target_entity"):
            end = rel.get(end_key)
            if end is not None and end not in names:
                errors.append(f"relation endpoint not a declared entity: {end!r}")
    return ValidationResult.passed() if not errors else ValidationResult(ok=False, errors=errors)


def validate_exhibition_frontmatter(raw: str, parsed: BaseModel | None, ctx: Mapping[str, Any]) -> ValidationResult:
    required = set(ctx.get("required_frontmatter") or [])
    if not required:
        return ValidationResult.passed()
    data = _as_dict(parsed)
    fm = data.get("frontmatter") if isinstance(data.get("frontmatter"), dict) else data
    missing = sorted(required - set(fm))
    if missing:
        return ValidationResult.failed(f"exhibition frontmatter missing: {missing}")
    return ValidationResult.passed()


VALIDATORS: dict[str, Validator] = {
    "json_model": validate_json_model,
    "source_span_ids": validate_source_span_ids,
    "requires_source_spans": validate_requires_source_spans,
    "no_unknown_wikilinks": validate_no_unknown_wikilinks,
    "no_source_truth_pollution": validate_no_source_truth_pollution,
    "confidence_range": validate_confidence_range,
    "relation_endpoints": validate_relation_endpoints,
    "exhibition_frontmatter": validate_exhibition_frontmatter,
}


def get_validator(name: str) -> Validator:
    if name not in VALIDATORS:
        raise KeyError(f"unknown validator: {name}")
    return VALIDATORS[name]


def run_validators(
    names: tuple[str, ...] | list[str],
    raw: str,
    parsed: BaseModel | None,
    ctx: Mapping[str, Any],
) -> ValidationResult:
    result = ValidationResult.passed()
    for name in names:
        result = result.merge(get_validator(name)(raw, parsed, ctx))
    return result
