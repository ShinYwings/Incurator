import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_v021_schema_and_behavior_specs_exist() -> None:
    assert (ROOT / "docs/spec/curator_schema/SCHEMA_v0.2.1.md").exists()
    assert (ROOT / "docs/spec/system_behavior/incurator_v0.2.1.md").exists()


def test_v021_plan_declares_spec_source_of_truth() -> None:
    plan = (ROOT / "docs/plans/update_plan/v0.2.1.md").read_text(encoding="utf-8")
    master = (
        ROOT / "docs/plans/update_plan/v0.2.1_specs/00_Master_Plan.md"
    ).read_text(encoding="utf-8")

    for text in (plan, master):
        assert "SCHEMA_v0.2.1.md" in text
        assert "incurator_v0.2.1.md" in text
        assert "docs/spec" in text


def test_agent_rules_require_spec_first_version_development() -> None:
    for filename in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        text = (ROOT / filename).read_text(encoding="utf-8")
        assert "Spec-First Version Development" in text
        assert "docs/spec/curator_schema/SCHEMA_vX.Y.Z.md" in text
        assert "docs/spec/system_behavior/incurator_vX.Y.Z.md" in text
        assert "plans alone are not sufficient ground truth" in text


def test_v021_package_versions_match_spec_version() -> None:
    version = "0.2.1"

    backend_pyproject = (ROOT / "backend/pyproject.toml").read_text(encoding="utf-8")
    backend_init = (ROOT / "backend/src/curator/__init__.py").read_text(encoding="utf-8")
    plugin_pkg = json.loads((ROOT / "plugin/package.json").read_text(encoding="utf-8"))
    plugin_lock = json.loads((ROOT / "plugin/package-lock.json").read_text(encoding="utf-8"))
    plugin_manifest = json.loads((ROOT / "plugin/manifest.json").read_text(encoding="utf-8"))

    assert re.search(r'^version\s*=\s*"0\.2\.1"', backend_pyproject, re.MULTILINE)
    assert f'__version__ = "{version}"' in backend_init
    assert plugin_pkg["version"] == version
    assert plugin_lock["version"] == version
    assert plugin_lock["packages"][""]["version"] == version
    assert plugin_manifest["version"] == version


def test_v021_antigravity_install_command_is_not_todo() -> None:
    spec = (
        ROOT / "docs/plans/update_plan/v0.2.1_specs/06_Infra_and_Migration.md"
    ).read_text(encoding="utf-8")
    schema = (ROOT / "docs/spec/curator_schema/SCHEMA_v0.2.1.md").read_text(
        encoding="utf-8"
    )
    models = json.loads(
        (ROOT / "backend/src/curator/data/models.json").read_text(encoding="utf-8")
    )

    install_cmd = models["providers"]["antigravity"]["install_cmd"]
    assert "TODO" not in spec
    assert install_cmd == "curl -fsSL https://antigravity.google/cli/install.sh | bash"
    assert install_cmd in spec
    assert install_cmd in schema
    assert "irm https://antigravity.google/cli/install.ps1 | iex" in spec
    assert "irm https://antigravity.google/cli/install.ps1 | iex" in schema


def test_v021_embedding_clustering_contract_is_enabled() -> None:
    pyproject = (ROOT / "backend/pyproject.toml").read_text(encoding="utf-8")
    behavior = (ROOT / "docs/spec/system_behavior/incurator_v0.2.1.md").read_text(
        encoding="utf-8"
    )
    workflow = (ROOT / "docs/guides/WORKFLOW_EN.md").read_text(encoding="utf-8")

    assert "scikit-learn" in pyproject
    assert "embedding-first L3 clustering" in behavior
    assert "embedding-based clustering" in workflow
