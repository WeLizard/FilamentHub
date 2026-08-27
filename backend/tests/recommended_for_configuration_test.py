"""Catalog recommendations resolved through the printer→configuration chain.

The configuration (PrinterProfile) resolves the catalog printer context on the
backend; a supplied physical printer must belong to the user and be linked to
the configuration. The connection endpoint is never involved.
"""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_printer import PresetPrinter
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_saved_preset import UserSavedPreset
from tests.conftest import accepted_legal

URL = "/api/v1/presets/recommended-for-configuration"


async def _catalog_printer(
    db: AsyncSession,
    *,
    max_extruder_temp: int | None = None,
) -> Printer:
    printer = Printer(
        name="Voron 2.4 350",
        manufacturer="Voron",
        model="2.4 350",
        slug="voron-2-4-350",
        nozzle_diameter=0.4,
        build_volume_x=350,
        build_volume_y=350,
        build_volume_z=350,
        max_extruder_temp=max_extruder_temp,
    )
    db.add(printer)
    await db.commit()
    await db.refresh(printer)
    return printer


async def _profile(
    db: AsyncSession,
    user: User,
    catalog_id: int | None,
    suffix: str = "04",
    orcaslicer_settings: dict | None = None,
) -> PrinterProfile:
    profile = PrinterProfile(
        owner_user_id=user.id,
        printer_id=catalog_id,
        name=f"Voron 2.4 350 · {suffix}",
        slug=f"voron-2-4-350-{suffix}",
        nozzle_diameters=[0.4],
        orcaslicer_settings=orcaslicer_settings or {},
        active=True,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def _device(db: AsyncSession, user: User, name: str = "My Voron") -> UserPrinterDevice:
    device = UserPrinterDevice(user_id=user.id, name=name)
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return device


async def _link(db: AsyncSession, user: User, device_id: int, profile_id: int) -> None:
    db.add(
        UserPrinterProfileLink(
            user_id=user.id, physical_printer_id=device_id, printer_profile_id=profile_id
        )
    )
    await db.commit()


async def _filament(
    db: AsyncSession,
    *,
    required_nozzle_hrc: int | None = None,
) -> Filament:
    brand = Brand(
        name=f"Recommendation Brand {required_nozzle_hrc or 'plain'}",
        slug=f"recommendation-brand-{required_nozzle_hrc or 'plain'}",
        active=True,
        verified=True,
    )
    db.add(brand)
    await db.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Exact recommendation material",
        slug=f"exact-recommendation-{required_nozzle_hrc or 'plain'}",
        material_type="PLA",
        active=True,
        required_nozzle_hrc=required_nozzle_hrc,
    )
    db.add(filament)
    await db.commit()
    await db.refresh(filament)
    return filament


async def _preset_for(
    db: AsyncSession,
    catalog: Printer,
    *,
    filament_id: int | None = None,
    name: str = "Voron PLA 210/60",
    extruder_temp: float = 210,
    is_official: bool = True,
    rating: float | None = None,
) -> Preset:
    preset = Preset(
        filament_id=filament_id,
        name=name,
        extruder_temp=extruder_temp,
        bed_temp=60,
        is_official=is_official,
        active=True,
        moderation_status=PresetModerationStatus.APPROVED,
        rating=rating,
    )
    preset.printer_links = [PresetPrinter(printer=catalog, is_primary=True)]
    db.add(preset)
    await db.commit()
    return preset


