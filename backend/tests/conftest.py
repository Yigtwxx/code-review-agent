"""Shared test fixtures.

Tests run against a real MongoDB (the one from docker-compose) but in a
throwaway database, so index behaviour and unique constraints are exercised for
real rather than mocked away.
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient

from app.config import settings
from app.db import mongo
from app.main import create_app

TEST_DB = "code_review_agent_test"


@pytest.fixture(autouse=True, scope="session")
def _use_test_database() -> None:
    settings.mongo_db_name = TEST_DB


@pytest.fixture
async def db() -> AsyncIterator[None]:
    """Fresh database per test."""
    admin = AsyncMongoClient(settings.mongo_url)
    await admin.drop_database(TEST_DB)
    await admin.close()

    await mongo.connect()
    try:
        yield
    finally:
        await mongo.disconnect()


@pytest.fixture
async def client(db: None) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
async def auth_client(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    """Client already registered and carrying an access token."""
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "dev@example.com", "password": "correct-horse-battery"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    yield client
