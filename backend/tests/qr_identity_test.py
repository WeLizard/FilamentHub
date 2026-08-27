"""QR envelope, ownership, lifecycle, and compact batch contract tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.brand import Brand
from app.models.brand_territorial_grant import (
    BrandTerritorialGrant,
    GrantSource,
    GrantStatus,
)
from app.models.filament import Filament
from app.models.organization import Organization, OrganizationMembership
from app.models.qr_identity import (
    QrManufacturerBatch,
    QrManufacturerBatchItem,
    QrManufacturerInstanceState,
    QrUserSpoolBinding,
)
from app.models.user import User
from app.models.user_spool import UserSpool, UserSpoolState
from app.services.qr_identity_service import (
    QR_MAX_SHORT_CODE_LENGTH,
    encode_qr_envelope,
    parse_qr_envelope,
    purge_expired_user_qr_bindings,
)
from tests.conftest import accepted_legal


async def _catalog_spool(
    db: AsyncSession,
    *,
    user: User,
    suffix: str,
) -> tuple[Filament, UserSpool]:
    brand = Brand(
        name=f"QR Identity Brand {suffix}",
        slug=f"qr-identity-brand-{suffix}",
        active=True,
        verified=True,
    )
    db.add(brand)
    await db.flush()
    filament = Filament(
        brand_id=brand.id,
        name=f"QR Identity Filament {suffix}",
        slug=f"qr-identity-filament-{suffix}",
        material_type="PETG",
        active=True,
        qr_code=f"FH-{suffix.upper()}",
    )
    db.add(filament)
    await db.flush()
    spool = UserSpool(
        user_id=user.id,
        filament_id=filament.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.shelf,
        source="manual",
    )
    db.add(spool)
    await db.commit()
    await db.refresh(filament)
    await db.refresh(spool)
    return filament, spool


async def _second_user(db: AsyncSession, suffix: str) -> tuple[User, str]:
    user = User(
        email=f"qr-{suffix}@example.com",
        username=f"qr_{suffix}",
        password_hash="unused",
        active=True,
        email_verified=True,
        **accepted_legal(),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, create_access_token({"sub": user.email})


def test_versioned_envelope_keeps_product_code_independently_decodable():
    token = "A" * 22
    code = encode_qr_envelope("FH-001", "U", token)
    parsed = parse_qr_envelope(code)

    assert parsed is not None
    assert parsed.product_code == "FH-001"
    assert parsed.namespace == "U"
    assert parsed.token == token
    assert len(code) <= QR_MAX_SHORT_CODE_LENGTH
    assert parse_qr_envelope("FH-001") is None


def test_versioned_envelope_decodes_with_and_without_filamenthub_mark():
    import cv2
    import numpy as np
    from PIL import Image

    from app.services.qr_service import (
        _qr_target_url,
        generate_branded_qr_code_image,
        generate_qr_code_image,
    )

    code = encode_qr_envelope("FH-MFG-001", "M", "A" * 32)
    expected = _qr_target_url(code)
    detector = cv2.QRCodeDetector()

    for renderer in (generate_qr_code_image, generate_branded_qr_code_image):
        master = Image.open(renderer(code, size=600)).convert("L")
        for size in (600, 120):
            rendered = np.array(master.resize((size, size), Image.Resampling.LANCZOS))
            assert detector.detectAndDecode(rendered)[0] == expected, (
                renderer.__name__,
                size,
                len(code),
            )


@pytest.mark.asyncio
async def test_user_qr_is_idempotent_private_and_degrades_to_product_after_rotation(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    filament, spool = await _catalog_spool(db_session, user=auth_user, suffix="USER1")

    issued = await auth_client.post(f"/api/v1/spools/{spool.id}/qr/issue")
    reprint = await auth_client.post(f"/api/v1/spools/{spool.id}/qr/issue")
    assert issued.status_code == reprint.status_code == 200
    original = issued.json()
    assert reprint.json()["short_code"] == original["short_code"]
    assert original["issuer"] == "user"
    assert original["state"] == "active"

    history = await auth_client.get("/api/v1/spools/qr-codes")
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["short_code"] == original["short_code"]

    stored = await db_session.scalar(
        select(QrUserSpoolBinding).where(QrUserSpoolBinding.user_spool_id == spool.id)
    )
    assert stored is not None
    parsed = parse_qr_envelope(original["short_code"])
    assert parsed is not None
    assert parsed.token not in stored.token_ciphertext
    assert stored.token_digest != parsed.token

    owner_scan = await auth_client.post(f"/api/v1/qr/{original['short_code']}/scan")
    assert owner_scan.status_code == 200
    assert owner_scan.json()["filament"]["id"] == filament.id
    assert owner_scan.json()["qr_identity"] == {
        "version": 1,
        "mode": "instance",
        "issuer": "user",
        "resolution": "linked",
        "spool_id": spool.id,
    }

    _foreign, foreign_token = await _second_user(db_session, "foreign-user-code")
    foreign_scan = await auth_client.post(
        f"/api/v1/qr/{original['short_code']}/scan",
        headers={"Authorization": f"Bearer {foreign_token}"},
    )
    assert foreign_scan.status_code == 200
    assert foreign_scan.json()["qr_identity"]["resolution"] == "product_only"
    assert foreign_scan.json()["qr_identity"]["spool_id"] is None

    rotated = await auth_client.post(
        f"/api/v1/spools/{spool.id}/qr/rotate",
        json={"revision": original["revision"], "idempotency_key": "rotate-user-0001"},
    )
    replay = await auth_client.post(
        f"/api/v1/spools/{spool.id}/qr/rotate",
        json={"revision": original["revision"], "idempotency_key": "rotate-user-0001"},
    )
    assert rotated.status_code == replay.status_code == 200
    assert rotated.json()["short_code"] == replay.json()["short_code"]
    assert rotated.json()["short_code"] != original["short_code"]

    old_scan = await auth_client.post(f"/api/v1/qr/{original['short_code']}/scan")
    assert old_scan.status_code == 200
    assert old_scan.json()["filament"]["id"] == filament.id
    assert old_scan.json()["qr_identity"]["resolution"] == "product_only"
    assert old_scan.json()["qr_identity"]["spool_id"] is None


@pytest.mark.asyncio
async def test_user_qr_retirement_restores_then_purges_without_reusing_token(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    filament, spool = await _catalog_spool(db_session, user=auth_user, suffix="USER2")
    issued = (await auth_client.post(f"/api/v1/spools/{spool.id}/qr/issue")).json()

    retired_response = await auth_client.post(
        f"/api/v1/spools/{spool.id}/qr/retire",
        json={"revision": issued["revision"]},
    )
    assert retired_response.status_code == 200
    retired = retired_response.json()
    assert retired["state"] == "pending_retirement"
    assert retired["short_code"] == issued["short_code"]

    repeated = await auth_client.post(
        f"/api/v1/spools/{spool.id}/qr/retire",
        json={"revision": issued["revision"]},
    )
    assert repeated.status_code == 200
    assert repeated.json()["revision"] == retired["revision"]

    stale_restore = await auth_client.post(
        f"/api/v1/spools/{spool.id}/qr/restore",
        json={"revision": issued["revision"]},
    )
    assert stale_restore.status_code == 409
    assert stale_restore.json()["detail"]["code"] == "ERR_QR_BINDING_REVISION_CONFLICT"

    restored_response = await auth_client.post(
        f"/api/v1/spools/{spool.id}/qr/restore",
        json={"revision": retired["revision"]},
    )
    assert restored_response.status_code == 200
    restored = restored_response.json()
    assert restored["short_code"] == issued["short_code"]
    assert restored["state"] == "active"

    retired_again = (
        await auth_client.post(
            f"/api/v1/spools/{spool.id}/qr/retire",
            json={"revision": restored["revision"]},
        )
    ).json()
    binding = await db_session.scalar(
        select(QrUserSpoolBinding).where(QrUserSpoolBinding.user_spool_id == spool.id)
    )
    assert binding is not None
    binding.purge_after = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db_session.commit()

    removed = await purge_expired_user_qr_bindings(db_session)
    await db_session.commit()
    assert removed == 1
    assert await db_session.scalar(select(func.count()).select_from(QrUserSpoolBinding)) == 0

    expired_scan = await auth_client.post(f"/api/v1/qr/{retired_again['short_code']}/scan")
    assert expired_scan.status_code == 200
    assert expired_scan.json()["filament"]["id"] == filament.id
    assert expired_scan.json()["qr_identity"]["resolution"] == "product_only"

    reissued_response = await auth_client.post(f"/api/v1/spools/{spool.id}/qr/issue")
    assert reissued_response.status_code == 200
    assert reissued_response.json()["short_code"] != retired_again["short_code"]


async def _manufacturer_workspace(
    db: AsyncSession,
    *,
    user: User,
    suffix: str,
) -> tuple[Brand, Filament, Organization]:
    organization = Organization(
        name=f"QR Org {suffix}",
        slug=f"qr-org-{suffix}",
        active=True,
        created_by_id=user.id,
    )
    brand = Brand(
        name=f"QR Manufacturer {suffix}",
        slug=f"qr-manufacturer-{suffix}",
        active=True,
        verified=True,
    )
    db.add_all([organization, brand])
    await db.flush()
    db.add_all(
        [
            OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                all_brands=True,
                active=True,
            ),
            BrandTerritorialGrant(
                brand_id=brand.id,
                organization_id=organization.id,
                country=None,
                status=GrantStatus.active,
                source=GrantSource.invitation,
            ),
        ]
    )
    user.active_organization_id = organization.id
    filament = Filament(
        brand_id=brand.id,
        name=f"QR Batch Filament {suffix}",
        slug=f"qr-batch-filament-{suffix}",
        material_type="PLA",
        active=True,
        qr_code=f"FH-B{suffix.upper()}",
    )
    db.add(filament)
    await db.commit()
    await db.refresh(brand)
    await db.refresh(filament)
    await db.refresh(organization)
    return brand, filament, organization


@pytest.mark.asyncio
async def test_manufacturer_million_batch_is_compact_deterministic_and_claimable(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    brand, filament, organization = await _manufacturer_workspace(
        db_session,
        user=auth_user,
        suffix="M1",
    )
    request = {
        "brand_id": brand.id,
        "mode": "serialized",
        "items": [{"filament_id": filament.id, "quantity": 1_000_000}],
    }
    created = await auth_client.post(
        "/api/v1/manufacturer/qr-batches",
        json=request,
        headers={"Idempotency-Key": "manufacturer-million-0001"},
    )
    replayed = await auth_client.post(
        "/api/v1/manufacturer/qr-batches",
        json=request,
        headers={"Idempotency-Key": "manufacturer-million-0001"},
    )
    assert created.status_code == replayed.status_code == 201
    batch = created.json()
    assert replayed.json()["public_id"] == batch["public_id"]
    assert batch["organization_id"] == organization.id
    assert batch["total_quantity"] == 1_000_000
    assert await db_session.scalar(select(func.count()).select_from(QrManufacturerBatch)) == 1
    assert await db_session.scalar(select(func.count()).select_from(QrManufacturerBatchItem)) == 1
    assert (
        await db_session.scalar(select(func.count()).select_from(QrManufacturerInstanceState)) == 0
    )

    page = await auth_client.get(
        f"/api/v1/manufacturer/qr-batches/{batch['public_id']}/payloads",
        params={"offset": 999_998, "limit": 2},
    )
    repeated_page = await auth_client.get(
        f"/api/v1/manufacturer/qr-batches/{batch['public_id']}/payloads",
        params={"offset": 999_998, "limit": 2},
    )
    assert page.status_code == repeated_page.status_code == 200
    other_code, code = [item["short_code"] for item in page.json()["items"]]
    assert [item["short_code"] for item in repeated_page.json()["items"]] == [
        other_code,
        code,
    ]
    assert len(code) <= QR_MAX_SHORT_CODE_LENGTH

    auth_client.headers.pop("Authorization", None)
    anonymous_scan = await auth_client.post(f"/api/v1/qr/{code}/scan")
    assert anonymous_scan.status_code == 200
    assert anonymous_scan.json()["filament"]["id"] == filament.id
    assert anonymous_scan.json()["qr_identity"]["resolution"] == "unbound"

    token = create_access_token({"sub": auth_user.email})
    spool = UserSpool(
        user_id=auth_user.id,
        filament_id=filament.id,
        initial_weight_g=1000,
        used_weight_g=0,
        state=UserSpoolState.shelf,
        source="manual",
    )
    db_session.add(spool)
    await db_session.commit()
    await db_session.refresh(spool)
    spool_id = spool.id
    claim = await auth_client.post(
        f"/api/v1/qr/{code}/claim",
        json={"spool_id": spool_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert claim.status_code == 200
    assert claim.json()["spool_id"] == spool_id
    assert (
        await db_session.scalar(select(func.count()).select_from(QrManufacturerInstanceState)) == 1
    )

    duplicate_spool_claim = await auth_client.post(
        f"/api/v1/qr/{other_code}/claim",
        json={"spool_id": spool_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert duplicate_spool_claim.status_code == 409
    assert duplicate_spool_claim.json()["detail"]["code"] == "ERR_QR_INSTANCE_UNAVAILABLE"

    owner_scan = await auth_client.post(
        f"/api/v1/qr/{code}/scan",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert owner_scan.status_code == 200
    assert owner_scan.json()["qr_identity"]["resolution"] == "linked"
    assert owner_scan.json()["qr_identity"]["spool_id"] == spool_id

    issued_again = await auth_client.post(
        f"/api/v1/spools/{spool_id}/qr/issue",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert issued_again.status_code == 200
    assert issued_again.json()["issuer"] == "manufacturer"
    assert issued_again.json()["short_code"] == code

    history = await auth_client.get(
        "/api/v1/spools/qr-codes",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["short_code"] == code


@pytest.mark.asyncio
async def test_manufacturer_batch_permissions_idempotency_and_sparse_exception(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    brand, filament, _organization = await _manufacturer_workspace(
        db_session,
        user=auth_user,
        suffix="M2",
    )
    request = {
        "brand_id": brand.id,
        "mode": "serialized",
        "items": [{"filament_id": filament.id, "quantity": 3}],
    }
    created = await auth_client.post(
        "/api/v1/manufacturer/qr-batches",
        json=request,
        headers={"Idempotency-Key": "manufacturer-small-0001"},
    )
    assert created.status_code == 201
    batch = created.json()

    conflict = await auth_client.post(
        "/api/v1/manufacturer/qr-batches",
        json={**request, "mode": "sku"},
        headers={"Idempotency-Key": "manufacturer-small-0001"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "ERR_QR_IDEMPOTENCY_CONFLICT"

    invalid_key = await auth_client.post(
        "/api/v1/manufacturer/qr-batches",
        json=request,
        headers={"Idempotency-Key": "        "},
    )
    assert invalid_key.status_code == 400
    assert invalid_key.json()["detail"]["code"] == "ERR_QR_IDEMPOTENCY_KEY_INVALID"

    exception = await auth_client.post(
        f"/api/v1/manufacturer/qr-batches/{batch['public_id']}/exceptions",
        json={
            "ordinal": 1,
            "action": "scrap",
            "idempotency_key": "manufacturer-scrap-0001",
        },
    )
    replay = await auth_client.post(
        f"/api/v1/manufacturer/qr-batches/{batch['public_id']}/exceptions",
        json={
            "ordinal": 1,
            "action": "scrap",
            "idempotency_key": "manufacturer-scrap-0001",
        },
    )
    assert exception.status_code == replay.status_code == 200
    assert exception.json()["status"] == replay.json()["status"] == "scrapped"
    assert exception.json()["manifest_revision"] == replay.json()["manifest_revision"]

    conflicting_replay = await auth_client.post(
        f"/api/v1/manufacturer/qr-batches/{batch['public_id']}/exceptions",
        json={
            "ordinal": 1,
            "action": "revoke",
            "idempotency_key": "manufacturer-scrap-0001",
        },
    )
    assert conflicting_replay.status_code == 409
    assert conflicting_replay.json()["detail"]["code"] == "ERR_QR_IDEMPOTENCY_CONFLICT"

    foreign, foreign_token = await _second_user(db_session, "foreign-manufacturer")
    foreign.active_organization_id = None
    await db_session.commit()
    hidden = await auth_client.get(
        f"/api/v1/manufacturer/qr-batches/{batch['public_id']}",
        headers={"Authorization": f"Bearer {foreign_token}"},
    )
    assert hidden.status_code == 404
    assert hidden.json()["detail"]["code"] == "ERR_QR_BATCH_NOT_FOUND"

    grant = await db_session.scalar(
        select(BrandTerritorialGrant).where(
            BrandTerritorialGrant.brand_id == brand.id,
            BrandTerritorialGrant.organization_id == batch["organization_id"],
        )
    )
    assert grant is not None
    grant.status = GrantStatus.revoked
    grant.revoked_at = datetime.now(timezone.utc)
    await db_session.commit()

    revoked_direct = await auth_client.get(
        f"/api/v1/manufacturer/qr-batches/{batch['public_id']}",
    )
    assert revoked_direct.status_code == 404
    assert revoked_direct.json()["detail"]["code"] == "ERR_QR_BATCH_NOT_FOUND"
    revoked_list = await auth_client.get("/api/v1/manufacturer/qr-batches")
    assert revoked_list.status_code == 200
    assert revoked_list.json()["total"] == 0
    assert revoked_list.json()["items"] == []
