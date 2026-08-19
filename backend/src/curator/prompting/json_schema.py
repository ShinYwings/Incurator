"""Flatten a pydantic JSON Schema for a CLI that cannot follow `$ref`.

`model_json_schema()` hoists every nested model and enum into `$defs` and points
at them with `$ref`. That is correct JSON Schema and the wrong thing to hand to
the Antigravity CLI.

**This module exists because of a silent failure, not a loud one.** Measured on
the real `curator.knowledge_unit_extract` schema, with the schema as the only
variable:

    as emitted ($defs + $ref)   status=SUCCESS  num_turns=2  units returned: 0
    flattened                   status=SUCCESS  num_turns=1  units returned: 2

The referenced schema does not error. It *succeeds and returns nothing*, leaving
the real answer in the response text under field names the contract never
declared. So an unflattened schema does not break a run — it ingests a source to
nothing while reporting success, which is worse than the crash this whole change
replaces. See SYSTEM_BEHAVIOR §11.0.
"""

from __future__ import annotations

from typing import Any

__all__ = ["flatten_refs", "UnflattenableSchema"]

_DEFS_KEYS = ("$defs", "definitions")


class UnflattenableSchema(ValueError):
    """A schema that cannot be expressed without `$ref` — e.g. a recursive model.

    Raised rather than returned as a partial result: a half-flattened schema
    reproduces the silent-empty failure this module exists to prevent, and the
    caller can still fall back to the prose path knowingly.
    """


def flatten_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Return ``schema`` with every ``$ref`` replaced by a copy of its target.

    Each site gets its OWN copy: sharing one object between two sites would let
    a later mutation of one silently rewrite the other.
    """
    defs: dict[str, Any] = {}
    for key in _DEFS_KEYS:
        defs.update(schema.get(key) or {})

    def resolve(node: Any, seen: frozenset[str]) -> Any:
        if isinstance(node, list):
            return [resolve(item, seen) for item in node]
        if not isinstance(node, dict):
            return node

        ref = node.get("$ref")
        if isinstance(ref, str):
            name = ref.rsplit("/", 1)[-1]
            if name in seen:
                # A model that contains itself cannot be inlined at all; every
                # expansion produces another `$ref`. Say so instead of looping.
                raise UnflattenableSchema(
                    f"'{name}' is recursive and cannot be flattened"
                )
            target = defs.get(name)
            if target is None:
                raise UnflattenableSchema(f"'{ref}' has no definition to inline")
            # Sibling keys beside a $ref (title, description, default) are kept:
            # pydantic emits them and dropping them loses field documentation.
            merged = {k: v for k, v in node.items() if k != "$ref"}
            resolved = resolve(target, seen | {name})
            return {**resolved, **merged}

        return {
            k: resolve(v, seen)
            for k, v in node.items()
            if k not in _DEFS_KEYS
        }

    flat = resolve(schema, frozenset())
    if not isinstance(flat, dict):  # pragma: no cover - a schema root is an object
        raise UnflattenableSchema("schema root is not an object")
    return flat
