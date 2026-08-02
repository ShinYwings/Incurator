"""Phase 1 (v0.3.1): prompt registry and contract completeness."""

from __future__ import annotations

from dataclasses import replace

import pytest

from curator import prompting
from curator.prompting.registry import PromptRegistry

REQUIRED_IDS = {
    "curator.source_map",
    "curator.knowledge_unit_extract",
    "curator.entity_relation_extract",
    "curator.community_report_write",
    "curator.synthesis_write",
    "curator.curation_plan",
    "curator.query_router",
    "curator.query_local_answer",
    "curator.query_global_reduce",
    "curator.query_explore_expand",
    "curator.backprop_classify",
    "curator.backprop_patch_plan",
    "curator.note_context_pack",
}


def test_all_required_prompts_registered() -> None:
    assert REQUIRED_IDS <= set(prompting.REGISTRY.ids())


def test_prompt_ids_are_unique() -> None:
    prompting.REGISTRY.assert_unique()


def test_duplicate_registration_raises() -> None:
    reg = PromptRegistry()
    contract = prompting.REGISTRY.get("curator.source_map")
    reg.register(contract)
    with pytest.raises(ValueError):
        reg.register(contract)


def test_get_unknown_prompt_raises() -> None:
    with pytest.raises(KeyError):
        prompting.REGISTRY.get("curator.does_not_exist")


def test_every_contract_has_required_fields() -> None:
    for contract in prompting.REGISTRY.list():
        assert contract.prompt_id
        assert contract.version
        assert contract.family
        assert contract.role
        assert contract.purpose
        assert contract.input_model is not None
        assert contract.system_template.strip()
        assert contract.user_template.strip()


def test_json_families_declare_output_model() -> None:
    # Every prompt that asks for JSON must declare an output model so the runner
    # can parse and validate it.
    for contract in prompting.REGISTRY.list():
        if "ONLY JSON" in contract.system_template:
            assert contract.output_model is not None, contract.prompt_id


def test_validator_names_are_known() -> None:
    for contract in prompting.REGISTRY.list():
        for name in contract.validators:
            assert name in prompting.VALIDATORS, f"{contract.prompt_id}:{name}"


def test_list_filters_by_family() -> None:
    query_prompts = prompting.REGISTRY.list(family="query")
    assert {c.prompt_id for c in query_prompts} == {
        "curator.query_router",
        "curator.query_local_answer",
        "curator.query_global_reduce",
    }


def test_prompt_versions_use_numeric_latest_and_list_order() -> None:
    reg = PromptRegistry()
    base = prompting.REGISTRY.get("curator.source_map")
    for version in ("v9", "v10", "v2"):
        reg.register(replace(base, prompt_id="curator.version_test", version=version))

    assert reg.get("curator.version_test").version == "v10"
    assert [contract.version for contract in reg.list()] == ["v2", "v9", "v10"]


@pytest.mark.parametrize("version", ["1", "v", "v1beta", "v1.", "v1..2"])
def test_prompt_registry_rejects_malformed_versions(version: str) -> None:
    reg = PromptRegistry()
    base = prompting.REGISTRY.get("curator.source_map")

    with pytest.raises(ValueError, match="malformed prompt version"):
        reg.register(replace(base, prompt_id="curator.version_test", version=version))

    assert reg.ids() == []
