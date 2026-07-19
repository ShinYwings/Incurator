"""Static guardrails for silent broad exception handlers at transport boundaries."""

from __future__ import annotations

import ast
from pathlib import Path


SRC_ROOT = Path(__file__).parents[1] / "src" / "curator"
TARGETS = (
    SRC_ROOT / "commands",
    SRC_ROOT / "mcp",
    SRC_ROOT / "plugin_api",
)


def _is_broad(handler: ast.ExceptHandler) -> bool:
    return handler.type is None or (
        isinstance(handler.type, ast.Name)
        and handler.type.id in {"Exception", "BaseException"}
    )


def _is_silent_statement(statement: ast.stmt) -> bool:
    return (
        isinstance(statement, (ast.Pass, ast.Continue))
        or isinstance(statement, ast.Return)
        and statement.value is None
    )


def test_target_packages_have_no_silent_broad_exception_handlers() -> None:
    silent: list[str] = []
    for target in TARGETS:
        for path in sorted(target.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.ExceptHandler)
                    and _is_broad(node)
                    and node.body
                    and all(_is_silent_statement(statement) for statement in node.body)
                ):
                    silent.append(f"{path.relative_to(SRC_ROOT)}:{node.lineno}")

    assert not silent, "silent broad exception handlers:\n" + "\n".join(silent)
