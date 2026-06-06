"""Prompt contract types for the v0.3.1 prompt subsystem.

A ``PromptContract`` is the single, versioned, testable description of one
prompt: its identity, its typed input/output models, its system/user templates,
the validators its output must pass, and its retry policy. Contracts are the
v0.3.1 replacement for the scattered ``build_*_messages()`` functions; see
``docs/specs/system_behavior/SYSTEM_BEHAVIOR.md`` §15.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel

from ..llm import ChatMessage

__all__ = [
    "ChatMessage",
    "PromptContract",
    "RenderedPrompt",
    "ValidationResult",
]


@dataclass(frozen=True)
class PromptContract:
    """A versioned, contract-driven prompt definition.

    Templates use ``{{ field }}`` placeholders (mustache-style) rather than
    ``str.format`` so that literal JSON braces in the template text are safe.
    Placeholders resolve against the rendered input model's fields plus any
    extra context passed to the renderer.
    """

    prompt_id: str
    version: str
    family: str
    role: str
    purpose: str
    input_model: type[BaseModel]
    system_template: str
    user_template: str
    output_model: type[BaseModel] | None = None
    validators: tuple[str, ...] = ()
    retry_policy: str = "json_repair_once"
    trace_fields: tuple[str, ...] = ()
    temperature: float = 0.3
    requires_source_spans: bool = False

    @property
    def supports_json_mode(self) -> bool:
        return self.output_model is not None

    @property
    def key(self) -> str:
        return f"{self.prompt_id}@{self.version}"


@dataclass(frozen=True)
class RenderedPrompt:
    """The concrete messages produced from a contract for one input."""

    contract: PromptContract
    messages: list[ChatMessage]
    input_hash: str


@dataclass
class ValidationResult:
    """Outcome of running one validator (or an aggregate of several)."""

    ok: bool
    errors: list[str] = field(default_factory=list)

    @classmethod
    def passed(cls) -> "ValidationResult":
        return cls(ok=True, errors=[])

    @classmethod
    def failed(cls, *errors: str) -> "ValidationResult":
        return cls(ok=False, errors=list(errors))

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        return ValidationResult(
            ok=self.ok and other.ok,
            errors=[*self.errors, *other.errors],
        )
