"""Tests for the filament-library scope (PROFILE-LIBRARY-1, RFC §3.3).

A saved preset carries a set of target machine profiles: empty → unscoped
(universal, compatibility from the preset's catalog PresetPrinter links),
one → targeted, several → compatible. Export must respect the requesting
user's target set.
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
from app.models.user_saved_preset import UserSavedPreset, UserSavedPresetTarget


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


async def _seed_system_printer(db: AsyncSession, *, name: str, slug: str) -> Printer:
    printer = Printer(
        name=name, manufacturer="Vendor", model=name, slug=slug, source="system"
    )
    db.add(printer)
    await db.flush()
    return printer


async def _save_preset(client: AsyncClient, headers: dict[str, str], preset_id: int) -> None:
    response = await client.post(
        "/api/v1/saved-presets/", json={"preset_id": preset_id}, headers=headers
    )
    assert response.status_code == 201


async def _patch_scope(
    client: AsyncClient, headers: dict[str, str], preset_id: int, target_ids: list[int]
):
    return await client.patch(
        f"/api/v1/saved-presets/{preset_id}/scope",
        json={"target_printer_profile_ids": target_ids},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_scope_single_target_is_targeted(client: AsyncClient, db_session: AsyncSession):
    headers, email = await _register_and_login(client, "scope-own")
    user = await _get_user(db_session, email)
    preset = await _seed_preset(db_session, "own")
    profile = await _seed_profile(
        db_session, owner_user_id=user.id, slug="scope-own-voron", name="My Voron"
    )
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    response = await _patch_scope(client, headers, preset.id, [profile.id])
    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "targeted"
    assert data["target_printer_profile_ids"] == [profile.id]


@pytest.mark.asyncio
async def test_scope_multiple_targets_is_compatible(
    client: AsyncClient, db_session: AsyncSession
):
    headers, email = await _register_and_login(client, "scope-multi")
    user = await _get_user(db_session, email)
    preset = await _seed_preset(db_session, "multi")
    p1 = await _seed_profile(
        db_session, owner_user_id=user.id, slug="scope-multi-1", name="Voron"
    )
    p2 = await _seed_profile(
        db_session, owner_user_id=user.id, slug="scope-multi-2", name="P2S"
    )
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    # duplicates in the request must collapse
    response = await _patch_scope(client, headers, preset.id, [p1.id, p2.id, p1.id])
    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "compatible"
    assert sorted(data["target_printer_profile_ids"]) == sorted([p1.id, p2.id])


@pytest.mark.asyncio
async def test_scope_reassign_overlapping_set(client: AsyncClient, db_session: AsyncSession):
    """Re-selecting a set that overlaps the current one must not collide on
    the (saved_preset, profile) unique index — the writer diffs the set
    instead of reassigning it wholesale (Postgres regression)."""
    headers, email = await _register_and_login(client, "scope-overlap")
    user = await _get_user(db_session, email)
    preset = await _seed_preset(db_session, "overlap")
    a = await _seed_profile(db_session, owner_user_id=user.id, slug="scope-ovl-a", name="A")
    b = await _seed_profile(db_session, owner_user_id=user.id, slug="scope-ovl-b", name="B")
    c = await _seed_profile(db_session, owner_user_id=user.id, slug="scope-ovl-c", name="C")
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    # [A] → [A, B] (A stays) → [A, C] (A stays, B removed, C added)
    assert (await _patch_scope(client, headers, preset.id, [a.id])).status_code == 200
    step2 = await _patch_scope(client, headers, preset.id, [a.id, b.id])
    assert step2.status_code == 200
    assert sorted(step2.json()["target_printer_profile_ids"]) == sorted([a.id, b.id])
    step3 = await _patch_scope(client, headers, preset.id, [a.id, c.id])
    assert step3.status_code == 200
    assert sorted(step3.json()["target_printer_profile_ids"]) == sorted([a.id, c.id])


@pytest.mark.asyncio
async def test_scope_rejects_foreign_profile(client: AsyncClient, db_session: AsyncSession):
    headers, email = await _register_and_login(client, "scope-foreign")
    _other_headers, other_email = await _register_and_login(client, "scope-foreign-other")
    user = await _get_user(db_session, email)
    other_user = await _get_user(db_session, other_email)
    preset = await _seed_preset(db_session, "foreign")
    own_profile = await _seed_profile(
        db_session, owner_user_id=user.id, slug="scope-foreign-own", name="Own"
    )
    foreign_profile = await _seed_profile(
        db_session, owner_user_id=other_user.id, slug="scope-foreign-p", name="Foreign"
    )
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    # a single foreign id in the set rejects the whole update
    response = await _patch_scope(
        client, headers, preset.id, [own_profile.id, foreign_profile.id]
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ERR_PRINTER_PROFILE_NOT_FOUND"

    # nothing was written
    result = await db_session.execute(
        select(UserSavedPresetTarget).join(
            UserSavedPreset, UserSavedPresetTarget.user_saved_preset_id == UserSavedPreset.id
        ).where(UserSavedPreset.user_id == user.id, UserSavedPreset.preset_id == preset.id)
    )
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_scope_rejects_inactive_profile(client: AsyncClient, db_session: AsyncSession):
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

    response = await _patch_scope(client, headers, preset.id, [profile.id])
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ERR_PRINTER_PROFILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_scope_unsaved_preset_404(client: AsyncClient, db_session: AsyncSession):
    headers, _ = await _register_and_login(client, "scope-unsaved")
    preset = await _seed_preset(db_session, "unsaved")
    await db_session.commit()

    response = await _patch_scope(client, headers, preset.id, [])
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ERR_SAVED_PRESET_NOT_FOUND"


@pytest.mark.asyncio
async def test_scope_empty_set_clears_targets(client: AsyncClient, db_session: AsyncSession):
    headers, email = await _register_and_login(client, "scope-clear")
    user = await _get_user(db_session, email)
    preset = await _seed_preset(db_session, "clear")
    profile = await _seed_profile(
        db_session, owner_user_id=user.id, slug="scope-clear-p", name="Clear Me"
    )
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    targeted = await _patch_scope(client, headers, preset.id, [profile.id])
    assert targeted.status_code == 200

    response = await _patch_scope(client, headers, preset.id, [])
    assert response.status_code == 200
    data = response.json()
    assert data["scope"] == "unscoped"
    assert data["target_printer_profile_ids"] == []


@pytest.mark.asyncio
async def test_export_targeted_narrows_to_profile_model(
    client: AsyncClient, db_session: AsyncSession
):
    """One target linked to a system printer → condition by its canonical
    printer_model, overriding the preset's own PresetPrinter links."""
    headers, email = await _register_and_login(client, "scope-exp-model")
    user = await _get_user(db_session, email)
    preset = await _seed_preset(db_session, "exp-model")
    authored = await _seed_system_printer(
        db_session, name="Bambu Lab X1 Carbon", slug="scope-exp-x1c"
    )
    target_printer = await _seed_system_printer(
        db_session, name="Voron 2.4 350", slug="scope-exp-voron"
    )
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

    targeted = await _patch_scope(client, headers, preset.id, [profile.id])
    assert targeted.status_code == 200

    response = await client.get(
        f"/api/v1/presets/{preset.id}/export/orcaslicer.json", headers=headers
    )
    assert response.status_code == 200
    exported = response.json()
    assert exported["compatible_printers_condition"] == 'printer_model=="Voron 2.4 350"'
    assert exported["compatible_printers"] == []


