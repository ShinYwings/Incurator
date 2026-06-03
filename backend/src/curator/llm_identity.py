import base64
import json
import os
from pathlib import Path

from . import constants as consts


def _decode_jwt_claims(token: str) -> dict:
    """Decode the payload of a JWT token and return its claims."""
    if not token or "." not in token:
        return {}
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    # Add base64 padding
    payload += "=" * (4 - len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return {}


def get_llm_account_info(provider_key: str) -> dict:
    """Read local credentials for the given provider and return account info.
    
    Returns:
        A dict with "email", "name", and "provider" keys.
        email and name may be None if not found or not applicable.
    """
    info = {"provider": provider_key, "email": None, "name": None}
    
    if provider_key == consts.BACKEND_OLLAMA:
        info["name"] = "Local (no account)"
        return info
        
    if provider_key == consts.BACKEND_DEEPSEEK_API:
        info["name"] = "API key configured"
        return info

    if provider_key == consts.BACKEND_CLAUDE_CODE:
        # Claude Code manages its auth via keychain/internal SQLite
        # and does not expose email in plain text JSON config.
        info["name"] = "Authenticated (CLI-managed)"
        return info

    if provider_key == consts.BACKEND_ANTIGRAVITY_CLI:
        # Read ~/.gemini/oauth_creds.json
        creds_path = Path.home() / ".gemini" / "oauth_creds.json"
        if creds_path.exists():
            try:
                with creds_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                id_token = data.get("id_token")
                if id_token:
                    claims = _decode_jwt_claims(id_token)
                    info["email"] = claims.get("email")
                    info["name"] = claims.get("name")
            except Exception:
                pass
        if not info["name"] and not info["email"]:
            info["name"] = "Authenticated"
        return info

    if provider_key == consts.BACKEND_CODEX_CLI:
        # Read ~/.codex/auth.json or ~/.config/codex/auth.json
        paths = [
            Path.home() / ".codex" / "auth.json",
            Path.home() / ".config" / "codex" / "auth.json",
        ]
        auth_file = next((p for p in paths if p.exists()), None)
        if auth_file:
            try:
                with auth_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                tokens = data.get("tokens")
                id_token = None
                if isinstance(tokens, dict):
                    id_token = tokens.get("id_token")
                elif isinstance(tokens, str):
                    # Sometimes the whole tokens string is a single token
                    id_token = tokens
                
                if id_token:
                    claims = _decode_jwt_claims(id_token)
                    info["email"] = claims.get("email")
                    info["name"] = claims.get("name")
            except Exception:
                pass
        if not info["name"] and not info["email"]:
            info["name"] = "Authenticated"
        return info

    info["name"] = "Unknown"
    return info
