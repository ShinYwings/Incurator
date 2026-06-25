"""Offline prompt-eval harness.

Prompt evals are treated as tests: a fixture supplies a contract id, a candidate
raw model output, and a validation context, and asserts whether the output should
pass the contract's validators. Running an eval does NOT call an LLM — it parses
and validates fixed text — so evals are deterministic and CI-safe.

Real model evals can layer on top by feeding ``run_prompt`` output into
``evaluate_output``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from .contracts import PromptContract, ValidationResult
from .registry import REGISTRY
from .runner import extract_json
from .validators import run_validators

__all__ = [
    "PromptEvalCase",
    "EvalOutcome",
    "evaluate_output",
    "run_eval_case",
    "BUILTIN_EVAL_CASES",
    "run_all",
]


@dataclass
class PromptEvalCase:
    name: str
    prompt_id: str
    raw_output: str
    validation_context: dict[str, Any] = field(default_factory=dict)
    expect_valid: bool = True
    prompt_version: str | None = None


@dataclass
class EvalOutcome:
    case: PromptEvalCase
    passed: bool
    actual_valid: bool
    validation: ValidationResult


def _parse(contract: PromptContract, raw: str) -> BaseModel | None:
    if contract.output_model is None:
        return None
    try:
        data = json.loads(extract_json(raw), strict=False)
        return contract.output_model.model_validate(data)
    except (json.JSONDecodeError, ValueError, ValidationError):
        return None


def evaluate_output(
    contract: PromptContract,
    raw: str,
    validation_context: dict[str, Any] | None = None,
) -> ValidationResult:
    """Validate a candidate output against a contract (no LLM call)."""
    parsed = _parse(contract, raw)
    names = list(contract.validators)
    if contract.output_model is not None and "json_model" not in names:
        names.insert(0, "json_model")
    return run_validators(names, raw, parsed, validation_context or {})


def run_eval_case(case: PromptEvalCase) -> EvalOutcome:
    contract = REGISTRY.get(case.prompt_id, case.prompt_version)
    validation = evaluate_output(contract, case.raw_output, case.validation_context)
    actual_valid = validation.ok
    return EvalOutcome(
        case=case,
        passed=(actual_valid == case.expect_valid),
        actual_valid=actual_valid,
        validation=validation,
    )


# Built-in deterministic fixtures (no LLM). These pin validator behavior for the
# most safety-critical contracts.
BUILTIN_EVAL_CASES: list[PromptEvalCase] = [
    PromptEvalCase(
        name="knowledge_units: valid with real spans",
        prompt_id="curator.knowledge_unit_extract",
        raw_output=json.dumps(
            {
                "units": [
                    {
                        "canonical_name": "Residual learning eases optimization",
                        "unit_type": "claim",
                        "statement": "Residual connections make deep nets easier to optimize.",
                        "source_span_ids": ["SPAN-aaaa1111"],
                        "confidence": 0.9,
                        "truth_status": "source_supported",
                    }
                ]
            }
        ),
        validation_context={"valid_span_ids": ["SPAN-aaaa1111", "SPAN-bbbb2222"]},
        expect_valid=True,
    ),
    PromptEvalCase(
        name="knowledge_units: invented span id is rejected",
        prompt_id="curator.knowledge_unit_extract",
        raw_output=json.dumps(
            {
                "units": [
                    {
                        "canonical_name": "Fabricated claim",
                        "unit_type": "claim",
                        "statement": "Something not in the spans.",
                        "source_span_ids": ["SPAN-ffff9999"],
                        "confidence": 0.8,
                        "truth_status": "source_supported",
                    }
                ]
            }
        ),
        validation_context={"valid_span_ids": ["SPAN-aaaa1111"]},
        expect_valid=False,
    ),
    PromptEvalCase(
        name="knowledge_units: source_supported with no span is rejected",
        prompt_id="curator.knowledge_unit_extract",
        raw_output=json.dumps(
            {
                "units": [
                    {
                        "canonical_name": "Unsupported",
                        "unit_type": "claim",
                        "statement": "No span attached.",
                        "source_span_ids": [],
                        "confidence": 0.5,
                        "truth_status": "source_supported",
                    }
                ]
            }
        ),
        validation_context={"valid_span_ids": ["SPAN-aaaa1111"]},
        expect_valid=False,
    ),
    PromptEvalCase(
        name="knowledge_units: confidence out of range is rejected",
        prompt_id="curator.knowledge_unit_extract",
        raw_output=json.dumps(
            {
                "units": [
                    {
                        "canonical_name": "Bad confidence",
                        "unit_type": "claim",
                        "statement": "Cited but bad confidence.",
                        "source_span_ids": ["SPAN-aaaa1111"],
                        "confidence": 1.7,
                        "truth_status": "source_supported",
                    }
                ]
            }
        ),
        validation_context={"valid_span_ids": ["SPAN-aaaa1111"]},
        # pydantic rejects confidence>1 at parse time -> json_model fails -> invalid
        expect_valid=False,
    ),
    PromptEvalCase(
        name="knowledge_units: non-English generated fields are rejected",
        prompt_id="curator.knowledge_unit_extract",
        raw_output=json.dumps(
            {
                "units": [
                    {
                        "canonical_name": "잔차 학습",
                        "unit_type": "claim",
                        "statement": "잔차 연결은 깊은 네트워크 최적화를 쉽게 한다.",
                        "source_span_ids": ["SPAN-aaaa1111"],
                        "confidence": 0.9,
                        "truth_status": "source_supported",
                    }
                ]
            }
        ),
        validation_context={"valid_span_ids": ["SPAN-aaaa1111"]},
        expect_valid=False,
    ),
    PromptEvalCase(
        name="knowledge_units: English fields with parenthetical foreign term are accepted",
        prompt_id="curator.knowledge_unit_extract",
        raw_output=json.dumps(
            {
                "units": [
                    {
                        "canonical_name": "Residual learning (잔차)",
                        "unit_type": "claim",
                        "statement": "The residual (잔차) connection eases deep network optimization.",
                        "source_span_ids": ["SPAN-aaaa1111"],
                        "confidence": 0.9,
                        "truth_status": "source_supported",
                    }
                ]
            }
        ),
        validation_context={"valid_span_ids": ["SPAN-aaaa1111"]},
        expect_valid=True,
    ),
    PromptEvalCase(
        name="entity_relation: relation endpoint must be a declared entity",
        prompt_id="curator.entity_relation_extract",
        raw_output=json.dumps(
            {
                "entities": [
                    {"canonical_name": "ResNet", "entity_type": "method",
                     "source_span_ids": ["SPAN-aaaa1111"]}
                ],
                "relations": [
                    {"source": "ResNet", "target": "Neural ODE",
                     "relation_type": "reinterpreted_as",
                     "assertion_source": "system_infers",
                     "source_span_ids": ["SPAN-aaaa1111"], "confidence": 0.6}
                ],
            }
        ),
        validation_context={"valid_span_ids": ["SPAN-aaaa1111"]},
        expect_valid=False,  # "Neural ODE" not declared as an entity
    ),
    PromptEvalCase(
        name="synthesis: proposing source mutation is rejected",
        prompt_id="curator.synthesis_write",
        raw_output=json.dumps(
            {
                "syntheses": [
                    {
                        "title": "Bad synthesis",
                        "statement": "Next, edit 04_Resources/paper.pdf to add the new claim.",
                        "source_span_ids": ["SPAN-aaaa1111"],
                        "confidence": 0.5,
                    }
                ]
            }
        ),
        validation_context={"valid_span_ids": ["SPAN-aaaa1111"]},
        expect_valid=False,
    ),
]


def run_all(cases: list[PromptEvalCase] | None = None) -> list[EvalOutcome]:
    return [run_eval_case(c) for c in (cases if cases is not None else BUILTIN_EVAL_CASES)]
