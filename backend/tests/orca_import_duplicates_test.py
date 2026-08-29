"""One OrcaSlicer identifier belongs to one row inside one account.

Two slicers signed into the same account used to import the same preset at the
same moment and get two copies. The database now refuses the second row, the
account lock keeps imports from racing into that refusal, and the endpoints
that accept an identifier by hand answer instead of failing.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preset import Preset
from app.models.print_profile import PrintProfile
from app.models.printer_profile import PrinterProfile
from app.models.user import User
from tests.conftest import registration_payload


async def _register_and_login(client: AsyncClient, suffix: str) -> dict[str, str]:
    email = f"{suffix}@example.com"
    password = "testpassword123"
    registered = await client.post(
        "/api/v1/auth/register",
        json=registration_payload(
            email=email, username=f"user_{suffix}", password=password, role="user"
        ),
    )
    assert registered.status_code == 201

    logged_in = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert logged_in.status_code == 200
    return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}


@pytest.mark.asyncio
async def test_an_account_cannot_hold_two_presets_with_one_orca_identifier(
    db_session: AsyncSession,
):
    user = User(
        email="two-presets@example.com",
        username="two_presets",
        password_hash="x",
        active=True,
    )
    db_session.add(user)
    await db_session.flush()

    db_session.add(
        Preset(
            name="First", user_id=user.id, external_id="orca-abc", extruder_temp=210, bed_temp=60
        )
    )
    await db_session.flush()

    db_session.add(
        Preset(
            name="Second", user_id=user.id, external_id="orca-abc", extruder_temp=215, bed_temp=60
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_the_same_identifier_may_live_in_two_different_accounts(
    db_session: AsyncSession,
):
    """People import the same bundled preset; the identifier is only unique per owner."""
    first = User(
        email="owner-one@example.com", username="owner_one", password_hash="x", active=True
    )
    second = User(
        email="owner-two@example.com", username="owner_two", password_hash="x", active=True
    )
    db_session.add_all([first, second])
    await db_session.flush()

    db_session.add_all(
        [
            Preset(
                name="Mine",
                user_id=first.id,
                external_id="orca-shared",
                extruder_temp=210,
                bed_temp=60,
            ),
            Preset(
                name="Yours",
                user_id=second.id,
                external_id="orca-shared",
                extruder_temp=210,
                bed_temp=60,
            ),
        ]
    )
    await db_session.flush()

    assert (
        await db_session.scalar(
            select(func.count()).select_from(Preset).where(Preset.external_id == "orca-shared")
        )
        == 2
    )


@pytest.mark.asyncio
async def test_official_profiles_share_identifiers_without_an_owner(db_session: AsyncSession):
    """Bundle profiles have no owner, so they stay outside the comparison."""
    db_session.add_all(
        [
            PrinterProfile(
                name="Official A", slug="official-a", external_id="orca-machine", is_official=True
            ),
            PrinterProfile(
                name="Official B", slug="official-b", external_id="orca-machine", is_official=True
            ),
        ]
    )
    await db_session.flush()


@pytest.mark.asyncio
async def test_repeated_import_of_one_profile_updates_instead_of_copying(
    client: AsyncClient, db_session: AsyncSession
):
    headers = await _register_and_login(client, "orca-repeat-import")

    payload = {
        "profiles": [
            {
                "external_id": "orca-repeat-1",
                "name": "0.20mm Standard @FilamentHub",
                "slug": "0-20mm-standard-repeat",
                "layer_height_mm": 0.2,
                "orcaslicer_settings": {"layer_height": "0.2"},
            }
        ]
    }

    first = await client.post(
        "/api/v1/orcaslicer/print-profiles/import", headers=headers, json=payload
    )
    second = await client.post(
        "/api/v1/orcaslicer/print-profiles/import", headers=headers, json=payload
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["results"][0]["status"] == "created"
    assert second.json()["results"][0]["status"] == "updated"

    copies = await db_session.scalar(
        select(func.count())
        .select_from(PrintProfile)
        .where(PrintProfile.external_id == "orca-repeat-1")
    )
    assert copies == 1


@pytest.mark.asyncio
async def test_machine_and_process_reimports_keep_opaque_untransported_settings(
    client: AsyncClient, db_session: AsyncSession
):
    headers = await _register_and_login(client, "orca-opaque-profile-reimport")
    cases = (
        (
            "printer-profiles",
            PrinterProfile,
            "orca-opaque-machine",
            "Opaque machine 0.4",
            {
                "nozzle_diameter": ["0.4"],
                "future_scalar": "old",
                "future_object": {"keep": [1, 2]},
                "future_nullable": None,
            },
        ),
        (
            "print-profiles",
            PrintProfile,
            "orca-opaque-process",
            "Opaque process 0.20",
            {
                "layer_height": "0.20",
                "future_scalar": "old",
                "future_object": {"keep": [1, 2]},
                "future_nullable": None,
            },
        ),
    )

    for endpoint, model, external_id, name, settings in cases:
        first = await client.post(
            f"/api/v1/orcaslicer/{endpoint}/import",
            headers=headers,
            json={
                "profiles": [
                    {
                        "external_id": external_id,
                        "name": name,
                        "orcaslicer_settings": settings,
                    }
                ]
            },
        )
        assert first.status_code == 200, first.text
        assert first.json()["results"][0]["status"] == "created"

        second = await client.post(
            f"/api/v1/orcaslicer/{endpoint}/import",
            headers=headers,
            json={
                "profiles": [
                    {
                        "external_id": external_id,
                        "name": name,
                        "orcaslicer_settings": {"future_scalar": "edited"},
                    }
                ]
            },
        )
        assert second.status_code == 200, second.text
        assert second.json()["results"][0]["status"] == "updated"

        profile = await db_session.scalar(
            select(model).where(model.external_id == external_id)
        )
        await db_session.refresh(profile)
        assert profile.orcaslicer_settings["future_scalar"] == "edited"
        assert profile.orcaslicer_settings["future_object"] == {"keep": [1, 2]}
        assert profile.orcaslicer_settings["future_nullable"] is None


@pytest.mark.asyncio
async def test_creating_a_profile_by_hand_reports_a_taken_identifier(
    client: AsyncClient, db_session: AsyncSession
):
    headers = await _register_and_login(client, "orca-manual-profile")

    body = {
        "name": "My process",
        "slug": "my-process",
        "external_id": "orca-manual-1",
        "active": True,
        "source": "user",
    }

    created = await client.post("/api/v1/print-profiles/", headers=headers, json=body)
    assert created.status_code == 201

    duplicate = await client.post(
        "/api/v1/print-profiles/",
        headers=headers,
        json={**body, "slug": "my-process-again"},
    )

    assert duplicate.status_code == 400
    assert duplicate.json()["detail"]["code"] == "ERR_EXTERNAL_ID_EXISTS"

    copies = await db_session.scalar(
        select(func.count()).select_from(PrintProfile).where(
            PrintProfile.external_id == "orca-manual-1"
        )
    )
    assert copies == 1
