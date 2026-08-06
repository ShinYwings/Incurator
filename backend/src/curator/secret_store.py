"""Local encrypted secret storage for backend-only credentials."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.fernet import Fernet

from . import config as cfg
from . import durable_io


class SecretDecryptionError(durable_io.DurableStateError):
    """A secret is stored under this name but cannot be decrypted here.

    Distinct from "no secret stored". The store is machine-local: the Fernet key
    lives in this machine's global config dir and is never synced, so a config
    that was synced from another device references secret names whose ciphertext
    this machine's key cannot open. Reporting that as a missing API key sends the
    user to re-check an env var that was never the problem.
    """


KEY_FILE = "secret.key"
STORE_FILE = "secrets.json"
DEFAULT_DEEPSEEK_SECRET = "deepseek-api-key"


def _secret_dir() -> Path:
    return cfg.get_global_config_dir() / "secrets"


def _load_fernet() -> Fernet:
    directory = _secret_dir()
    directory.mkdir(parents=True, exist_ok=True)
    key_path = directory / KEY_FILE
    if key_path.exists():
        try:
            key = key_path.read_bytes().strip()
        except OSError as exc:
            raise durable_io.DurableStateError(
                f"secret key is unreadable: {key_path}"
            ) from exc
    else:
        key = Fernet.generate_key()
        durable_io.atomic_write_text(key_path, key.decode("ascii") + "\n", mode=0o600)
    try:
        return Fernet(key)
    except (TypeError, ValueError) as exc:
        raise durable_io.DurableStateError(
            f"secret key is corrupt: {key_path}"
        ) from exc


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
    except (OSError, json.JSONDecodeError) as exc:
        raise durable_io.DurableStateError(
            f"secret store is unreadable or corrupt: {path}"
        ) from exc
    if not isinstance(data, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in data.items()
    ):
        raise durable_io.DurableStateError(
            f"secret store is not a string mapping: {path}"
        )
    return data


def _write_store(data: dict[str, str]) -> None:
    path = _store_path()
    durable_io.atomic_write_text(
        path,
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        mode=0o600,
    )


def set_secret(name: str, value: str) -> str:
    if not name:
        raise ValueError("secret name is required")
    with durable_io.locked_path(_store_path()):
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
    with durable_io.locked_path(_store_path()):
        data = _read_store()
        encoded = data.get(name)
        if not encoded:
            return ""
        try:
            encrypted = base64.urlsafe_b64decode(encoded.encode("ascii"))
            return _load_fernet().decrypt(encrypted).decode("utf-8")
        except durable_io.DurableStateError:
            raise
        except Exception as exc:
            # The name IS present in the store, so this is never "not
            # configured". InvalidToken (wrong/rotated key), a corrupt base64
            # payload, or a non-UTF-8 plaintext all land here.
            raise SecretDecryptionError(
                f"secret '{name}' is stored but cannot be decrypted on this "
                f"machine ({type(exc).__name__}). The encryption key is "
                f"machine-local and is never synced, so a secret set on another "
                f"device must be re-entered here with "
                f"`wiki config provider --api-key <value>`"
            ) from exc


def delete_secret(reference: str) -> bool:
    name = reference.removeprefix("secret:")
    with durable_io.locked_path(_store_path()):
        data = _read_store()
        if name not in data:
            return False
        data.pop(name, None)
        _write_store(data)
        return True


def list_secrets() -> dict[str, str]:
    with durable_io.locked_path(_store_path()):
        names = sorted(_read_store())
    return {f"secret:{name}": mask_secret(f"secret:{name}") for name in names}


def mask_secret(reference: str) -> str:
    try:
        value = get_secret(reference)
    except SecretDecryptionError:
        # Listing every secret must not fail because one of them is
        # undecryptable — but the row has to say so rather than read as empty.
        return "<undecryptable>"
    if not value:
        return ""
    if len(value) <= 8:
        return "********"
    return f"{value[:4]}...{value[-4:]}"
