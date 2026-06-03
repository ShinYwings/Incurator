"""Prompt registry: unique, versioned lookup of prompt contracts.

The registry is the single place that knows every prompt the Curator can run.
``assert_unique`` enforces the v0.3.1 rule that prompt ids are unique; a
duplicate registration of the same ``prompt_id@version`` is a defect.
"""

from __future__ import annotations

from .contracts import PromptContract

__all__ = ["PromptRegistry", "REGISTRY", "register"]


class PromptRegistry:
    def __init__(self) -> None:
        # key: prompt_id -> {version: contract}
        self._by_id: dict[str, dict[str, PromptContract]] = {}

    def register(self, contract: PromptContract) -> PromptContract:
        versions = self._by_id.setdefault(contract.prompt_id, {})
        if contract.version in versions:
            raise ValueError(
                f"duplicate prompt registration: {contract.key}"
            )
        versions[contract.version] = contract
        return contract

    def get(self, prompt_id: str, version: str | None = None) -> PromptContract:
        versions = self._by_id.get(prompt_id)
        if not versions:
            raise KeyError(f"unknown prompt id: {prompt_id}")
        if version is None:
            # Latest by string-sorted version (v1, v2, ...).
            latest = sorted(versions)[-1]
            return versions[latest]
        if version not in versions:
            raise KeyError(f"unknown prompt version: {prompt_id}@{version}")
        return versions[version]

    def list(self, family: str | None = None) -> list[PromptContract]:
        out = []
        for versions in self._by_id.values():
            for contract in versions.values():
                if family is None or contract.family == family:
                    out.append(contract)
        return sorted(out, key=lambda c: c.key)

    def ids(self) -> list[str]:
        return sorted(self._by_id)

    def assert_unique(self) -> None:
        """No-op guard kept for symmetry; duplicates already raise on register."""
        seen: set[str] = set()
        for contract in self.list():
            if contract.key in seen:
                raise ValueError(f"duplicate prompt key: {contract.key}")
            seen.add(contract.key)


# Global registry, populated by importing the families package.
REGISTRY = PromptRegistry()


def register(contract: PromptContract) -> PromptContract:
    """Register a contract in the global registry."""
    return REGISTRY.register(contract)
