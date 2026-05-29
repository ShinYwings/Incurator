"""Shared cloud model catalogue for backend and MCP clients."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any


_FALLBACK_MODELS: dict[str, Any] = {
    "schema_version": 1,
    "providers": {
        "antigravity": {
            "backend_key": "antigravity-cli",
            "cli_cmd": "agy",
            "install_cmd": "curl -fsSL https://antigravity.google/cli/install.sh | bash",
            "models": [
                {
                    "id": "gemini-3.5-flash",
                    "label": "Gemini 3.5 Flash",
                    "tier": "flash",
                    "context_window": 1_000_000,
                    "supports_vision": True,
                },
                {
                    "id": "gemini-3.1-flash-lite-preview",
                    "label": "Gemini 3.1 Flash Lite Preview",
                    "tier": "flash",
                    "context_window": 1_000_000,
                    "supports_vision": True,
                },
                {
                    "id": "gemini-3.1-flash-preview",
                    "label": "Gemini 3.1 Flash Preview",
                    "tier": "flash",
                    "context_window": 1_000_000,
                    "supports_vision": True,
                },
                {
                    "id": "gemini-3.1-pro-preview",
                    "label": "Gemini 3.1 Pro Preview",
                    "tier": "think",
                    "context_window": 1_000_000,
                    "supports_vision": True,
                },
                {
                    "id": "gemini-2.5-flash",
                    "label": "Gemini 2.5 Flash",
                    "tier": "flash",
                    "context_window": 1_000_000,
                    "supports_vision": True,
                },
                {
                    "id": "gemini-2.5-pro",
                    "label": "Gemini 2.5 Pro",
                    "tier": "think",
                    "context_window": 1_000_000,
                    "supports_vision": True,
                },
            ],
        },
        "claude": {
            "backend_key": "claude-code",
            "cli_cmd": "claude",
            "install_cmd": "npm install -g @anthropic-ai/claude-code",
            "models": [
                {
                    "id": "claude-sonnet-4-6",
                    "label": "Claude Sonnet 4.6",
                    "tier": "flash",
                    "context_window": 200_000,
                    "supports_vision": True,
                },
                {
                    "id": "claude-haiku-4-5",
                    "label": "Claude Haiku 4.5",
                    "tier": "flash",
                    "context_window": 200_000,
                    "supports_vision": True,
                },
                {
                    "id": "claude-opus-4-7",
                    "label": "Claude Opus 4.7",
                    "tier": "think",
                    "context_window": 200_000,
                    "supports_vision": True,
                },
            ],
        },
        "openai": {
            "backend_key": "codex-cli",
            "cli_cmd": "codex",
            "install_cmd": "npm install -g @openai/codex",
            "models": [
                {
                    "id": "gpt-5.5",
                    "label": "GPT-5.5",
                    "tier": "flash",
                    "context_window": 400_000,
                    "supports_vision": True,
                },
                {
                    "id": "gpt-5.3-codex",
                    "label": "GPT-5.3 Codex",
                    "tier": "think",
                    "context_window": 400_000,
                    "supports_vision": True,
                },
            ],
        },
    },
}


def load_models_catalogue() -> dict[str, Any]:
    """Load bundled models.json, falling back to a baked-in catalogue."""
    try:
        ref = resources.files("curator") / "data" / "models.json"
        with ref.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("providers"):
            return data
    except Exception:
        pass
    return _FALLBACK_MODELS


def get_default_model(provider: str, tier: str = "flash") -> str:
    """Return the first model id for provider/tier from the shared catalogue."""
    data = load_models_catalogue()
    provider_data = data.get("providers", {}).get(provider, {})
    for model in provider_data.get("models", []):
        if model.get("tier") == tier and model.get("id"):
            return str(model["id"])
    return ""


def get_available_models() -> dict[str, list[dict[str, Any]]]:
    """Return provider model lists for client UI rendering."""
    data = load_models_catalogue()
    out: dict[str, list[dict[str, Any]]] = {}
    for provider, info in data.get("providers", {}).items():
        models: list[dict[str, Any]] = []
        for model in info.get("models", []):
            models.append(
                {
                    "id": model.get("id", ""),
                    "label": model.get("label", model.get("id", "")),
                    "tier": model.get("tier", "flash"),
                    "context_window": model.get("context_window"),
                    "supports_vision": bool(model.get("supports_vision", False)),
                }
            )
        out[provider] = models
    return out
