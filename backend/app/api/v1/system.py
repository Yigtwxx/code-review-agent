"""Capability endpoints: which models and analysers this instance can use."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.agents.llm import LlmUnavailable, list_models
from app.config import settings
from app.static_analysis import eslint_tool

router = APIRouter(prefix="/system", tags=["system"])


class Capabilities(BaseModel):
    default_model: str
    available_models: list[str]
    ollama_reachable: bool
    #: Analysers that will actually run, so the UI can be honest about coverage.
    static_analysers: list[str]
    max_upload_mb: int
    max_files_per_review: int


@router.get("/capabilities")
async def capabilities() -> Capabilities:
    try:
        models = await list_models()
        reachable = True
    except LlmUnavailable:
        models = []
        reachable = False

    analysers = ["ruff", "bandit", "secret-scanner", "tree-sitter", "dependency-check"]
    if eslint_tool.ESLINT_BIN.exists():
        analysers.append("eslint")

    return Capabilities(
        default_model=settings.llm_model,
        available_models=models,
        ollama_reachable=reachable,
        static_analysers=sorted(analysers),
        max_upload_mb=settings.max_upload_bytes // 1024 // 1024,
        max_files_per_review=settings.max_files_per_review,
    )
