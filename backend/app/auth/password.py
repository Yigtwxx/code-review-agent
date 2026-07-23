"""Password hashing (argon2 via pwdlib)."""

from pwdlib import PasswordHash

_hasher = PasswordHash.recommended()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time verification; never raises on malformed hashes."""
    try:
        return _hasher.verify(plain, hashed)
    except Exception:
        return False
