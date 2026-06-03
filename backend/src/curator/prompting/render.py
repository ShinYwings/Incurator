"""Render a prompt contract + input into concrete chat messages.

Templates use ``{{ field }}`` placeholders so literal JSON braces in template
text (common in extraction prompts) are never mistaken for format fields. Values
come from the input model's fields plus any extra ``context`` mapping; non-string
values are JSON-encoded for stable, readable substitution.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from pydantic import BaseModel

from .contracts import ChatMessage, PromptContract, RenderedPrompt

__all__ = [
    "render_prompt",
    "render_template",
    "hash_messages",
    "hash_text",
]

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, indent=2)


def render_template(template: str, values: Mapping[str, Any]) -> str:
    """Replace ``{{ field }}`` placeholders. Unknown placeholders raise so a
    missing input is a loud error, not a silent empty string."""
    missing: list[str] = []

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            missing.append(name)
            return match.group(0)
        return _stringify(values[name])

    out = _PLACEHOLDER.sub(_sub, template)
    if missing:
        raise KeyError(
            f"prompt template references undefined fields: {sorted(set(missing))}"
        )
    return out


def render_prompt(
    contract: PromptContract,
    input_obj: BaseModel,
    *,
    context: Mapping[str, Any] | None = None,
) -> RenderedPrompt:
    values: dict[str, Any] = dict(input_obj.model_dump())
    if context:
        values.update(context)
    system = render_template(contract.system_template, values)
    user = render_template(contract.user_template, values)
    messages = [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content=user),
    ]
    return RenderedPrompt(
        contract=contract,
        messages=messages,
        input_hash=hash_messages(messages),
    )


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def hash_messages(messages: list[ChatMessage]) -> str:
    joined = "\n".join(f"{m.role}:{m.content}" for m in messages)
    return hash_text(joined)
