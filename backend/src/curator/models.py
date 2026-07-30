"""Shared cloud model catalogue for backend and MCP clients.

`data/models.json` is the single source of truth for the model catalogue.
Edit that file to add/change models — no Python changes are needed. The
critical default-model strings also have last-resort fallbacks in `llm.py`
(`get_default_model(...) or "..."`), so the system still starts even if the
data file is somehow unavailable.
"""

from __future__ import annotations

import json
import logging
from importlib import resources
from typing import Any

_log = logging.getLogger(__name__)

# Emergency stub used only if data/models.json cannot be read. Intentionally
# empty: callers degrade gracefully (get_default_model → "", which llm.py
# covers with hardcoded last-resort strings; get_available_models → {}).
_EMPTY_CATALOGUE: dict[str, Any] = {"schema_version": 1, "providers": {}}


def load_models_catalogue() -> dict[str, Any]:
    """Load the bundled models.json (the single source of truth)."""
    try:
        ref = resources.files("curator") / "data" / "models.json"
        with ref.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("providers"):
            return data
        _log.warning("models.json is malformed (no providers); using empty catalogue")
    except Exception as exc:
        _log.warning("Could not load models.json (%s); using empty catalogue", exc)
    return _EMPTY_CATALOGUE


def get_default_model(provider: str) -> str:
    """Return the first model id for provider from the shared catalogue."""
    data = load_models_catalogue()
    provider_data = data.get("providers", {}).get(provider, {})
    for model in provider_data.get("models", []):
        if model.get("id"):
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
                    "context_window": model.get("context_window"),
                    "supports_vision": bool(model.get("supports_vision", False)),
                    "supports_thinking": bool(model.get("supports_thinking", False)),
                    # Reasoning/effort levels the underlying CLI accepts for this
                    # model (e.g. claude --effort, codex -c model_reasoning_effort).
                    # Empty list means the model has no selectable effort dimension.
                    "efforts": list(model.get("efforts", []) or []),
                    "default_effort": str(model.get("default_effort", "") or ""),
                }
            )
        out[provider] = models
    return out


def get_model_efforts(provider: str, model_id: str) -> list[str]:
    """Return the allowed effort levels for a provider/model, or [] if none."""
    data = load_models_catalogue()
    for model in data.get("providers", {}).get(provider, {}).get("models", []):
        if model.get("id") == model_id:
            return list(model.get("efforts", []) or [])
    return []


def get_backend_model_efforts(backend_key: str, model_id: str) -> list[str]:
    """Return effort levels for a persisted backend-key/model pair."""
    data = load_models_catalogue()
    for provider in data.get("providers", {}).values():
        if provider.get("backend_key") != backend_key:
            continue
        for model in provider.get("models", []):
            if model.get("id") == model_id:
                return list(model.get("efforts", []) or [])
        return []
    return []


def get_default_effort(provider: str, model_id: str) -> str:
    """Return the default effort for a provider/model, or '' if none."""
    data = load_models_catalogue()
    for model in data.get("providers", {}).get(provider, {}).get("models", []):
        if model.get("id") == model_id:
            default = str(model.get("default_effort", "") or "")
            if default:
                return default
            efforts = list(model.get("efforts", []) or [])
            return efforts[0] if efforts else ""
    return ""
