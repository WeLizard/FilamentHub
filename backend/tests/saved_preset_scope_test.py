"""Tests for the filament-library scope (PROFILE-LIBRARY-1, RFC §3.3).

A saved preset is either unscoped (universal — compatibility from the
preset's catalog PresetPrinter links) or targeted to one of the user's own
Orca machine profiles. Export must respect the requesting user's scope.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_printer import PresetPrinter
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_saved_preset import UserSavedPreset


async def _register_and_login(client: AsyncClient, suffix: str) -> tuple[dict[str, str], str]:
    email = f"{suffix}@example.com"
    password = "testpassword123"
    register_response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": f"user_{suffix}",
            "password": password,
            "role": "user",
        },
    )
    assert register_response.status_code == 201
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, email


async def _get_user(db: AsyncSession, email: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one()


async def _seed_preset(db: AsyncSession, slug: str) -> Preset:
    brand = Brand(name=f"Scope Brand {slug}", slug=f"scope-brand-{slug}", active=True)
    db.add(brand)
    await db.flush()
    filament = Filament(
        brand_id=brand.id,
        name=f"Scope PLA {slug}",
        slug=f"scope-pla-{slug}",
        material_type="PLA",
        diameter=1.75,
        active=True,
    )
    db.add(filament)
    await db.flush()
    preset = Preset(
        filament_id=filament.id,
        name=f"Scope Preset {slug}",
        is_official=True,
        extruder_temp=200.0,
        bed_temp=60.0,
        moderation_status=PresetModerationStatus.APPROVED,
        active=True,
    )
    db.add(preset)
    await db.flush()
    return preset


async def _seed_profile(
    db: AsyncSession,
    *,
    owner_user_id: int | None,
    slug: str,
    name: str,
    printer: Printer | None = None,
    active: bool = True,
) -> PrinterProfile:
    profile = PrinterProfile(
        printer_id=printer.id if printer else None,
        owner_user_id=owner_user_id,
        name=name,
        slug=slug,
        active=active,
        orcaslicer_settings={},
    )
    db.add(profile)
    await db.flush()
    return profile


async def _save_preset(client: AsyncClient, headers: dict[str, str], preset_id: int) -> None:
    response = await client.post(
        "/api/v1/saved-presets/", json={"preset_id": preset_id}, headers=headers
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_scope_targeted_own_profile(client: AsyncClient, db_session: AsyncSession):
    headers, email = await _register_and_login(client, "scope-own")
    user = await _get_user(db_session, email)
    preset = await _seed_preset(db_session, "own")
    profile = await _seed_profile(
        db_session, owner_user_id=user.id, slug="scope-own-voron", name="My Voron"
    )
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    response = await client.patch(
        f"/api/v1/saved-presets/{preset.id}/scope",
        json={"scope": "targeted", "target_printer_profile_id": profile.id},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "targeted"
    assert data["target_printer_profile_id"] == profile.id


@pytest.mark.asyncio
async def test_scope_targeted_requires_target(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client, "scope-notarget")
    preset = await _seed_preset(db_session, "notarget")
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    response = await client.patch(
        f"/api/v1/saved-presets/{preset.id}/scope",
        json={"scope": "targeted"},
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ERR_PRINTER_PROFILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_scope_targeted_rejects_foreign_profile(
    client: AsyncClient, db_session: AsyncSession
):
    headers, _ = await _register_and_login(client, "scope-foreign")
    other_headers, other_email = await _register_and_login(client, "scope-foreign-other")
    other_user = await _get_user(db_session, other_email)
    preset = await _seed_preset(db_session, "foreign")
    foreign_profile = await _seed_profile(
        db_session, owner_user_id=other_user.id, slug="scope-foreign-p", name="Foreign"
    )
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    response = await client.patch(
        f"/api/v1/saved-presets/{preset.id}/scope",
        json={"scope": "targeted", "target_printer_profile_id": foreign_profile.id},
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ERR_PRINTER_PROFILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_scope_targeted_rejects_inactive_profile(
    client: AsyncClient, db_session: AsyncSession
):
    headers, email = await _register_and_login(client, "scope-inactive")
    user = await _get_user(db_session, email)
    preset = await _seed_preset(db_session, "inactive")
    profile = await _seed_profile(
        db_session,
        owner_user_id=user.id,
        slug="scope-inactive-p",
        name="Inactive",
        active=False,
    )
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    response = await client.patch(
        f"/api/v1/saved-presets/{preset.id}/scope",
        json={"scope": "targeted", "target_printer_profile_id": profile.id},
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ERR_PRINTER_PROFILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_scope_unsaved_preset_404(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client, "scope-unsaved")
    preset = await _seed_preset(db_session, "unsaved")
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/saved-presets/{preset.id}/scope",
        json={"scope": "unscoped"},
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ERR_SAVED_PRESET_NOT_FOUND"


@pytest.mark.asyncio
async def test_scope_unscoped_clears_target(client: AsyncClient, db_session: AsyncSession):
    headers, email = await _register_and_login(client, "scope-clear")
    user = await _get_user(db_session, email)
    preset = await _seed_preset(db_session, "clear")
    profile = await _seed_profile(
        db_session, owner_user_id=user.id, slug="scope-clear-p", name="Clear Me"
    )
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    targeted = await client.patch(
        f"/api/v1/saved-presets/{preset.id}/scope",
        json={"scope": "targeted", "target_printer_profile_id": profile.id},
        headers=headers,
    )
    assert targeted.status_code == 200

    # target id in the unscoped payload must be ignored, not validated
    response = await client.patch(
        f"/api/v1/saved-presets/{preset.id}/scope",
        json={"scope": "unscoped", "target_printer_profile_id": profile.id},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "unscoped"
    assert data["target_printer_profile_id"] is None


@pytest.mark.asyncio
async def test_export_targeted_narrows_to_profile_model(
    client: AsyncClient, db_session: AsyncSession
):
    """Targeted at a profile linked to a system printer → condition by its
    canonical printer_model, overriding the preset's own PresetPrinter links."""
    headers, email = await _register_and_login(client, "scope-exp-model")
    user = await _get_user(db_session, email)
    preset = await _seed_preset(db_session, "exp-model")
    authored = Printer(
        name="Bambu Lab X1 Carbon",
        manufacturer="Bambu Lab",
        model="X1 Carbon",
        slug="scope-exp-x1c",
        source="system",
    )
    target_printer = Printer(
        name="Voron 2.4 350",
        manufacturer="Voron",
        model="2.4 350",
        slug="scope-exp-voron",
        source="system",
    )
    db_session.add_all([authored, target_printer])
    await db_session.flush()
    db_session.add(PresetPrinter(preset_id=preset.id, printer_id=authored.id, is_primary=True))
    profile = await _seed_profile(
        db_session,
        owner_user_id=user.id,
        slug="scope-exp-voron-profile",
        name="Voron 2.4 350 0.4 nozzle",
        printer=target_printer,
    )
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    targeted = await client.patch(
        f"/api/v1/saved-presets/{preset.id}/scope",
        json={"scope": "targeted", "target_printer_profile_id": profile.id},
        headers=headers,
    )
    assert targeted.status_code == 200

    response = await client.get(
        f"/api/v1/presets/{preset.id}/export/orcaslicer.json", headers=headers
    )
    assert response.status_code == 200
    exported = response.json()
    assert exported["compatible_printers_condition"] == 'printer_model=="Voron 2.4 350"'
    assert exported["compatible_printers"] == []


