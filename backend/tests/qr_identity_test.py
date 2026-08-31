"""QR envelope, ownership, lifecycle, and compact batch contract tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import create_access_token
from app.models.brand import Brand
from app.models.brand_territorial_grant import (
    BrandTerritorialGrant,
    GrantSource,
    GrantStatus,
)
from app.models.filament import Filament
from app.models.organization import Organization, OrganizationMembership
from app.models.preset import Preset, PresetModerationStatus
from app.models.qr_identity import (
    QrManufacturerBatch,
    QrManufacturerBatchItem,
    QrManufacturerInstanceState,
    QrOperationReceipt,
    QrUserSpoolBinding,
)
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool, UserSpoolState
from app.services.qr_identity_service import (
    QR_MAX_SHORT_CODE_LENGTH,
    encode_qr_envelope,
    list_manufacturer_qr_batches,
    parse_qr_envelope,
    purge_expired_user_qr_bindings,
    restore_user_spool_qr,
    retire_user_spool_qr,
)
from app.services.spoolmanager_import_service import link_imported_spools_to_preset
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


async def _second_filament(
    db: AsyncSession,
    *,
    source: Filament,
    suffix: str,
) -> Filament:
    filament = Filament(
        brand_id=source.brand_id,
        name=f"QR Replacement Filament {suffix}",
        slug=f"qr-replacement-filament-{suffix}",
        material_type="ABS",
        active=True,
        qr_code=f"FH-R{suffix.upper()}",
    )
    db.add(filament)
    await db.commit()
    await db.refresh(filament)
    return filament


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


@pytest.mark.asyncio
async def test_retire_and_restore_return_loaded_responses_with_expire_on_commit(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    _filament, spool = await _catalog_spool(db_session, user=auth_user, suffix="EXPIRING-SESSION")
    issued = (await auth_client.post(f"/api/v1/spools/{spool.id}/qr/issue")).json()
    sessions = async_sessionmaker(
        db_session.bind,
        class_=AsyncSession,
        expire_on_commit=True,
    )

    async with sessions() as session:
        user = await session.get(User, auth_user.id)
        retired = await retire_user_spool_qr(
            session,
            user=user,
            spool_id=spool.id,
            revision=issued["revision"],
        )
    assert retired.state == "pending_retirement"
    assert retired.short_code == issued["short_code"]

    async with sessions() as session:
        user = await session.get(User, auth_user.id)
        restored = await restore_user_spool_qr(
            session,
            user=user,
            spool_id=spool.id,
            revision=retired.revision,
        )
    assert restored.state == "active"
    assert restored.short_code == issued["short_code"]


@pytest.mark.asyncio
async def test_material_change_requires_atomic_qr_replacement_and_preserves_old_product(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    original_filament, spool = await _catalog_spool(
        db_session,
        user=auth_user,
        suffix="MATERIAL1",
    )
    first_replacement = await _second_filament(
        db_session,
        source=original_filament,
        suffix="MATERIAL1A",
    )
    second_replacement = await _second_filament(
        db_session,
        source=original_filament,
        suffix="MATERIAL1B",
    )

    ordinary_change = await auth_client.patch(
        f"/api/v1/spools/{spool.id}",
        json={"filament_id": first_replacement.id},
    )
    assert ordinary_change.status_code == 200
    assert ordinary_change.json()["filament_id"] == first_replacement.id

    issued = (await auth_client.post(f"/api/v1/spools/{spool.id}/qr/issue")).json()
    blocked = await auth_client.patch(
        f"/api/v1/spools/{spool.id}",
        json={"filament_id": second_replacement.id},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "ERR_QR_MATERIAL_CHANGE_REQUIRES_REISSUE"

    missing_confirmation = await auth_client.post(
        f"/api/v1/spools/{spool.id}/qr/replace-material",
        json={
            "filament_id": second_replacement.id,
            "revision": issued["revision"],
            "idempotency_key": "replace-material-0001",
            "confirm_reprint": False,
        },
    )
    assert missing_confirmation.status_code == 422

    request = {
        "filament_id": second_replacement.id,
        "revision": issued["revision"],
        "idempotency_key": "replace-material-0001",
        "confirm_reprint": True,
    }
    replaced = await auth_client.post(
        f"/api/v1/spools/{spool.id}/qr/replace-material",
        json=request,
    )
    replay = await auth_client.post(
        f"/api/v1/spools/{spool.id}/qr/replace-material",
        json=request,
    )
    assert replaced.status_code == replay.status_code == 200
    assert replay.json() == replaced.json()
    assert replaced.json()["filament_id"] == second_replacement.id
    assert replaced.json()["short_code"] != issued["short_code"]

    conflicting_replay = await auth_client.post(
        f"/api/v1/spools/{spool.id}/qr/replace-material",
        json={**request, "filament_id": original_filament.id},
    )
    assert conflicting_replay.status_code == 409
    assert conflicting_replay.json()["detail"]["code"] == "ERR_QR_IDEMPOTENCY_CONFLICT"

    old_scan = await auth_client.post(f"/api/v1/qr/{issued['short_code']}/scan")
    assert old_scan.status_code == 200
    assert old_scan.json()["filament"]["id"] == first_replacement.id
    assert old_scan.json()["qr_identity"]["resolution"] == "product_only"
    replacement_scan = await auth_client.post(
        f"/api/v1/qr/{replaced.json()['short_code']}/scan"
    )
    assert replacement_scan.status_code == 200
    assert replacement_scan.json()["filament"]["id"] == second_replacement.id
    assert replacement_scan.json()["qr_identity"]["resolution"] == "linked"

    rotated = await auth_client.post(
        f"/api/v1/spools/{spool.id}/qr/rotate",
        json={
            "revision": replaced.json()["revision"],
            "idempotency_key": "rotate-after-replace-0001",
        },
    )
    assert rotated.status_code == 200
    replay_after_newer_operation = await auth_client.post(
        f"/api/v1/spools/{spool.id}/qr/replace-material",
        json=request,
    )
    assert replay_after_newer_operation.status_code == 200
    assert replay_after_newer_operation.json() == replaced.json()
    assert (
        await db_session.scalar(select(func.count()).select_from(QrOperationReceipt))
        == 2
    )


@pytest.mark.asyncio
async def test_import_resolution_and_spool_compat_use_the_material_qr_guard(
    client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    original_filament, spool = await _catalog_spool(
        db_session,
        user=auth_user,
        suffix="MATERIAL2",
    )
    first_replacement = await _second_filament(
        db_session,
        source=original_filament,
        suffix="MATERIAL2A",
    )
    second_replacement = await _second_filament(
        db_session,
        source=original_filament,
        suffix="MATERIAL2B",
    )
    spool.source = "octoprint_spoolmanager"
    spool.extra = {"import_external_ref": "material-guard-ref"}
    preset = Preset(
        filament_id=first_replacement.id,
        user_id=auth_user.id,
        name="Resolved import material",
        is_official=False,
        is_weighted=False,
        extruder_temp=240,
        bed_temp=90,
        moderation_status=PresetModerationStatus.PENDING,
        active=True,
        orcaslicer_settings={
            "import_external_ref": "material-guard-ref",
            "import_provider": "octoprint_spoolmanager",
        },
    )
    db_session.add(preset)
    await db_session.commit()

    assert await link_imported_spools_to_preset(db_session, preset) == [spool.id]
    await db_session.commit()
    await db_session.refresh(spool)
    assert spool.filament_id == first_replacement.id

    token = create_access_token({"sub": auth_user.email})
    issued = await client.post(
        f"/api/v1/spools/{spool.id}/qr/issue",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert issued.status_code == 200
    user_id = auth_user.id
    spool_id = spool.id
    second_replacement_id = second_replacement.id
    preset.filament_id = second_replacement.id
    await db_session.commit()

    with pytest.raises(HTTPException) as exc:
        await link_imported_spools_to_preset(db_session, preset)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "ERR_QR_MATERIAL_CHANGE_REQUIRES_REISSUE"
    await db_session.rollback()

    device = UserPrinterDevice(
        user_id=user_id,
        name="QR guard adapter",
        device_fingerprint="qr-guard-adapter",
        api_key="qr_guard_adapter_key",
    )
    db_session.add(device)
    await db_session.commit()
    compatible_patch = await client.patch(
        f"/api/v1/spool_compat/{device.api_key}/v1/spool/{spool_id}",
        json={"filament_id": second_replacement_id},
    )
    assert compatible_patch.status_code == 409
    assert (
        compatible_patch.json()["detail"]["code"]
        == "ERR_QR_MATERIAL_CHANGE_REQUIRES_REISSUE"
    )


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
async def test_claimed_manufacturer_qr_permanently_locks_spool_material(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    brand, filament, _organization = await _manufacturer_workspace(
        db_session,
        user=auth_user,
        suffix="MATERIALLOCK",
    )
    replacement = await _second_filament(
        db_session,
        source=filament,
        suffix="MATERIALLOCK",
    )
    created = await auth_client.post(
        "/api/v1/manufacturer/qr-batches",
        json={
            "brand_id": brand.id,
            "mode": "serialized",
            "items": [{"filament_id": filament.id, "quantity": 1}],
        },
        headers={"Idempotency-Key": "manufacturer-lock-0001"},
    )
    assert created.status_code == 201
    payloads = await auth_client.get(
        f"/api/v1/manufacturer/qr-batches/{created.json()['public_id']}/payloads"
    )
    code = payloads.json()["items"][0]["short_code"]
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
    claimed = await auth_client.post(
        f"/api/v1/qr/{code}/claim",
        json={"spool_id": spool.id},
    )
    assert claimed.status_code == 200

    ordinary_change = await auth_client.patch(
        f"/api/v1/spools/{spool.id}",
        json={"filament_id": replacement.id},
    )
    assert ordinary_change.status_code == 409
    assert (
        ordinary_change.json()["detail"]["code"]
        == "ERR_MANUFACTURER_QR_MATERIAL_LOCKED"
    )
    explicit_replacement = await auth_client.post(
        f"/api/v1/spools/{spool.id}/qr/replace-material",
        json={
            "filament_id": replacement.id,
            "revision": 1,
            "idempotency_key": "manufacturer-replace-0001",
            "confirm_reprint": True,
        },
    )
    assert explicit_replacement.status_code == 409
    assert (
        explicit_replacement.json()["detail"]["code"]
        == "ERR_MANUFACTURER_QR_MATERIAL_LOCKED"
    )


@pytest.mark.asyncio
async def test_manufacturer_batch_list_uses_bounded_queries_for_brand_history(
    auth_client: AsyncClient,
    auth_user: User,
    db_session: AsyncSession,
):
    brand, filament, _organization = await _manufacturer_workspace(
        db_session,
        user=auth_user,
        suffix="QUERYCOUNT",
    )
    for index in range(3):
        created = await auth_client.post(
            "/api/v1/manufacturer/qr-batches",
            json={
                "brand_id": brand.id,
                "mode": "serialized",
                "items": [{"filament_id": filament.id, "quantity": index + 1}],
            },
            headers={"Idempotency-Key": f"query-count-batch-{index:04d}"},
        )
        assert created.status_code == 201

    historical_brands = [
        Brand(
            name=f"QR Historical Manufacturer {index}",
            slug=f"qr-historical-manufacturer-{index}",
            active=True,
            verified=True,
        )
        for index in range(24)
    ]
    db_session.add_all(historical_brands)
    await db_session.flush()
    db_session.add_all(
        [
            QrManufacturerBatch(
                public_id=f"historical-batch-{index:016d}",
                token_ref=f"HIST{index:010d}",
                organization_id=_organization.id,
                brand_id=brand.id,
                created_by_id=auth_user.id,
                mode="serialized",
                total_quantity=1,
                manifest_revision=1,
                secret_ciphertext="history",
                idempotency_key_digest=f"{index + 10_000:064x}",
                request_digest=f"{index + 20_000:064x}",
            )
            for index, brand in enumerate(historical_brands)
        ]
    )
    await db_session.commit()

    statements: list[str] = []

    def record_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    assert db_session.bind is not None
    event.listen(db_session.bind.sync_engine, "before_cursor_execute", record_statement)
    try:
        listed = await list_manufacturer_qr_batches(
            db_session,
            user=auth_user,
            offset=0,
            limit=50,
        )
    finally:
        event.remove(db_session.bind.sync_engine, "before_cursor_execute", record_statement)

    assert listed.total == 3
    assert len(listed.items) == 3
    item_queries = [
        statement
        for statement in statements
        if "FROM qr_manufacturer_batch_items" in statement
    ]
    assert len(statements) == 3
    assert len(item_queries) == 1

    second_page = await list_manufacturer_qr_batches(
        db_session,
        user=auth_user,
        offset=1,
        limit=1,
    )
    assert second_page.total == 3
    assert len(second_page.items) == 1


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

    restored = await auth_client.post(
        f"/api/v1/manufacturer/qr-batches/{batch['public_id']}/exceptions",
        json={
            "ordinal": 1,
            "action": "restore",
            "idempotency_key": "manufacturer-restore-0001",
        },
    )
    assert restored.status_code == 200
    assert restored.json()["status"] is None
    revoked = await auth_client.post(
        f"/api/v1/manufacturer/qr-batches/{batch['public_id']}/exceptions",
        json={
            "ordinal": 1,
            "action": "revoke",
            "idempotency_key": "manufacturer-revoke-0001",
        },
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "revoked"
    old_key_after_newer_operation = await auth_client.post(
        f"/api/v1/manufacturer/qr-batches/{batch['public_id']}/exceptions",
        json={
            "ordinal": 1,
            "action": "scrap",
            "idempotency_key": "manufacturer-scrap-0001",
        },
    )
    assert old_key_after_newer_operation.status_code == 200
    assert old_key_after_newer_operation.json() == exception.json()
    batch_id = await db_session.scalar(
        select(QrManufacturerBatch.id).where(
            QrManufacturerBatch.public_id == batch["public_id"]
        )
    )
    current_state = await db_session.scalar(
        select(QrManufacturerInstanceState).where(
            QrManufacturerInstanceState.batch_id == batch_id,
            QrManufacturerInstanceState.ordinal == 1,
        )
    )
    assert current_state is not None
    assert current_state.status == "revoked"

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
