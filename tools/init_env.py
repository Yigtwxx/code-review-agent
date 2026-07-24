"""Bootstrap local env files for the dev start scripts.

Creates the root `.env` from `.env.example` when missing, replaces the
`change-me-in-your-local-env` placeholders with freshly generated secrets, and
writes `frontend/.env.local` so the browser knows where the API lives.

Secrets are generated on this machine and never leave it; both files stay
gitignored. Existing values are never overwritten.
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

PLACEHOLDER = "change-me-in-your-local-env"
ROOT = Path(__file__).resolve().parent.parent


def _generate(key: str) -> str:
    if key == "FERNET_KEY":
        from cryptography.fernet import Fernet

        return Fernet.generate_key().decode()
    return secrets.token_urlsafe(48)


def ensure_backend_env() -> None:
    env_path = ROOT / ".env"
    example_path = ROOT / ".env.example"

    if not env_path.exists():
        if not example_path.exists():
            sys.exit(f"missing {example_path}, cannot create .env")
        env_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
        print("created .env from .env.example")

    out: list[str] = []
    generated: list[str] = []

    for line in env_path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.lstrip().startswith("#") and value.strip() == PLACEHOLDER:
            name = key.strip()
            out.append(f"{name}={_generate(name)}")
            generated.append(name)
        else:
            out.append(line)

    if generated:
        env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
        print(f"generated local secrets for: {', '.join(generated)}")


def ensure_frontend_env(backend_port: str) -> None:
    env_local = ROOT / "frontend" / ".env.local"
    if env_local.exists():
        return
    env_local.write_text(
        f"NEXT_PUBLIC_API_BASE=http://localhost:{backend_port}\n", encoding="utf-8"
    )
    print("created frontend/.env.local")


def main() -> None:
    ensure_backend_env()
    ensure_frontend_env(os.environ.get("BACKEND_PORT", "8001"))


if __name__ == "__main__":
    main()
