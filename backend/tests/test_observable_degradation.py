"""SYSTEM_BEHAVIOR §32 — internal recoveries must stay observable.

§32 forbids the unexplained silent `except Exception: pass`. Each test here
pins one boundary that used to swallow its cause: the operation still degrades
gracefully (that part is correct), but the suppressed reason now reaches a log
so the user is not left with a wrong diagnosis or a false success.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from curator import config as cfg
from curator import db, lint, llm_identity


def _seeded_vault(tmp_path: Path) -> cfg.WikiPaths:
    paths = cfg.WikiPaths(tmp_path)
    for layer_dir in (paths.contexts, paths.atoms, paths.concepts, paths.synthesis):
        layer_dir.mkdir(parents=True, exist_ok=True)
    (tmp_path / "03_Notes").mkdir(parents=True, exist_ok=True)
    db.init_db(paths.state_db)
    (paths.atoms / "ATM-broken1.md").write_text(
        """---
id: ATM-broken1
type: atom
parent_source: 01_Contexts/CTX-missing1
source_path: ""
claim_type: fact
last_updated: 2026-05-04T00:00:00Z
---

# Broken Atom

- [[01_Contexts/]]
""",
        encoding="utf-8",
    )
    return paths


def test_lint_fix_reports_a_failed_search_index_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """`wiki lint --fix` rewrote pages but could not reindex them.

    The pages on disk and the search index have diverged, so queries serve stale
    text until `wiki reindex` runs. Swallowing the failure made that a false
    success: the command reported N pages fixed and said nothing about the index.
    """
    paths = _seeded_vault(tmp_path)
    report = lint.run_lint(paths)
    assert any(issue.fixable for issue in report.issues)

    from curator import search

    def _boom(*_args, **_kwargs):
        raise RuntimeError("embedding provider unreachable")

    monkeypatch.setattr(search, "update_index", _boom)

    with caplog.at_level(logging.WARNING, logger="curator.lint"):
        modified = lint.apply_fixes(paths, report.issues)

    assert modified >= 1
    messages = [record.getMessage() for record in caplog.records]
    assert any("embedding provider unreachable" in m for m in messages), messages
    assert any("wiki reindex" in m for m in messages), messages


@pytest.mark.parametrize(
    ("provider_key", "creds_relpath"),
    [
        ("antigravity-cli", ".gemini/oauth_creds.json"),
        ("codex-cli", ".codex/auth.json"),
    ],
)
def test_unreadable_cli_credentials_are_logged_not_silently_generic(
    provider_key: str,
    creds_relpath: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A corrupt provider credential file degrades to the generic account label.

    That fallback is correct — §32 only requires the suppressed cause remain
    observable, because otherwise "Authenticated" is indistinguishable from a
    credential file the user needs to repair.
    """
    creds = tmp_path / creds_relpath
    creds.parent.mkdir(parents=True, exist_ok=True)
    creds.write_text("{not json at all", encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    with caplog.at_level(logging.WARNING, logger="curator.llm_identity"):
        info = llm_identity.get_llm_account_info(provider_key)

    assert info["name"] == "Authenticated"
    messages = [record.getMessage() for record in caplog.records]
    assert any(str(creds) in m for m in messages), messages


def test_malformed_jwt_claims_stay_a_silent_deterministic_fallback() -> None:
    """The counterpart rule: deterministic parsing catches specific classes only.

    A token that is not valid base64 JSON is expected input, not a degradation,
    so §32 wants narrow exception classes here rather than a warning per call.
    """
    assert llm_identity._decode_jwt_claims("header.!!!not-base64!!!.sig") == {}
    assert llm_identity._decode_jwt_claims("") == {}
    assert llm_identity._decode_jwt_claims("no-dots") == {}
