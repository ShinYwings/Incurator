"""Local encrypted secret storage for backend-only credentials."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet

from . import config as cfg


KEY_FILE = "secret.key"
STORE_FILE = "secrets.json"
DEFAULT_DEEPSEEK_SECRET = "deepseek-api-key"


def _secret_dir() -> Path:
    return cfg.get_global_config_dir() / "secrets"


def _chmod_owner_only(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _load_fernet() -> Fernet:
    directory = _secret_dir()
    directory.mkdir(parents=True, exist_ok=True)
    key_path = directory / KEY_FILE
    if key_path.exists():
        key = key_path.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        key_path.write_bytes(key + b"\n")
        _chmod_owner_only(key_path)
    return Fernet(key)


def _store_path() -> Path:
    directory = _secret_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / STORE_FILE


def _read_store() -> dict[str, str]:
    path = _store_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(k, str)}


def _write_store(data: dict[str, str]) -> None:
    path = _store_path()
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _chmod_owner_only(path)


def set_secret(name: str, value: str) -> str:
    if not name:
        raise ValueError("secret name is required")
    fernet = _load_fernet()
    data = _read_store()
    encrypted = fernet.encrypt(value.encode("utf-8"))
    data[name] = base64.urlsafe_b64encode(encrypted).decode("ascii")
    _write_store(data)
    return f"secret:{name}"


def get_secret(reference: str) -> str:
    name = reference.removeprefix("secret:")
    if not name:
        return ""
    data = _read_store()
    encoded = data.get(name)
    if not encoded:
        return ""
    try:
        encrypted = base64.urlsafe_b64decode(encoded.encode("ascii"))
        return _load_fernet().decrypt(encrypted).decode("utf-8")
    except Exception:
        return ""


def delete_secret(reference: str) -> bool:
    name = reference.removeprefix("secret:")
    data = _read_store()
    if name not in data:
        return False
    data.pop(name, None)
    _write_store(data)
    return True


def list_secrets() -> dict[str, str]:
    return {f"secret:{name}": mask_secret(f"secret:{name}") for name in sorted(_read_store())}


def mask_secret(reference: str) -> str:
    value = get_secret(reference)
    if not value:
        return ""
    if len(value) <= 8:
        return "********"
    return f"{value[:4]}...{value[-4:]}"