@pytest.mark.asyncio
async def test_config_resolves_catalog_and_recommends(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    catalog = await _catalog_printer(db_session)
    await _preset_for(db_session, catalog)
    profile = await _profile(db_session, auth_user, catalog.id)

    resp = await auth_client.get(URL, params={"printer_profile_id": profile.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["printer_id"] == catalog.id
    assert body["printer_name"] == "Voron 2.4 350"
    assert len(body["items"]) == 1


@pytest.mark.asyncio
async def test_unbound_config_still_recommends(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    # No physical printer at all — the config alone drives recommendations.
    catalog = await _catalog_printer(db_session)
    await _preset_for(db_session, catalog)
    profile = await _profile(db_session, auth_user, catalog.id)

    resp = await auth_client.get(URL, params={"printer_profile_id": profile.id})
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


@pytest.mark.asyncio
async def test_linked_physical_printer_ok(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    catalog = await _catalog_printer(db_session)
    await _preset_for(db_session, catalog)
    profile = await _profile(db_session, auth_user, catalog.id)
    device = await _device(db_session, auth_user)
    await _link(db_session, auth_user, device.id, profile.id)

    resp = await auth_client.get(
        URL, params={"printer_profile_id": profile.id, "physical_printer_id": device.id}
    )
    assert resp.status_code == 200
    assert resp.json()["printer_id"] == catalog.id


@pytest.mark.asyncio
async def test_physical_printer_must_be_linked(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    catalog = await _catalog_printer(db_session)
    profile = await _profile(db_session, auth_user, catalog.id)
    device = await _device(db_session, auth_user)  # not linked to the profile

    resp = await auth_client.get(
        URL, params={"printer_profile_id": profile.id, "physical_printer_id": device.id}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "ERR_PRINTER_PROFILE_NOT_LINKED"


@pytest.mark.asyncio
async def test_physical_printer_ownership_enforced(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    other = User(
        email="other@example.com", username="other", password_hash="$2b$12$test", active=True
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    catalog = await _catalog_printer(db_session)
    profile = await _profile(db_session, auth_user, catalog.id)
    foreign_device = await _device(db_session, other, name="Not yours")

    resp = await auth_client.get(
        URL,
        params={"printer_profile_id": profile.id, "physical_printer_id": foreign_device.id},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ERR_DEVICE_NOT_FOUND"


@pytest.mark.asyncio
async def test_foreign_profile_hidden(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    other = User(
        email="other2@example.com", username="other2", password_hash="$2b$12$test", active=True
    )
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)

    catalog = await _catalog_printer(db_session)
    foreign_profile = await _profile(db_session, other, catalog.id)

    resp = await auth_client.get(URL, params={"printer_profile_id": foreign_profile.id})
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ERR_PRINTER_PROFILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_ownerless_official_config_not_selectable(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    # Shared/official configurations (owner_user_id IS NULL) are not selectable
    # here: recommendations run against the user's own configurations only.
    catalog = await _catalog_printer(db_session)
    official = PrinterProfile(
        owner_user_id=None,
        printer_id=catalog.id,
        name="Official Voron",
        slug="official-voron",
        is_official=True,
        active=True,
    )
    db_session.add(official)
    await db_session.commit()
    await db_session.refresh(official)

    resp = await auth_client.get(URL, params={"printer_profile_id": official.id})
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ERR_PRINTER_PROFILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_config_without_catalog_model(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    profile = await _profile(db_session, auth_user, None)  # no catalog link

    resp = await auth_client.get(URL, params={"printer_profile_id": profile.id})
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "ERR_PRINTER_NOT_FOUND"


@pytest.mark.asyncio
async def test_compatible_community_ranks_above_incompatible_official(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    catalog = await _catalog_printer(db_session, max_extruder_temp=250)
    filament = await _filament(db_session)
    official = await _preset_for(
        db_session,
        catalog,
        filament_id=filament.id,
        name="Official but too hot",
        extruder_temp=280,
        is_official=True,
    )
    community = await _preset_for(
        db_session,
        catalog,
        filament_id=filament.id,
        name="Community compatible",
        extruder_temp=230,
        is_official=False,
        rating=4.8,
    )
    profile = await _profile(db_session, auth_user, catalog.id)

    resp = await auth_client.get(
        URL,
        params={"printer_profile_id": profile.id, "filament_id": filament.id},
    )

    assert resp.status_code == 200
    items = resp.json()["items"]
    assert [item["preset"]["id"] for item in items] == [community.id, official.id]
    assert items[0]["compatibility_status"] == "compatible"
    assert items[1]["compatibility_status"] == "incompatible"
    assert items[1]["hard_conflicts"] == ["hotend_temperature"]


@pytest.mark.asyncio
async def test_missing_machine_specs_report_unknown_coverage(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    catalog = await _catalog_printer(db_session)
    filament = await _filament(db_session)
    await _preset_for(db_session, catalog, filament_id=filament.id)
    profile = await _profile(db_session, auth_user, catalog.id)

    resp = await auth_client.get(
        URL,
        params={"printer_profile_id": profile.id, "filament_id": filament.id},
    )

    item = resp.json()["items"][0]
    assert item["compatibility_status"] == "unknown"
    assert item["compatibility_coverage"] == 0.0
    assert item["compatibility_checks"][0]["status"] == "unknown"


@pytest.mark.asyncio
async def test_nozzle_conflict_and_existing_saved_state_are_explained(
    auth_client: AsyncClient, db_session: AsyncSession, auth_user: User
) -> None:
    catalog = await _catalog_printer(db_session, max_extruder_temp=300)
    filament = await _filament(db_session, required_nozzle_hrc=50)
    preset = await _preset_for(db_session, catalog, filament_id=filament.id)
    profile = await _profile(
        db_session,
        auth_user,
        catalog.id,
        orcaslicer_settings={"nozzle_type": ["brass"]},
    )
    db_session.add(
        UserSavedPreset(
            user_id=auth_user.id,
            preset_id=preset.id,
            sync=False,
        )
    )
    await db_session.commit()

    resp = await auth_client.get(
        URL,
        params={"printer_profile_id": profile.id, "filament_id": filament.id},
    )

    item = resp.json()["items"][0]
    assert item["compatibility_status"] == "incompatible"
    assert item["compatibility_coverage"] == 1.0
    assert item["hard_conflicts"] == ["nozzle_hrc"]
    assert item["saved"] is True
    assert item["sync_enabled"] is False


@pytest.mark.asyncio
async def test_concurrent_explicit_save_is_idempotent_and_keeps_sync_off(tmp_path) -> None:
    """Recommendation selection stays separate from one explicit library write."""
    from sqlalchemy import func, select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.security import create_access_token
    from app.db.base import Base
    from app.db.session import get_db
    from app.main import app

    database_path = (tmp_path / "recommendation-save.db").as_posix()
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database_path}",
        connect_args={"timeout": 30},
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    had_db_override = get_db in app.dependency_overrides
    previous_db_override = app.dependency_overrides.get(get_db)
    limiter_was_enabled = app.state.limiter.enabled

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as setup_db:
            user = User(
                email="recommendation-save@example.com",
                username="recommendation_save",
                password_hash="unused",
                active=True,
                email_verified=True,
                **accepted_legal(),
            )
            preset = Preset(
                name="Explicit save only",
                extruder_temp=210,
                bed_temp=60,
                is_official=True,
                active=True,
                moderation_status=PresetModerationStatus.APPROVED,
            )
            setup_db.add_all([user, preset])
            await setup_db.commit()
            await setup_db.refresh(user)
            await setup_db.refresh(preset)
            token = create_access_token({"sub": user.email})
            preset_id = preset.id

        async def override_get_db():
            async with session_factory() as request_db:
                yield request_db

        app.dependency_overrides[get_db] = override_get_db
        app.state.limiter.enabled = False
        transport = ASGITransport(app=app)
        headers = {"Authorization": f"Bearer {token}"}
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            responses = await asyncio.gather(
                client.post(
                    "/api/v1/saved-presets/",
                    json={"preset_id": preset_id, "sync": False},
                    headers=headers,
                ),
                client.post(
                    "/api/v1/saved-presets/",
                    json={"preset_id": preset_id, "sync": False},
                    headers=headers,
                ),
            )

        assert [response.status_code for response in responses] == [201, 201]
        assert [response.json()["sync"] for response in responses] == [False, False]
        async with session_factory() as verification_db:
            row_count = await verification_db.scalar(
                select(func.count()).select_from(UserSavedPreset)
            )
            assert row_count == 1
            saved = await verification_db.scalar(select(UserSavedPreset))
            assert saved is not None
            assert saved.sync is False
    finally:
        if had_db_override:
            app.dependency_overrides[get_db] = previous_db_override
        else:
            app.dependency_overrides.pop(get_db, None)
        app.state.limiter.enabled = limiter_was_enabled
        await engine.dispose()
