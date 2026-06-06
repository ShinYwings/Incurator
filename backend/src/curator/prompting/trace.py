"""Prompt run tracing: persist every prompt invocation to ``prompt_runs``.

A prompt run is opened (``start_prompt_run``) before the model call and closed
(``finish_prompt_run``) after validation, recording input/output hashes,
validator status, retry count, and model provenance. Every generated artifact
must be able to name the ``PTR-`` that produced it
(SYSTEM_BEHAVIOR.md §15.2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import db
from .contracts import PromptContract, RenderedPrompt, ValidationResult
from .render import hash_text

__all__ = [
    "provider_name",
    "hash_prompt_output",
    "start_prompt_run",
    "finish_prompt_run",
]

# Map LLM client class names to the provider keys used in config/catalogue.
_PROVIDER_BY_CLASS = {
    "OllamaClient": "ollama",
    "ClaudeCodeClient": "claude-code",
    "AntigravityCliClient": "antigravity-cli",
    "CodexCliClient": "codex-cli",
    "DeepSeekApiClient": "deepseek-api",
}


def provider_name(client: Any) -> str:
    """Best-effort provider key for any LLM client (incl. FailoverClient)."""
    if client is None:
        return ""
    active = getattr(client, "active_provider", None)
    target = active if active is not None else client
    return _PROVIDER_BY_CLASS.get(type(target).__name__, type(target).__name__)


def model_name(client: Any) -> str:
    if client is None:
        return ""
    return str(getattr(client, "model", "") or "")


def hash_prompt_output(output: str) -> str:
    return hash_text(output)


def start_prompt_run(
    db_path: Path,
    contract: PromptContract,
    rendered: RenderedPrompt,
    client: Any = None,
    *,
    source_ids: list[int] | None = None,
    source_span_ids: list[str] | None = None,
    curate_spec_hash: str = "",
    query_trace_id: str | None = None,
) -> str:
    """Open a prompt run row and return its ``PTR-`` trace id."""
    return db.record_prompt_run(
        db_path,
        prompt_id=contract.prompt_id,
        prompt_version=contract.version,
        family=contract.family,
        role=contract.role,
        model_provider=provider_name(client),
        model_name=model_name(client),
        input_hash=rendered.input_hash,
        source_ids=source_ids,
        source_span_ids=source_span_ids,
        curate_spec_hash=curate_spec_hash,
        query_trace_id=query_trace_id,
    )


def finish_prompt_run(
    db_path: Path,
    trace_id: str,
    *,
    output: str,
    validation: ValidationResult,
    retry_count: int = 0,
    latency_ms: int | None = None,
) -> None:
    """Close a prompt run, recording output hash and validator outcome."""
    if not validation.ok:
        status = "failed"
    elif retry_count > 0:
        status = "repaired"
    else:
        status = "ok"
    db.finish_prompt_run(
        db_path,
        trace_id,
        output_hash=hash_prompt_output(output),
        validator_status=status,
        validator_errors=validation.errors,
        retry_count=retry_count,
        latency_ms=latency_ms,
    )
