"""ROADMAP A5: the three index-refresh sites differ ON PURPOSE. Do not unify.

Three MCP tools refresh the search index after a write, and the blocks look near
identical — one catches a typed tuple, two catch `Exception`. That reads as
drift, and an attempt was made on 2026-08-23 to extract one shared helper.

**Two existing tests stopped it**, and they were right:

| tool | unexpected error | pinned by |
|---|---|---|
| `curator_register_source` | **propagates** | `test_error_handling_mcp_server.py::test_register_source_propagates_unexpected_index_refresh_error` |
| `curator_build_source` | **reported as a warning**, `ok: True` | `test_register_build_split.py::test_sync_build_reports_degraded_search_index_refresh` |

The difference is not accidental, it is priced on **what the failure costs the
user**. Registration is cheap and re-runnable, so surfacing a bug in the indexer
is worth failing the call. A build has just run L1→L3 through the LLM — minutes
of provider time — and throwing that away because the index refresh hit a bug
would be far worse than reporting it.

This file exists because the resemblance is genuinely misleading, and the two
tests above are in different files, so neither one reads as a policy. Something
had to say why they disagree.
"""

from __future__ import annotations

import inspect


def test_the_two_policies_are_still_distinct() -> None:
    """If a future refactor makes these identical, the tests above will both
    break — but only after the change is written. Fail here first, with the
    reason attached."""
    from curator.mcp import server

    src = inspect.getsource(server)
    typed = src.count("except (OSError, sqlite3.Error, search.SearchBackendError)")
    assert typed >= 1, (
        "curator_register_source's typed catch is gone; unexpected indexer bugs "
        "will now be reported as warnings instead of surfacing"
    )


def test_the_reason_for_the_difference_is_written_down() -> None:
    """A distinction nobody can find the reason for gets removed eventually."""
    from curator.mcp import server

    src = inspect.getsource(server)
    assert "re-runnable" in src or "already landed" in src, (
        "nothing in mcp/server.py explains why register propagates and build "
        "warns; without that, the next reader unifies them"
    )