@pytest.mark.asyncio
async def test_export_compatible_ors_system_models(
    client: AsyncClient, db_session: AsyncSession
):
    """Several targets, all resolvable → OR-condition across their models."""
    headers, email = await _register_and_login(client, "scope-exp-or")
    user = await _get_user(db_session, email)
    preset = await _seed_preset(db_session, "exp-or")
    voron = await _seed_system_printer(
        db_session, name="Voron 2.4 350", slug="scope-exp-or-voron"
    )
    p2s = await _seed_system_printer(
        db_session, name="Bambu Lab P2S", slug="scope-exp-or-p2s"
    )
    profile1 = await _seed_profile(
        db_session,
        owner_user_id=user.id,
        slug="scope-exp-or-1",
        name="Voron machine",
        printer=voron,
    )
    profile2 = await _seed_profile(
        db_session,
        owner_user_id=user.id,
        slug="scope-exp-or-2",
        name="P2S machine",
        printer=p2s,
    )
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    response = await _patch_scope(client, headers, preset.id, [profile1.id, profile2.id])
    assert response.status_code == 200

    exported = (
        await client.get(
            f"/api/v1/presets/{preset.id}/export/orcaslicer.json", headers=headers
        )
    ).json()
    condition = exported["compatible_printers_condition"]
    assert 'printer_model=="Voron 2.4 350"' in condition
    assert 'printer_model=="Bambu Lab P2S"' in condition
    assert " or " in condition
    assert exported["compatible_printers"] == []


