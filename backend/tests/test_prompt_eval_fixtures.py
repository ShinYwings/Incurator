"""Phase 1 (v0.3.1): offline prompt-eval fixtures."""

from __future__ import annotations

import pytest

from curator.prompting import evals


@pytest.mark.parametrize("case", evals.BUILTIN_EVAL_CASES, ids=lambda c: c.name)
def test_builtin_eval_case(case: evals.PromptEvalCase) -> None:
    outcome = evals.run_eval_case(case)
    assert outcome.passed, (
        f"{case.name}: expected valid={case.expect_valid}, "
        f"got valid={outcome.actual_valid}, errors={outcome.validation.errors}"
    )


def test_run_all_reports_every_case() -> None:
    outcomes = evals.run_all()
    assert len(outcomes) == len(evals.BUILTIN_EVAL_CASES)
    assert all(o.passed for o in outcomes)
