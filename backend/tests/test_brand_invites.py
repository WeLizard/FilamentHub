"""Tests for the brand invitation flow."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_brand_invite_flow(admin_client: AsyncClient):
    """Admin issues an invite, accepts it, a verified brand is created, token burns.

    Uses a single client because admin_client/auth_client share one underlying
    client object and would clobber each other's auth header.
    """
    created = await admin_client.post(
        "/api/v1/admin/brand-invites",
        json={"email": "brand@example.com", "brand_name": "Inv Brand", "expires_days": 7},
    )
    assert created.status_code == 201
    token = created.json()["token"]
    assert created.json()["invite_url"].endswith(token)

    public = await admin_client.get(f"/api/v1/brand-invites/{token}")
    assert public.status_code == 200
    assert public.json()["valid"] is True
    assert public.json()["brand_name"] == "Inv Brand"

    accept = await admin_client.post(
        f"/api/v1/brand-invites/{token}/accept", json={"brand_name": "Inv Brand"}
    )
    assert accept.status_code == 200
    assert accept.json()["brand_name"] == "Inv Brand"
    assert accept.json()["brand_id"] > 0

    # Token is single-use: now invalid, and re-accepting fails.
    public_after = await admin_client.get(f"/api/v1/brand-invites/{token}")
    assert public_after.json()["valid"] is False

    again = await admin_client.post(
        f"/api/v1/brand-invites/{token}/accept", json={"brand_name": "Inv Brand"}
    )
    assert again.status_code == 400


@pytest.mark.asyncio
async def test_brand_invite_requires_admin(auth_client: AsyncClient):
    """A non-admin cannot create invites."""
    resp = await auth_client.post("/api/v1/admin/brand-invites", json={"email": "x@example.com"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_brand_invite_transliterates_cyrillic_brand_slug(admin_client: AsyncClient):
    created = await admin_client.post(
        "/api/v1/admin/brand-invites",
        json={"email": "nit@example.com", "brand_name": "НИТ", "expires_days": 7},
    )
    assert created.status_code == 201

    accepted = await admin_client.post(
        f"/api/v1/brand-invites/{created.json()['token']}/accept",
        json={"brand_name": "НИТ"},
    )
    assert accepted.status_code == 200

    brand = await admin_client.get(f"/api/v1/brands/{accepted.json()['brand_id']}")
    assert brand.status_code == 200
    assert brand.json()["slug"] == "nit"


@pytest.mark.asyncio
async def test_brand_invite_unknown_token(admin_client: AsyncClient):
    """An unknown token reports invalid, not a server error."""
    resp = await admin_client.get("/api/v1/brand-invites/nope-nope-nope")
    assert resp.status_code == 200
    assert resp.json()["valid"] is False