@pytest.mark.asyncio
async def test_export_mixed_targets_pin_all_by_name(
    client: AsyncClient, db_session: AsyncSession
):
    """A set with at least one custom profile (no resolvable system model)
    pins the whole set by exact profile names — mixing a condition with a
    compatible_printers list would AND them in Orca."""
    headers, email = await _register_and_login(client, "scope-exp-mixed")
    user = await _get_user(db_session, email)
    preset = await _seed_preset(db_session, "exp-mixed")
    voron = await _seed_system_printer(
        db_session, name="Voron 2.4 350", slug="scope-exp-mixed-voron"
    )
    system_profile = await _seed_profile(
        db_session,
        owner_user_id=user.id,
        slug="scope-exp-mixed-sys",
        name="Voron machine",
        printer=voron,
    )
    custom_profile = await _seed_profile(
        db_session,
        owner_user_id=user.id,
        slug="scope-exp-mixed-custom",
        name="My Custom Rig 0.6",
    )
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    response = await _patch_scope(
        client, headers, preset.id, [system_profile.id, custom_profile.id]
    )
    assert response.status_code == 200

    exported = (
        await client.get(
            f"/api/v1/presets/{preset.id}/export/orcaslicer.json", headers=headers
        )
    ).json()
    assert sorted(exported["compatible_printers"]) == sorted(
        ["Voron machine", "My Custom Rig 0.6"]
    )
    assert "compatible_printers_condition" not in exported


@pytest.mark.asyncio
async def test_export_unscoped_keeps_authored_links(
    client: AsyncClient, db_session: AsyncSession
):
    """Unscoped (and not saved at all) — today's behavior: condition from the
    preset's catalog PresetPrinter links."""
    headers, _ = await _register_and_login(client, "scope-exp-unscoped")
    preset = await _seed_preset(db_session, "exp-unscoped")
    authored = await _seed_system_printer(
        db_session, name="Bambu Lab X1 Carbon", slug="scope-exp-unscoped-x1c"
    )
    db_session.add(PresetPrinter(preset_id=preset.id, printer_id=authored.id, is_primary=True))
    await db_session.commit()

    # not saved at all
    exported = (
        await client.get(
            f"/api/v1/presets/{preset.id}/export/orcaslicer.json", headers=headers
        )
    ).json()
    assert exported["compatible_printers_condition"] == 'printer_model=="Bambu Lab X1 Carbon"'

    # saved with default (unscoped) scope — same result
    await _save_preset(client, headers, preset.id)
    exported = (
        await client.get(
            f"/api/v1/presets/{preset.id}/export/orcaslicer.json", headers=headers
        )
    ).json()
    assert exported["compatible_printers_condition"] == 'printer_model=="Bambu Lab X1 Carbon"'


@pytest.mark.asyncio
async def test_export_deactivated_target_falls_back(
    client: AsyncClient, db_session: AsyncSession
):
    """A target whose profile was deactivated must not break export — with no
    live targets left it falls back to the authored-links behavior."""
    headers, email = await _register_and_login(client, "scope-exp-gone")
    user = await _get_user(db_session, email)
    preset = await _seed_preset(db_session, "exp-gone")
    profile = await _seed_profile(
        db_session, owner_user_id=user.id, slug="scope-exp-gone-p", name="Gone Soon"
    )
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    targeted = await _patch_scope(client, headers, preset.id, [profile.id])
    assert targeted.status_code == 200

    profile.active = False
    await db_session.commit()

    exported_response = await client.get(
        f"/api/v1/presets/{preset.id}/export/orcaslicer.json", headers=headers
    )
    assert exported_response.status_code == 200
    exported = exported_response.json()
    assert exported["compatible_printers"] == []
    assert "compatible_printers_condition" not in exported


@pytest.mark.asyncio
async def test_unsave_removes_target_rows(client: AsyncClient, db_session: AsyncSession):
    """Removing a preset from the library must not leave orphan target rows
    (ORM delete-orphan cascade; profile deletion is covered by the DB-level
    ON DELETE CASCADE, which SQLite test engine does not enforce)."""
    headers, email = await _register_and_login(client, "scope-cascade")
    user = await _get_user(db_session, email)
    preset = await _seed_preset(db_session, "cascade")
    profile = await _seed_profile(
        db_session, owner_user_id=user.id, slug="scope-cascade-p", name="Doomed"
    )
    await db_session.commit()
    await _save_preset(client, headers, preset.id)

    response = await _patch_scope(client, headers, preset.id, [profile.id])
    assert response.status_code == 200

    unsave = await client.delete(f"/api/v1/saved-presets/{preset.id}", headers=headers)
    assert unsave.status_code == 204

    result = await db_session.execute(
        select(UserSavedPresetTarget).where(
            UserSavedPresetTarget.printer_profile_id == profile.id
        )
    )
    assert result.scalars().all() == []


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
    assert saved.target_printer_profile_ids == []
