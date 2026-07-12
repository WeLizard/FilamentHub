"""Tests for QR backfill on brand verification.

Materials created before a brand is verified (by users or the brand itself)
get their QR codes when the brand becomes verified or the brand triggers a
backfill. A pre-existing code is never overwritten.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.services import qr_service
from app.services.qr_service import backfill_brand_qr_codes


async def _brand_with_filaments(db: AsyncSession, *, verified: bool, tag: str) -> Brand:
    brand = Brand(name=f"BF {tag}", slug=f"bf-{tag}", active=True, verified=verified)
    db.add(brand)
    await db.flush()
    for i in range(2):
        db.add(Filament(
            brand_id=brand.id, name=f"BF {tag} {i}", slug=f"bf-{tag}-{i}",
            material_type="PLA", active=True,
        ))
    db.add(Filament(
        brand_id=brand.id, name=f"BF {tag} has", slug=f"bf-{tag}-has",
        material_type="PLA", active=True, qr_code=f"already-{tag}",
    ))
    await db.commit()
    await db.refresh(brand)
    return brand


@pytest.mark.asyncio
async def test_backfill_assigns_only_missing(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr(qr_service, "save_qr_code_image", lambda *a, **k: [])
    brand = await _brand_with_filaments(db_session, verified=True, tag="v")

    assigned = await backfill_brand_qr_codes(brand, db_session)
    await db_session.commit()

    assert assigned == 2
    still_missing = await db_session.scalar(
        select(Filament.id).where(Filament.brand_id == brand.id, Filament.qr_code.is_(None))
    )
    assert still_missing is None
    # Pre-existing code untouched.
    kept = await db_session.scalar(
        select(Filament.qr_code).where(Filament.slug == "bf-v-has")
    )
    assert kept == "already-v"


@pytest.mark.asyncio
async def test_backfill_noop_for_unverified(db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr(qr_service, "save_qr_code_image", lambda *a, **k: [])
    brand = await _brand_with_filaments(db_session, verified=False, tag="u")
    assert await backfill_brand_qr_codes(brand, db_session) == 0


@pytest.mark.asyncio
async def test_backfill_endpoint_forbidden_for_non_owner(client: AsyncClient, db_session: AsyncSession):
    brand = Brand(name="Other Brand", slug="other-brand", active=True, verified=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    email, password = "qr-backfill@example.com", "testpassword123"
    await client.post("/api/v1/auth/register", json={
        "email": email, "username": "qr_backfill", "password": password, "role": "user",
    })
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.post(f"/api/v1/brands/{brand.id}/backfill-qr", headers=headers)
    assert response.status_code == 403
