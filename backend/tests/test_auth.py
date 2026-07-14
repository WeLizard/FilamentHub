"""Tests for authentication endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.brand import Brand
from app.models.user import User
from app.services.organization_access import grant_brand_owner_membership


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
async def test_profile_update_cannot_assign_arbitrary_brand(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    """The generic profile endpoint must never grant or select brand access."""
    brand = Brand(name="Protected Brand", slug="protected-brand", active=True, verified=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    response = await auth_client.patch("/api/v1/auth/me", json={"brand_id": brand.id})
    assert response.status_code == 200
    assert response.json()["brand_id"] is None
    await db_session.refresh(auth_user)
    assert auth_user.brand_id is None


@pytest.mark.asyncio
async def test_active_brand_requires_membership_and_lists_granted_brands(
    auth_client: AsyncClient,
    auth_user: User,
    admin_user: User,
    db_session: AsyncSession,
):
    """Active brand is a scoped workspace choice, not an authorization grant."""
    allowed = Brand(name="Allowed Brand", slug="allowed-brand", active=True, verified=True)
    denied = Brand(name="Denied Brand", slug="denied-brand", active=True, verified=True)
    db_session.add_all([allowed, denied])
    await db_session.flush()
    await grant_brand_owner_membership(
        db_session,
        brand=allowed,
        user=auth_user,
        granted_by_id=admin_user.id,
    )
    await db_session.commit()

    denied_response = await auth_client.put(
        "/api/v1/auth/me/active-brand",
        json={"brand_id": denied.id},
    )
    assert denied_response.status_code == 403

    brands_response = await auth_client.get("/api/v1/auth/me/brands")
    assert brands_response.status_code == 200
    assert [item["brand_id"] for item in brands_response.json()] == [allowed.id]
    assert brands_response.json()[0]["membership_role"] == "owner"

    selected = await auth_client.put(
        "/api/v1/auth/me/active-brand",
        json={"brand_id": allowed.id},
    )
    assert selected.status_code == 200
    assert selected.json()["brand_id"] == allowed.id

    cleared = await auth_client.put(
        "/api/v1/auth/me/active-brand",
        json={"brand_id": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["brand_id"] is None


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


@pytest.mark.asyncio
async def test_upload_avatar(client: AsyncClient, monkeypatch, tmp_path):
    """Avatar uploads are decoded, normalized to WebP and replace the old file."""
    from io import BytesIO
    import struct

    from PIL import Image

    from app.services import file_service

    monkeypatch.setattr(file_service, "get_upload_root_dir", lambda: tmp_path)
    user_data = {
        "email": "avatar@example.com",
        "username": "avataruser",
        "password": "password123",
        "role": "user",
    }
    await client.post("/api/v1/auth/register", json=user_data)
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": user_data["email"], "password": user_data["password"]},
    )
    token = login.json()["access_token"]

    def png_bytes(color: tuple[int, int, int]) -> bytes:
        output = BytesIO()
        Image.new("RGB", (640, 320), color).save(output, "PNG")
        return output.getvalue()

    def bmp_bytes(color: tuple[int, int, int]) -> bytes:
        output = BytesIO()
        Image.new("RGB", (640, 320), color).save(output, "BMP")
        return output.getvalue()

    def oversized_bmp_bytes(width: int, height: int) -> bytes:
        output = BytesIO()
        Image.new("RGB", (1, 1), (0, 0, 0)).save(output, "BMP")
        data = bytearray(output.getvalue())
        struct.pack_into("<I", data, 18, width)
        struct.pack_into("<I", data, 22, height)
        return bytes(data)

    resp = await client.post(
        "/api/v1/auth/me/avatar",
        files={"file": ("a.bmp", bmp_bytes((255, 0, 0)), "image/bmp")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    first_url = resp.json().get("avatar_url") or ""
    assert first_url.startswith("/uploads/avatars/")
    assert first_url.endswith(".webp")
    first_path = tmp_path / "avatars" / first_url.rsplit("/", 1)[-1]
    assert first_path.exists()
    with Image.open(first_path) as stored:
        assert stored.format == "WEBP"
        assert stored.size == (256, 256)

    oversize = await client.post(
        "/api/v1/auth/me/avatar",
        files={"file": ("too-big.bmp", oversized_bmp_bytes(5001, 5000), "image/bmp")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert oversize.status_code == 400
    assert oversize.json()["detail"]["code"] == "ERR_FILE_SIZE_EXCEEDED"
    assert first_path.exists()

    disguised = await client.post(
        "/api/v1/auth/me/avatar",
        files={"file": ("payload.png", b"<script>alert(1)</script>", "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert disguised.status_code == 400
    assert disguised.json()["detail"]["code"] == "ERR_FILE_CONTENT_MISMATCH"
    assert first_path.exists()

    replaced = await client.post(
        "/api/v1/auth/me/avatar",
        files={"file": ("b.png", png_bytes((0, 0, 255)), "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert replaced.status_code == 200
    second_url = replaced.json()["avatar_url"]
    second_path = tmp_path / "avatars" / second_url.rsplit("/", 1)[-1]
    assert second_path.exists()
    assert not first_path.exists()


@pytest.mark.asyncio
async def test_oauth_callback_validates_state(client: AsyncClient, monkeypatch):
    """OAuth callback must accept only the state issued to this browser (CSRF)."""
    from app.api.v1.endpoints import auth as auth_module
    from app.services.oauth_service import OAuthUserInfo

    monkeypatch.setattr(auth_module, "is_provider_configured", lambda provider: True)
    monkeypatch.setattr(
        auth_module,
        "get_google_auth_url",
        lambda state: f"https://accounts.google.com/o/oauth2/auth?state={state}",
    )

    async def fake_exchange(code: str) -> OAuthUserInfo:
        return OAuthUserInfo(
            provider="google",
            provider_id="g-123",
            email="oauth-state@example.com",
            name="OAuth User",
            email_verified=True,
        )

    monkeypatch.setattr(auth_module, "exchange_google_code", fake_exchange)

    # No state cookie at all -> rejected
    no_cookie = await client.post(
        "/api/v1/auth/oauth/google/callback",
        json={"code": "any-code", "state": "forged-state"},
    )
    assert no_cookie.status_code == 401
    assert no_cookie.json()["detail"]["code"] == "ERR_OAUTH_INVALID_STATE"

    # Issue a real state (server sets the HttpOnly cookie on this client)
    url_resp = await client.get("/api/v1/auth/oauth/google/url")
    assert url_resp.status_code == 200
    issued_state = url_resp.json()["state"]

    # Cookie present but state forged -> rejected
    mismatch = await client.post(
        "/api/v1/auth/oauth/google/callback",
        json={"code": "any-code", "state": "forged-state"},
    )
    assert mismatch.status_code == 401
    assert mismatch.json()["detail"]["code"] == "ERR_OAUTH_INVALID_STATE"

    # Matching state -> flow proceeds, user is created and logged in
    ok = await client.post(
        "/api/v1/auth/oauth/google/callback",
        json={"code": "any-code", "state": issued_state},
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]


@pytest.mark.asyncio
async def test_plugin_session_is_short_lived_and_endpoint_scoped(
    auth_client: AsyncClient,
    auth_user,
):
    """Plugin capability must never become a replacement account access token."""
    from app.core.security import create_plugin_token, decode_plugin_token

    issued = await auth_client.post("/api/v1/auth/plugin-session", json={})
    assert issued.status_code == 200
    assert issued.headers["Cache-Control"] == "no-store"
    payload = issued.json()
    assert payload["expires_in"] == settings.PLUGIN_TOKEN_EXPIRE_MINUTES * 60
    assert "refresh_token" not in payload

    plugin_token = payload["plugin_token"]
    decoded = decode_plugin_token(plugin_token)
    assert decoded is not None
    assert decoded["user_id"] == auth_user.id
    assert set(decoded["scopes"]) == {"presets:read", "presets:write"}
    plugin_headers = {"Authorization": f"Bearer {plugin_token}"}

    regular_api = await auth_client.get("/api/v1/auth/me", headers=plugin_headers)
    assert regular_api.status_code == 401

    plugin_read = await auth_client.get(
        "/api/v1/auth/my-presets",
        headers=plugin_headers,
    )
    assert plugin_read.status_code == 200

    plugin_write = await auth_client.post(
        "/api/v1/orcaslicer/filaments/import",
        headers=plugin_headers,
        json={"profiles": []},
    )
    assert plugin_write.status_code == 200

    read_only_token = create_plugin_token(
        {"sub": auth_user.email, "user_id": auth_user.id},
        ["presets:read"],
    )
    denied_write = await auth_client.post(
        "/api/v1/orcaslicer/filaments/import",
        headers={"Authorization": f"Bearer {read_only_token}"},
        json={"profiles": []},
    )
    assert denied_write.status_code == 403
    assert denied_write.json()["detail"]["code"] == "ERR_ACCESS_DENIED"
