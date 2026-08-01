"""Prompt registry: unique, versioned lookup of prompt contracts.

The registry is the single place that knows every prompt the Curator can run.
``assert_unique`` enforces the v0.3.1 rule that prompt ids are unique; a
duplicate registration of the same ``prompt_id@version`` is a defect.
"""

from __future__ import annotations

import re
from typing import List

from .contracts import PromptContract

__all__ = ["PromptRegistry", "REGISTRY", "register"]

_VERSION_RE = re.compile(r"^v([0-9]+(?:\.[0-9]+)*)$")


def _version_key(version: str) -> tuple[int, ...]:
    match = _VERSION_RE.fullmatch(version)
    if match is None:
        raise ValueError(
            f"malformed prompt version: {version!r}; expected v<integer>(.<integer>)*"
        )
    return tuple(int(part) for part in match.group(1).split("."))


class PromptRegistry:
    def __init__(self) -> None:
        # key: prompt_id -> {version: contract}
        self._by_id: dict[str, dict[str, PromptContract]] = {}

    def register(self, contract: PromptContract) -> PromptContract:
        _version_key(contract.version)
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
            latest = max(versions, key=_version_key)
            return versions[latest]
        if version not in versions:
            raise KeyError(f"unknown prompt version: {prompt_id}@{version}")
        return versions[version]

    def list(self, family: str | None = None) -> List[PromptContract]:
        out = []
        for versions in self._by_id.values():
            for contract in versions.values():
                if family is None or contract.family == family:
                    out.append(contract)
        return sorted(out, key=lambda c: (c.prompt_id, _version_key(c.version)))

    def ids(self) -> List[str]:
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
