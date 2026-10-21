"""CSV draft resolution preserves private transport identity and QR guards."""

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.user_spool import UserSpool, UserSpoolState
from app.services.legal_acceptance_service import (
    CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    CURRENT_TERMS_VERSION,
)
from app.services.spool_compat_resource_service import create_import_ref
from app.services.spoolmanager_import_service import link_imported_spools_to_preset
from tests.spool_compat_test import _seed_spool_context


async def _scenario(db: AsyncSession):
    user, seed, _ = await _seed_spool_context(db)
    user.email_verified = True
    user.terms_version_accepted = CURRENT_TERMS_VERSION
    user.personal_data_consent_version = CURRENT_PERSONAL_DATA_CONSENT_VERSION
    target = Filament(
        brand_id=seed.filament.brand_id, name="CSV target", slug="csv-target",
        material_type="PLA", color_name="Blue", color_hex="#0000FF",
        diameter=1.75, density=1.24, spool_weight=1000, active=True,
    )
    db.add(target)
    await db.flush()
    ref = await create_import_ref(db, user_id=user.id, kind="filament",
                                  payload={"name": "Unknown CSV"}, source_namespace="octoprint_spoolmanager")
    spools = [UserSpool(
        user_id=user.id, filament_id=None, compat_filament_ref_id=ref.id,
        initial_weight_g=1000, used_weight_g=0, state=UserSpoolState.shelf,
        source="octoprint_spoolmanager", extra={"import_external_ref": "csv-row"},
    ) for _ in range(2)]
    preset = Preset(
        user_id=user.id, filament_id=None, name="CSV draft", is_official=False,
        is_weighted=False, extruder_temp=210, bed_temp=60,
        moderation_status=PresetModerationStatus.PENDING, active=False,
        orcaslicer_settings={"import_external_ref": "csv-row",
                             "import_provider": "octoprint_spoolmanager"},
    )
    db.add_all([*spools, preset])
    await db.commit()
    return user, target, ref, spools, preset


@pytest.mark.asyncio
async def test_csv_preset_resolution_repoints_shared_pending_ref_without_changing_wire_id(
    db_session: AsyncSession,
) -> None:
    _, target, ref, spools, preset = await _scenario(db_session)
    old_wire = ref.wire_id
    linked = await link_imported_spools_to_preset(
        db_session, preset, target_filament_id=target.id,
    )
    assert linked == [spool.id for spool in spools]
    assert ref.wire_id == old_wire and ref.filament_id == target.id
    assert all(spool.compat_filament_ref_id == ref.id and spool.filament_id == target.id
               for spool in spools)
    assert all(spool.extra["import_resolved_filament_id"] == str(target.id) for spool in spools)
    revision = ref.revision
    await link_imported_spools_to_preset(db_session, preset, target_filament_id=target.id)
    assert ref.revision == revision


@pytest.mark.asyncio
async def test_preset_patch_resolves_pending_csv_ref_before_preset_write(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    user, target, ref, spools, preset = await _scenario(db_session)
    wire_id = ref.wire_id
    token = create_access_token({"sub": user.email})
    response = await client.patch(
        f"/api/v1/presets/{preset.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"filament_id": target.id, "active": True},
    )
    assert response.status_code == 200, response.text
    await db_session.refresh(ref)
    for spool in spools:
        await db_session.refresh(spool)
        assert spool.filament_id == target.id and spool.compat_filament_ref_id == ref.id
    assert ref.wire_id == wire_id and ref.filament_id == target.id


@pytest.mark.asyncio
async def test_csv_link_to_different_catalog_material_clears_only_selected_spool_ref(
    db_session: AsyncSession,
) -> None:
    _, target, ref, spools, preset = await _scenario(db_session)
    await link_imported_spools_to_preset(db_session, preset, target_filament_id=target.id)
    await db_session.commit()
    replacement = Filament(
        brand_id=target.brand_id, name="CSV replacement", slug="csv-replacement",
        material_type="PLA", color_name="Red", color_hex="#FF0000",
        diameter=1.75, density=1.24, spool_weight=1000, active=True,
    )
    db_session.add(replacement)
    await db_session.flush()
    spools[1].extra = {"import_external_ref": "other-row"}
    await db_session.flush()
    await link_imported_spools_to_preset(db_session, preset, target_filament_id=replacement.id)
    assert ref.filament_id == target.id
    assert spools[0].filament_id == replacement.id and spools[0].compat_filament_ref_id is None
    assert spools[1].filament_id == target.id and spools[1].compat_filament_ref_id == ref.id


@pytest.mark.asyncio
async def test_csv_shared_pending_resolution_guard_rejection_does_not_partially_repoint(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, target, ref, spools, preset = await _scenario(db_session)
    from app.services import spool_compat_resource_service

    actual_guard = spool_compat_resource_service.set_spool_filament_with_qr_guard

    async def rejecting_guard(db, *, spool, filament_id, compat_filament_ref_id):
        if spool.id == spools[1].id:
            raise HTTPException(status_code=409, detail="ERR_QR_MATERIAL_CHANGE_REQUIRES_REISSUE")
        return await actual_guard(db, spool=spool, filament_id=filament_id,
                                  compat_filament_ref_id=compat_filament_ref_id)

    monkeypatch.setattr(spool_compat_resource_service, "set_spool_filament_with_qr_guard",
                        rejecting_guard)
    with pytest.raises(HTTPException) as exc:
        await link_imported_spools_to_preset(db_session, preset, target_filament_id=target.id)
    assert exc.value.status_code == 409
    await db_session.rollback()
    for spool in spools:
        await db_session.refresh(spool)
        assert spool.filament_id is None and spool.compat_filament_ref_id == ref.id
    await db_session.refresh(ref)
    assert ref.filament_id is None
