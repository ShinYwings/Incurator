"""Incurator v0.3.1 prompt subsystem.

A versioned, contract-driven, traceable prompt layer. Importing this package
registers every prompt family into the global ``REGISTRY`` and exposes the public
surface pipelines use:

    from curator import prompting
    contract = prompting.REGISTRY.get("curator.knowledge_unit_extract")
    result = prompting.run_prompt(db_path, client, contract, input_obj, ...)

See ``docs/specs/system_behavior/SYSTEM_BEHAVIOR_v0.3.1.md`` §15.
"""

from __future__ import annotations

from .contracts import (
    ChatMessage,
    PromptContract,
    RenderedPrompt,
    ValidationResult,
)
from .registry import REGISTRY, PromptRegistry, register
from .render import hash_messages, hash_text, render_prompt, render_template
from .runner import PromptRunResult, run_prompt
from .trace import finish_prompt_run, hash_prompt_output, provider_name, start_prompt_run
from .validators import VALIDATORS, get_validator, run_validators

# Importing families registers all prompt contracts as a side effect.
from . import families  # noqa: E402,F401

# Fail fast on any accidental duplicate registration.
REGISTRY.assert_unique()

__all__ = [
    "ChatMessage",
    "PromptContract",
    "RenderedPrompt",
    "ValidationResult",
    "PromptRegistry",
    "REGISTRY",
    "register",
    "render_prompt",
    "render_template",
    "hash_messages",
    "hash_text",
    "hash_prompt_output",
    "provider_name",
    "start_prompt_run",
    "finish_prompt_run",
    "run_prompt",
    "PromptRunResult",
    "VALIDATORS",
    "get_validator",
    "run_validators",
    "families",
]