@pytest.mark.asyncio
async def test_export_targeted_custom_profile_pins_by_name(
    client: AsyncClient, db_session: AsyncSession
):
    """Targeted at a profile without a resolvable system model (self-build,
    generic Klipper) → pin by the exact machine-profile name."""
    headers, email = await _register_and_login(client, "scope-exp-pin")
    user = await _get_user(db_session, email)
    preset = await _seed_preset(db_session, "exp-pin")
    profile = await _seed_profile(
        db_session,
        owner_user_id=user.id,
        slug="scope-exp-custom",
        name="My Custom Rig 0.6",
    )
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    targeted = await client.patch(
        f"/api/v1/saved-presets/{preset.id}/scope",
        json={"scope": "targeted", "target_printer_profile_id": profile.id},
        headers=headers,
    )
    assert targeted.status_code == 200

    response = await client.get(
        f"/api/v1/presets/{preset.id}/export/orcaslicer.json", headers=headers
    )
    assert response.status_code == 200
    exported = response.json()
    assert exported["compatible_printers"] == ["My Custom Rig 0.6"]
    assert "compatible_printers_condition" not in exported


@pytest.mark.asyncio
async def test_export_unscoped_keeps_authored_links(
    client: AsyncClient, db_session: AsyncSession
):
    """Unscoped (and not saved at all) — today's behavior: condition from the
    preset's catalog PresetPrinter links."""
    headers, _ = await _register_and_login(client, "scope-exp-unscoped")
    preset = await _seed_preset(db_session, "exp-unscoped")
    authored = Printer(
        name="Bambu Lab X1 Carbon",
        manufacturer="Bambu Lab",
        model="X1 Carbon",
        slug="scope-exp-unscoped-x1c",
        source="system",
    )
    db_session.add(authored)
    await db_session.flush()
    db_session.add(PresetPrinter(preset_id=preset.id, printer_id=authored.id, is_primary=True))
    await db_session.commit()

    # not saved at all
    response = await client.get(
        f"/api/v1/presets/{preset.id}/export/orcaslicer.json", headers=headers
    )
    assert response.status_code == 200
    exported = response.json()
    assert exported["compatible_printers_condition"] == 'printer_model=="Bambu Lab X1 Carbon"'

    # saved with default (unscoped) scope — same result
    await _save_preset(client, headers, preset.id)
    response = await client.get(
        f"/api/v1/presets/{preset.id}/export/orcaslicer.json", headers=headers
    )
    assert response.status_code == 200
    exported = response.json()
    assert exported["compatible_printers_condition"] == 'printer_model=="Bambu Lab X1 Carbon"'


