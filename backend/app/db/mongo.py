"""MongoDB connection lifecycle.

Beanie 2.x drives pymongo's native `AsyncMongoClient`; motor is not involved.
"""

from beanie import init_beanie
from pymongo import AsyncMongoClient

from app.config import settings
from app.db.models import DOCUMENT_MODELS

_client: AsyncMongoClient | None = None


async def connect() -> None:
    """Open the client and register document models (creates indexes)."""
    global _client
    _client = AsyncMongoClient(settings.mongo_url, tz_aware=True)
    await init_beanie(
        database=_client[settings.mongo_db_name],
        document_models=list(DOCUMENT_MODELS),
    )


async def disconnect() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def get_client() -> AsyncMongoClient:
    if _client is None:
        raise RuntimeError("MongoDB client is not connected")
    return _client


async def ping() -> bool:
    """Cheap health probe used by /health."""
    try:
        await get_client().admin.command("ping")
    except Exception:
        return False
    return True
