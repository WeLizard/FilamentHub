"""Tests for brands endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand


@pytest.mark.asyncio
async def test_list_brands_empty(client: AsyncClient):
    """Test listing brands when database is empty."""
    response = await client.get("/api/v1/brands/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["page"] == 1
    assert data["size"] == 50


@pytest.mark.asyncio
async def test_create_brand(auth_client: AsyncClient):
    """Test creating a brand."""
    brand_data = {
        "name": "Test Brand",
        "slug": "test-brand",
        "description": "Test description",
        "website": "https://test.com",
        "verified": True,
    }
    response = await auth_client.post("/api/v1/brands/", json=brand_data)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == brand_data["name"]
    assert data["slug"] == brand_data["slug"]
    assert data["verified"] is False
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_get_brand(client: AsyncClient, db_session: AsyncSession):
    """Test getting a brand by ID."""
    # Create brand directly in DB
    brand = Brand(
        name="Test Brand 2",
        slug="test-brand-2",
        verified=False,
        active=True,
    )
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    # Get brand via API
    response = await client.get(f"/api/v1/brands/{brand.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == brand.id
    assert data["name"] == brand.name


@pytest.mark.asyncio
async def test_get_brand_not_found(client: AsyncClient):
    """Test getting non-existent brand."""
    response = await client.get("/api/v1/brands/99999")
    assert response.status_code == 404



@pytest.mark.asyncio
async def test_brand_request_proof_files_are_gated(client: AsyncClient, db_session: AsyncSession):
    """Proof documents are not public via /uploads and are served only to owner/admin."""
    import json

    from sqlalchemy import select

    from app.models.brand_request import BrandRequest, BrandRequestType
    from app.models.user import User
    from app.services.file_service import get_upload_root_dir

    async def register(suffix: str) -> dict[str, str]:
        email = f"{suffix}@example.com"
        resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "username": f"user_{suffix}",
                "password": "testpassword123",
                "role": "user",
            },
        )
        assert resp.status_code == 201
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "testpassword123"},
        )
        return {"Authorization": f"Bearer {login.json()['access_token']}"}

    owner_headers = await register("proof-owner")
    other_headers = await register("proof-other")

    owner = (
        await db_session.execute(
            select(User).where(User.email == "proof-owner@example.com")
        )
    ).scalar_one()

    request = BrandRequest(
        user_id=owner.id,
        request_type=BrandRequestType.CREATE,
        new_brand_name="ProofCo",
        proof_files=json.dumps(["brand_requests/0/proof-test.png"]),
    )
    db_session.add(request)
    await db_session.commit()
    await db_session.refresh(request)

    proof_dir = get_upload_root_dir() / "brand_requests" / str(request.id)
    proof_dir.mkdir(parents=True, exist_ok=True)
    proof_file = proof_dir / "proof-test.png"
    proof_file.write_bytes(b"proof-bytes")

    try:
        # Public static mount must not serve proof documents
        public = await client.get(
            f"/uploads/brand_requests/{request.id}/proof-test.png"
        )
        assert public.status_code == 404

        endpoint = f"/api/v1/brand-requests/{request.id}/proof/proof-test.png"

        anon = await client.get(endpoint)
        assert anon.status_code == 401

        other = await client.get(endpoint, headers=other_headers)
        assert other.status_code == 403

        ok = await client.get(endpoint, headers=owner_headers)
        assert ok.status_code == 200
        assert ok.content == b"proof-bytes"

        traversal = await client.get(
            f"/api/v1/brand-requests/{request.id}/proof/..%2F..%2Fsecret.png",
            headers=owner_headers,
        )
        assert traversal.status_code == 404
    finally:
        proof_file.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_admin_brand_logo_accepts_bmp_and_rejects_disguised_bmp(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
    tmp_path,
):
    """Brand logos are normalized to WebP and BMP uploads are validated by content."""
    from io import BytesIO

    from PIL import Image

    from app.api.v1.endpoints import admin as admin_endpoints
    from app.models.brand import Brand

    monkeypatch.setattr(admin_endpoints, "get_upload_root_dir", lambda: tmp_path)

    brand = Brand(name="Logo BMP Brand", slug="logo-bmp-brand", active=True, verified=False)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    def bmp_bytes(color: tuple[int, int, int]) -> bytes:
        output = BytesIO()
        Image.new("RGB", (300, 150), color).save(output, "BMP")
        return output.getvalue()

    ok = await admin_client.post(
        f"/api/v1/admin/brands/{brand.id}/logo",
        files={"file": ("logo.bmp", bmp_bytes((10, 20, 30)), "image/bmp")},
    )
    assert ok.status_code == 200
    logo_url = ok.json()["logo_url"] or ""
    assert logo_url.endswith(".webp")
    stored_path = tmp_path / "brand_logos" / logo_url.rsplit("/", 1)[-1]
    assert stored_path.exists()
    with Image.open(stored_path) as stored:
        assert stored.format == "WEBP"

    bad = await admin_client.post(
        f"/api/v1/admin/brands/{brand.id}/logo",
        files={"file": ("bad.bmp", b"not really a bmp", "image/bmp")},
    )
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] == "ERR_FILE_CONTENT_MISMATCH"

    active_svg = await admin_client.post(
        f"/api/v1/admin/brands/{brand.id}/logo",
        files={"file": ("active.svg", b"<svg><script>alert(1)</script></svg>", "image/svg+xml")},
    )
    assert active_svg.status_code == 400
    assert active_svg.json()["detail"]["code"] == "ERR_FILE_EXT_NOT_ALLOWED"


def test_validate_file_signature_rejects_content_ext_mismatch():
    """Uploads must match their extension by magic bytes, not just the name."""
    from fastapi import HTTPException

    from app.services.file_service import validate_file_signature

    # Correct signatures pass
    validate_file_signature(".png", b"\x89PNG\r\n\x1a\n....")
    validate_file_signature(".pdf", b"%PDF-1.7\n....")
    validate_file_signature(".jpg", b"\xff\xd8\xff\xe0....")
    validate_file_signature(".docx", b"PK\x03\x04....")

    # Executable renamed to .png is rejected
    with pytest.raises(HTTPException) as exc:
        validate_file_signature(".png", b"MZ\x90\x00 this is a PE binary")
    assert exc.value.detail["code"] == "ERR_FILE_CONTENT_MISMATCH"

    # HTML smuggled as .pdf is rejected
    with pytest.raises(HTTPException) as exc:
        validate_file_signature(".pdf", b"<html><script>alert(1)</script>")
    assert exc.value.detail["code"] == "ERR_FILE_CONTENT_MISMATCH"
