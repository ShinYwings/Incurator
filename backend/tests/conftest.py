from pathlib import Path

import pytest

from curator import config as cfg


@pytest.fixture(autouse=True)
def isolate_global_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep CLI tests from writing repo-local .cache/config state."""
    monkeypatch.setattr(cfg, "get_global_config_dir", lambda: tmp_path / "global_config")
