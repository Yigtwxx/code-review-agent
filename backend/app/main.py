"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import auth, reviews, system, ws
from app.config import settings
from app.db import mongo

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await mongo.connect()
    logger.info("Connected to MongoDB db=%s", settings.mongo_db_name)
    try:
        yield
    finally:
        await mongo.disconnect()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Code Review Agent",
        description=(
            "Multi-agent AI code review and security analysis. "
            "Static analysis cross-validates every LLM finding."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(reviews.router, prefix="/api/v1")
    app.include_router(system.router, prefix="/api/v1")
    app.include_router(ws.router)

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "mongo": await mongo.ping(),
            "llm_model": settings.llm_model,
        }

    return app


app = create_app()
