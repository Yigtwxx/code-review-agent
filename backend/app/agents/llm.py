"""Local LLM access.

Every agent call goes through `structured()`, which forces the model to answer
against a Pydantic schema. Free-text answers are never parsed: a schema
violation is a retry, not a best-effort regex.

Determinism is deliberate - a fixed seed and a near-zero temperature mean two
reviews of the same file give the same findings, which is what makes the
benchmark numbers meaningful.
"""

import asyncio
import logging

import httpx
from langchain_ollama import ChatOllama
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

logger = logging.getLogger(__name__)


class LlmUnavailable(RuntimeError):
    """Ollama is not reachable or the requested model is not pulled."""


#: Guards a local runtime that can only serve so many generations at once.
_semaphore = asyncio.Semaphore(settings.max_concurrent_agents)

#: model name -> capability set, from /api/show. Cached: it cannot change
#: while the process runs, and the probe costs a round trip.
_capabilities: dict[str, frozenset[str]] = {}


async def _model_capabilities(model: str) -> frozenset[str]:
    if model in _capabilities:
        return _capabilities[model]
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{settings.ollama_base_url}/api/show", json={"model": model}
            )
            response.raise_for_status()
            caps = frozenset(response.json().get("capabilities") or ())
    except httpx.HTTPError as exc:
        raise LlmUnavailable(f"Cannot query model {model}: {exc}") from exc
    _capabilities[model] = caps
    return caps


async def list_models() -> list[str]:
    """Model names available on the local Ollama instance."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags")
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise LlmUnavailable(f"Ollama is not reachable: {exc}") from exc
    return sorted(model["name"] for model in response.json().get("models", []))


async def _build(model: str, num_ctx: int, num_predict: int) -> ChatOllama:
    kwargs: dict[str, object] = {
        "model": model,
        "base_url": settings.ollama_base_url,
        "temperature": settings.llm_temperature,
        "seed": settings.llm_seed,
        "num_ctx": num_ctx,
        "num_predict": num_predict,
        "client_kwargs": {"timeout": settings.llm_timeout_seconds},
    }
    # Reasoning models burn a lot of tokens thinking before answering. We ask
    # for the answer directly; passing the flag to a model without the
    # capability is an error, so only set it when supported.
    if "thinking" in await _model_capabilities(model):
        kwargs["reasoning"] = False
    return ChatOllama(**kwargs)


@retry(
    stop=stop_after_attempt(settings.llm_max_retries),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((ValueError, httpx.HTTPError, TimeoutError)),
    reraise=True,
)
async def _invoke[M: BaseModel](
    chat: ChatOllama, schema: type[M], messages: list[tuple]
) -> M:
    result = await chat.with_structured_output(schema).ainvoke(messages)
    if not isinstance(result, schema):
        # A model that ignores the schema gets another attempt rather than
        # letting a malformed object leak into the review.
        raise ValueError(f"Model returned {type(result).__name__}, expected {schema}")
    return result


async def structured[M: BaseModel](
    schema: type[M],
    *,
    system: str,
    user: str,
    model: str | None = None,
    num_ctx: int | None = None,
    num_predict: int | None = None,
) -> M:
    """Ask the model for one `schema` instance.

    Raises `LlmUnavailable` when Ollama cannot serve the request at all; other
    failures have already been retried with backoff.
    """
    chosen = model or settings.llm_model
    chat = await _build(
        chosen,
        num_ctx or settings.llm_num_ctx,
        num_predict or settings.llm_num_predict,
    )

    async with _semaphore:
        try:
            return await _invoke(chat, schema, [("system", system), ("human", user)])
        except httpx.ConnectError as exc:
            raise LlmUnavailable(f"Ollama is not reachable: {exc}") from exc
