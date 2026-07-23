"""Registration, login, refresh and ownership isolation."""

from httpx import AsyncClient

CREDENTIALS = {"email": "alice@example.com", "password": "correct-horse-battery"}


async def test_register_returns_token_and_refresh_cookie(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/register", json=CREDENTIALS)

    assert response.status_code == 201, response.text
    assert response.json()["access_token"]
    assert "refresh_token" in response.cookies


async def test_register_rejects_duplicate_email(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=CREDENTIALS)

    response = await client.post("/api/v1/auth/register", json=CREDENTIALS)

    assert response.status_code == 409


async def test_register_rejects_short_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register", json={"email": "b@example.com", "password": "short"}
    )

    assert response.status_code == 422


async def test_login_then_me_round_trip(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=CREDENTIALS)

    login = await client.post("/api/v1/auth/login", json=CREDENTIALS)
    assert login.status_code == 200, login.text

    token = login.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert me.status_code == 200
    assert me.json()["email"] == CREDENTIALS["email"]
    assert me.json()["has_github_token"] is False


async def test_login_with_wrong_password_is_rejected(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=CREDENTIALS)

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": CREDENTIALS["email"], "password": "not-the-password"},
    )

    assert response.status_code == 401


async def test_login_with_unknown_email_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "correct-horse-battery"},
    )

    assert response.status_code == 401


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")

    assert response.status_code == 401


async def test_me_rejects_a_refresh_token_used_as_access_token(
    client: AsyncClient,
) -> None:
    register = await client.post("/api/v1/auth/register", json=CREDENTIALS)
    refresh_token = register.cookies["refresh_token"]

    response = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh_token}"}
    )

    assert response.status_code == 401


async def test_refresh_issues_a_new_access_token(client: AsyncClient) -> None:
    await client.post("/api/v1/auth/register", json=CREDENTIALS)

    response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 200, response.text
    assert response.json()["access_token"]


async def test_refresh_without_cookie_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/refresh")

    assert response.status_code == 401


async def test_preferences_update_persists(auth_client: AsyncClient) -> None:
    response = await auth_client.patch(
        "/api/v1/auth/me",
        json={"llm_model": "qwen2.5-coder:7b-instruct-q4_K_M", "min_severity": "high"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["preferences"]["llm_model"] == "qwen2.5-coder:7b-instruct-q4_K_M"
    assert body["preferences"]["min_severity"] == "high"