@pytest.mark.asyncio
async def test_export_targeted_deleted_profile_falls_back(
    client: AsyncClient, db_session: AsyncSession
):
    """A targeted row whose profile was deactivated must not break export —
    it falls back to the authored-links behavior."""
    headers, email = await _register_and_login(client, "scope-exp-gone")
    user = await _get_user(db_session, email)
    preset = await _seed_preset(db_session, "exp-gone")
    profile = await _seed_profile(
        db_session, owner_user_id=user.id, slug="scope-exp-gone-p", name="Gone Soon"
    )
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    targeted = await client.patch(
        f"/api/v1/saved-presets/{preset.id}/scope",
        json={"scope": "targeted", "target_printer_profile_id": profile.id},
        headers=headers,
    )
    assert targeted.status_code == 200

    profile.active = False
    await db_session.commit()

    response = await client.get(
        f"/api/v1/presets/{preset.id}/export/orcaslicer.json", headers=headers
    )
    assert response.status_code == 200
    exported = response.json()
    assert exported["compatible_printers"] == []
    assert "compatible_printers_condition" not in exported


@pytest.mark.asyncio
async def test_scope_defaults_unscoped_on_save(client: AsyncClient, db_session: AsyncSession):
    headers, email = await _register_and_login(client, "scope-default")
    user = await _get_user(db_session, email)
    preset = await _seed_preset(db_session, "default")
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    result = await db_session.execute(
        select(UserSavedPreset).where(
            UserSavedPreset.user_id == user.id,
            UserSavedPreset.preset_id == preset.id,
        )
    )
    saved = result.scalar_one()
    assert saved.scope == "unscoped"
    assert saved.target_printer_profile_id is None
