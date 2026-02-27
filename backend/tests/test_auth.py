"""Tests for authentication endpoints."""

import pytest
from httpx import AsyncClient

from app.core.config import settings


@pytest.mark.asyncio
async def test_register_user(client: AsyncClient):
    """Test user registration."""
    user_data = {
        "email": "test@example.com",
        "username": "testuser",
        "password": "testpassword123",
        "role": "user",
    }
    response = await client.post("/api/v1/auth/register", json=user_data)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == user_data["email"]
    assert data["username"] == user_data["username"]
    assert "password" not in data  # Password should not be in response
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient):
    """Test registering with duplicate email."""
    user_data = {
        "email": "duplicate@example.com",
        "username": "user1",
        "password": "password123",
        "role": "user",
    }
    # First registration
    response = await client.post("/api/v1/auth/register", json=user_data)
    assert response.status_code == 201
    
    # Try to register again with same email
    user_data["username"] = "user2"  # Different username
    response = await client.post("/api/v1/auth/register", json=user_data)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ERR_EMAIL_EXISTS"


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    """Test user login."""
    # Register first
    user_data = {
        "email": "login@example.com",
        "username": "loginuser",
        "password": "loginpassword123",
        "role": "user",
    }
    await client.post("/api/v1/auth/register", json=user_data)
    
    # Login
    login_data = {
        "email": user_data["email"],
        "password": user_data["password"],
    }
    response = await client.post("/api/v1/auth/login", json=login_data)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["access_token"] is not None


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    """Test login with wrong password."""
    # Register first
    user_data = {
        "email": "wrongpass@example.com",
        "username": "wrongpassuser",
        "password": "correctpassword123",
        "role": "user",
    }
    await client.post("/api/v1/auth/register", json=user_data)
    
    # Try to login with wrong password
    login_data = {
        "email": user_data["email"],
        "password": "wrongpassword",
    }
    response = await client.post("/api/v1/auth/login", json=login_data)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user(client: AsyncClient):
    """Test getting current user info."""
    # Register and login
    user_data = {
        "email": "currentuser@example.com",
        "username": "currentuser",
        "password": "password123",
        "role": "user",
    }
    await client.post("/api/v1/auth/register", json=user_data)
    
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    token = login_response.json()["access_token"]
    
    # Get current user
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == user_data["email"]
    assert data["username"] == user_data["username"]


@pytest.mark.asyncio
async def test_cookie_auth_login_and_me_in_dual_mode(client: AsyncClient, monkeypatch):
    """Cookie auth should work in dual mode without Authorization header."""
    monkeypatch.setattr(settings, "AUTH_WEB_MODE", "dual")

    user_data = {
        "email": "cookie-dual@example.com",
        "username": "cookie_dual_user",
        "password": "password123",
        "role": "user",
    }
    register_response = await client.post("/api/v1/auth/register", json=user_data)
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    assert login_response.status_code == 200
    assert settings.AUTH_ACCESS_COOKIE_NAME in login_response.headers.get("set-cookie", "")

    me_response = await client.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["email"] == user_data["email"]


@pytest.mark.asyncio
async def test_cookie_auth_requires_csrf_for_mutation(client: AsyncClient, monkeypatch):
    """Mutating requests with cookie auth must provide matching CSRF header."""
    monkeypatch.setattr(settings, "AUTH_WEB_MODE", "dual")

    user_data = {
        "email": "csrf@example.com",
        "username": "csrf_user",
        "password": "password123",
        "role": "user",
    }
    register_response = await client.post("/api/v1/auth/register", json=user_data)
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    assert login_response.status_code == 200

    no_csrf_response = await client.patch(
        "/api/v1/auth/me/settings",
        json={"allow_print_profiles_export": False},
    )
    assert no_csrf_response.status_code == 403

    csrf_token = client.cookies.get(settings.AUTH_CSRF_COOKIE_NAME)
    assert csrf_token is not None

    with_csrf_response = await client.patch(
        "/api/v1/auth/me/settings",
        json={"allow_print_profiles_export": False},
        headers={settings.AUTH_CSRF_HEADER_NAME: csrf_token},
    )
    assert with_csrf_response.status_code == 200
    assert with_csrf_response.json()["allow_print_profiles_export"] is False


@pytest.mark.asyncio
async def test_legacy_bearer_still_works_in_dual_mode(client: AsyncClient, monkeypatch):
    """Legacy Bearer flow must remain valid when dual mode is enabled."""
    monkeypatch.setattr(settings, "AUTH_WEB_MODE", "dual")

    user_data = {
        "email": "legacy-dual@example.com",
        "username": "legacy_dual_user",
        "password": "password123",
        "role": "user",
    }
    register_response = await client.post("/api/v1/auth/register", json=user_data)
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == user_data["email"]


@pytest.mark.asyncio
async def test_logout_revokes_legacy_access_token(client: AsyncClient):
    """After logout, previously issued access token should be rejected."""
    user_data = {
        "email": "revoke@example.com",
        "username": "revoke_user",
        "password": "password123",
        "role": "user",
    }
    register_response = await client.post("/api/v1/auth/register", json=user_data)
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    refresh_token = login_response.json()["refresh_token"]

    logout_response = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout_response.status_code == 204

    me_response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == 401


@pytest.mark.asyncio
async def test_cookie_refresh_requires_csrf_in_dual_mode(client: AsyncClient, monkeypatch):
    """Cookie refresh should reject request without CSRF token in dual mode."""
    monkeypatch.setattr(settings, "AUTH_WEB_MODE", "dual")

    user_data = {
        "email": "cookie-refresh-csrf@example.com",
        "username": "cookie_refresh_csrf_user",
        "password": "password123",
        "role": "user",
    }
    register_response = await client.post("/api/v1/auth/register", json=user_data)
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    assert login_response.status_code == 200

    no_csrf_refresh = await client.post("/api/v1/auth/refresh")
    assert no_csrf_refresh.status_code == 403

    csrf_token = client.cookies.get(settings.AUTH_CSRF_COOKIE_NAME)
    assert csrf_token is not None
    with_csrf_refresh = await client.post(
        "/api/v1/auth/refresh",
        headers={settings.AUTH_CSRF_HEADER_NAME: csrf_token},
    )
    assert with_csrf_refresh.status_code == 200
    assert "access_token" in with_csrf_refresh.json()


@pytest.mark.asyncio
async def test_legacy_refresh_body_still_works_in_dual_mode(client: AsyncClient, monkeypatch):
    """Legacy refresh with body token must stay valid in dual mode."""
    monkeypatch.setattr(settings, "AUTH_WEB_MODE", "dual")

    user_data = {
        "email": "legacy-refresh@example.com",
        "username": "legacy_refresh_user",
        "password": "password123",
        "role": "user",
    }
    register_response = await client.post("/api/v1/auth/register", json=user_data)
    assert register_response.status_code == 201

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    assert login_response.status_code == 200
    refresh_token = login_response.json()["refresh_token"]
    assert refresh_token

    refresh_response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_response.status_code == 200
    assert "access_token" in refresh_response.json()
