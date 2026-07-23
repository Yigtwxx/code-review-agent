"""Application settings.

Every secret and every tunable comes from the environment - nothing is
hardcoded, and the model name in particular is a setting so that the benchmark
harness can swap models without touching agent code.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent
PROMPTS_DIR = BACKEND_ROOT / "app" / "prompts"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- database ---
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db_name: str = "code_review_agent"

    # --- auth ---
    jwt_secret: str = "insecure-development-secret-replace-me-in-env"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    #: Fernet key protecting per-user GitHub tokens at rest. Empty in dev means
    #: token storage is refused rather than stored in the clear.
    fernet_key: str = ""

    # --- llm (local ollama) ---
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen3.6:35b-a3b"
    llm_temperature: float = 0.1
    llm_seed: int = 42
    llm_num_ctx: int = 16384
    #: Output cap. A runaway generation is a hung review, so this is always set
    #: explicitly rather than left to the model's default.
    llm_num_predict: int = 4096
    #: Refactoring returns a whole file, so it needs a larger output budget.
    llm_refactor_num_predict: int = 8192
    llm_timeout_seconds: int = 300
    llm_max_retries: int = 3

    # --- analysis limits ---
    max_upload_bytes: int = 10 * 1024 * 1024
    max_files_per_review: int = 200
    max_file_bytes: int = 512 * 1024
    #: Agents run concurrently; cap it so a local LLM is not thrashed.
    max_concurrent_agents: int = 3

    # --- integrations ---
    github_token: str = ""
    github_api_url: str = "https://api.github.com"
    ci_shared_secret: str = ""

    # --- app ---
    # NoDecode: take the raw env string and split it ourselves instead of
    # letting pydantic-settings try to JSON-decode a comma-separated list.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    log_level: str = "INFO"

    @field_validator("jwt_secret")
    @classmethod
    def _reject_weak_secret(cls, value: str) -> str:
        # HS256 keys shorter than the 256-bit digest weaken the MAC (RFC 7518 3.2).
        if len(value.encode()) < 32:
            raise ValueError("JWT_SECRET must be at least 32 bytes")
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
