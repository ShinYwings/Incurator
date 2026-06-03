"""Run a prompt contract end-to-end: render, trace, call, validate, repair.

``run_prompt`` is the single entry point pipelines use in v0.3.1. It renders the
contract, opens a ``prompt_runs`` trace, calls the LLM client, parses/validates
the output, performs one JSON-repair retry when the contract allows it, closes
the trace, and returns the parsed model plus the trace id.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, ValidationError

from .contracts import ChatMessage, PromptContract, ValidationResult
from .render import render_prompt
from .trace import finish_prompt_run, start_prompt_run
from .validators import run_validators

__all__ = ["PromptRunResult", "run_prompt", "extract_json"]


@dataclass
class PromptRunResult:
    trace_id: str
    raw: str
    parsed: BaseModel | None
    validation: ValidationResult
    retry_count: int

    @property
    def ok(self) -> bool:
        return self.validation.ok


def extract_json(text: str) -> str:
    """Extract the first balanced JSON object or array from model text,
    tolerating code fences and surrounding prose."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("\n", 1)
        text = parts[1] if len(parts) == 2 else text
        if text.rstrip().endswith("```"):
            text = text.rsplit("```", 1)[0]
    # Find the earliest of '{' or '['.
    candidates = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not candidates:
        return text
    start = min(candidates)
    open_ch = text[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth, in_str, escape = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _parse(contract: PromptContract, raw: str) -> BaseModel | None:
    if contract.output_model is None:
        return None
    try:
        data = json.loads(extract_json(raw), strict=False)
    except (json.JSONDecodeError, ValueError):
        return None
    try:
        return contract.output_model.model_validate(data)
    except ValidationError:
        return None


def _validator_names(contract: PromptContract) -> list[str]:
    names = list(contract.validators)
    if contract.output_model is not None and "json_model" not in names:
        names.insert(0, "json_model")
    return names


def _validate(
    contract: PromptContract,
    raw: str,
    parsed: BaseModel | None,
    ctx: Mapping[str, Any],
) -> ValidationResult:
    return run_validators(_validator_names(contract), raw, parsed, ctx)


def _repair_message(result_raw: str, errors: list[str]) -> list[ChatMessage]:
    issues = "\n".join(f"- {e}" for e in errors)
    return [
        ChatMessage(role="assistant", content=result_raw),
        ChatMessage(
            role="user",
            content=(
                "Your previous response failed validation:\n"
                f"{issues}\n\n"
                "Return a corrected response that fixes every issue. "
                "Output only the corrected JSON, with no commentary."
            ),
        ),
    ]


def run_prompt(
    db_path: Path,
    client: Any,
    contract: PromptContract,
    input_obj: BaseModel,
    *,
    context: Mapping[str, Any] | None = None,
    validation_context: Mapping[str, Any] | None = None,
    source_ids: list[int] | None = None,
    source_span_ids: list[str] | None = None,
    curate_spec_hash: str = "",
    query_trace_id: str | None = None,
) -> PromptRunResult:
    vctx: Mapping[str, Any] = validation_context or {}
    rendered = render_prompt(contract, input_obj, context=context)
    trace_id = start_prompt_run(
        db_path,
        contract,
        rendered,
        client,
        source_ids=source_ids,
        source_span_ids=source_span_ids,
        curate_spec_hash=curate_spec_hash,
        query_trace_id=query_trace_id,
    )

    started = time.monotonic()
    raw = client.chat(
        rendered.messages,
        json_mode=contract.supports_json_mode,
        temperature=contract.temperature,
    )
    parsed = _parse(contract, raw)
    validation = _validate(contract, raw, parsed, vctx)
    retry_count = 0

    if not validation.ok and contract.retry_policy == "json_repair_once":
        retry_count = 1
        repair_messages = [*rendered.messages, *_repair_message(raw, validation.errors)]
        raw2 = client.chat(
            repair_messages,
            json_mode=contract.supports_json_mode,
            temperature=contract.temperature,
        )
        parsed2 = _parse(contract, raw2)
        validation2 = _validate(contract, raw2, parsed2, vctx)
        # Keep the repair attempt; it is the model's best/last word.
        raw, parsed, validation = raw2, parsed2, validation2

    latency_ms = int((time.monotonic() - started) * 1000)
    finish_prompt_run(
        db_path,
        trace_id,
        output=raw,
        validation=validation,
        retry_count=retry_count,
        latency_ms=latency_ms,
    )
    return PromptRunResult(
        trace_id=trace_id,
        raw=raw,
        parsed=parsed,
        validation=validation,
        retry_count=retry_count,
    )
