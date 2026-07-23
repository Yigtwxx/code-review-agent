"""Symmetric encryption for user-supplied third-party tokens.

GitHub tokens are stored as Fernet ciphertext. If no key is configured we
refuse to store rather than silently persisting a credential in the clear.
"""

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class SecretStorageUnavailable(Exception):
    """FERNET_KEY is not configured, so secrets must not be persisted."""


def _fernet() -> Fernet:
    if not settings.fernet_key:
        raise SecretStorageUnavailable(
            "FERNET_KEY is not set; refusing to store a credential unencrypted"
        )
    return Fernet(settings.fernet_key.encode())


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(ciphertext: str) -> str | None:
    """Return the plaintext, or None if the key changed or data is corrupt."""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, SecretStorageUnavailable, ValueError):
        return None
