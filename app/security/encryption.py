from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from pydantic import ValidationError as PydanticValidationError

from app.config.settings import Settings, get_settings


ENCRYPTED_PREFIX = "enc:v1:"


class EncryptionError(RuntimeError):
    """Raised when encrypted application data cannot be handled safely."""


class EncryptionConfigError(EncryptionError):
    """Raised when encryption is enabled but the key is missing or invalid."""


def is_encrypted(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX)


def encrypt_text(value: str | None) -> str | None:
    if value is None:
        return None
    if is_encrypted(value):
        return value
    token = _get_fernet().encrypt(value.encode("utf-8")).decode("ascii")
    return f"{ENCRYPTED_PREFIX}{token}"


def decrypt_text(value: str | None) -> str | None:
    if value is None:
        return None
    if not is_encrypted(value):
        return value
    token = value.removeprefix(ENCRYPTED_PREFIX).encode("ascii")
    try:
        return _get_fernet().decrypt(token).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise EncryptionError("Encrypted value cannot be decrypted") from exc


def encrypt_json(value: dict[str, Any] | None) -> str:
    payload = value or {}
    plaintext = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    encrypted = encrypt_text(plaintext)
    if encrypted is None:
        raise EncryptionError("JSON encryption returned empty ciphertext")
    return encrypted


def decrypt_json(value: str | dict[str, Any] | None) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    plaintext = decrypt_text(value)
    if plaintext is None:
        return {}
    try:
        data = json.loads(plaintext)
    except json.JSONDecodeError as exc:
        raise EncryptionError("Encrypted JSON payload is invalid") from exc
    if not isinstance(data, dict):
        raise EncryptionError("Encrypted JSON payload must be an object")
    return data


@lru_cache
def _get_fernet() -> Fernet:
    return build_fernet(get_settings())


def build_fernet(settings: Settings) -> Fernet:
    if not settings.encryption_enabled:
        raise EncryptionConfigError("Encryption is disabled")
    key = settings.app_encryption_key.strip()
    if not key:
        raise EncryptionConfigError(
            "APP_ENCRYPTION_KEY is required when encryption is enabled"
        )
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, PydanticValidationError) as exc:
        raise EncryptionConfigError("APP_ENCRYPTION_KEY is not a valid Fernet key") from exc
