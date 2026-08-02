"""The path presets actually travel: OrcaSlicer sends filament presets to FilamentHub.

This is the core of the product and it had no coverage at all. Three lookups in
the import read JSON through a PostgreSQL-only construct, so the whole endpoint
raised on the SQLite test engine and could only ever be checked by hand against
a development server. The lookups are portable now, and this is what they were
blocking.

Nothing here proves anything about the account lock that serialises concurrent
imports: that is a PostgreSQL advisory lock and SQLite has no such thing. The
lock is verified against a real database.
"""

import hashlib

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User
from tests.conftest import registration_payload

IMPORT_URL = "/api/v1/orcaslicer/filaments/import"


async def _signed_in(client: AsyncClient, db: AsyncSession, suffix: str) -> tuple[dict, User]:
    email = f"{suffix}@example.com"
    password = "testpassword123"
    registered = await client.post(
        "/api/v1/auth/register",
        json=registration_payload(
            email=email, username=f"user_{suffix}", password=password
        ),
    )
    assert registered.status_code == 201

    logged_in = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert logged_in.status_code == 200

    person = await db.scalar(select(User).where(User.email == email))
    return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}, person


def _preset(name: str, **overrides) -> dict:
    """A preset shaped the way the plugin sends one."""
    payload = {
        "name": name,
        "external_id": f"orca-{name.lower().replace(' ', '-')}",
        "extruder_temp": 210,
        "bed_temp": 60,
        "orcaslicer_settings": {
            "filament_type": ["PLA"],
            "filament_vendor": ["Test Vendor"],
            "nozzle_temperature": ["210"],
        },
    }
    payload.update(overrides)
    return payload


async def _import(client: AsyncClient, headers: dict, *profiles: dict):
    return await client.post(IMPORT_URL, headers=headers, json={"profiles": list(profiles)})


@pytest.mark.asyncio
async def test_a_users_own_preset_arrives_as_a_draft(
    client: AsyncClient, db_session: AsyncSession
):
    """Someone else's preset is not published — it waits as the author's draft."""
    headers, person = await _signed_in(client, db_session, "orca-import-draft")

    response = await _import(client, headers, _preset("Shop PLA"))

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["status"] == "created"

    draft = await db_session.scalar(
        select(Preset).where(Preset.external_id == "orca-shop-pla")
    )
    assert draft is not None
    assert draft.user_id == person.id
    assert draft.active is False
    assert draft.moderation_status == PresetModerationStatus.PENDING
    assert draft.extruder_temp == 210
    assert draft.orcaslicer_settings["fhub_draft_id"] == f"draft_{person.id}_orca-shop-pla"


@pytest.mark.asyncio
async def test_sending_the_same_preset_again_updates_it(
    client: AsyncClient, db_session: AsyncSession
):
    headers, _ = await _signed_in(client, db_session, "orca-import-again")

    first = await _import(client, headers, _preset("Repeat PLA"))
    second = await _import(client, headers, _preset("Repeat PLA", extruder_temp=225))

    assert first.json()["results"][0]["status"] == "created"
    assert second.json()["results"][0]["status"] != "created"

    presets = (
        await db_session.execute(
            select(Preset).where(Preset.external_id == "orca-repeat-pla")
        )
    ).scalars().all()
    assert len(presets) == 1
    await db_session.refresh(presets[0])
    assert presets[0].extruder_temp == 225


@pytest.mark.asyncio
async def test_a_draft_is_recognised_by_its_marker_after_orca_renumbers_it(
    client: AsyncClient, db_session: AsyncSession
):
    """OrcaSlicer's own identifiers have changed format more than once.

    The draft marker FilamentHub writes into the preset survives that, and
    finding a draft by it is one of the lookups that used to be unreachable
    from the tests. The preset is also renamed here on purpose: with the name
    unchanged the search by name would find it anyway and the marker would
    prove nothing.
    """
    headers, person = await _signed_in(client, db_session, "orca-import-marker")

    created = await _import(client, headers, _preset("Marker PLA"))
    assert created.json()["results"][0]["status"] == "created"
    marker = f"draft_{person.id}_orca-marker-pla"

    renumbered = _preset("Marker PLA, renamed by its owner")
    renumbered["external_id"] = "orca-brand-new-identifier"
    renumbered["orcaslicer_settings"] = {
        **renumbered["orcaslicer_settings"],
        "fhub_draft_id": marker,
    }
    again = await _import(client, headers, renumbered)

    assert again.json()["results"][0]["status"] != "created"
    total = await db_session.scalar(
        select(func.count()).select_from(Preset).where(Preset.user_id == person.id)
    )
    assert total == 1


@pytest.mark.asyncio
async def test_a_draft_already_promoted_is_left_alone(
    client: AsyncClient, db_session: AsyncSession
):
    """Once a draft becomes a published preset, re-sending the template must not undo it.

    The published preset remembers where it came from; that memory is the second
    of the lookups this file exists to cover.
    """
    headers, person = await _signed_in(client, db_session, "orca-import-promoted")

    promoted = Preset(
        name="Promoted PLA",
        user_id=person.id,
        extruder_temp=215,
        bed_temp=60,
        active=True,
        moderation_status=PresetModerationStatus.APPROVED,
        orcaslicer_settings={"derived_from_external_id": "orca-template-source"},
    )
    db_session.add(promoted)
    await db_session.commit()

    response = await _import(
        client, headers, _preset("Template PLA", external_id="orca-template-source")
    )

    result = response.json()["results"][0]
    assert result["status"] == "skipped"
    assert result["fhub_id"] == promoted.id

    total = await db_session.scalar(
        select(func.count()).select_from(Preset).where(Preset.user_id == person.id)
    )
    assert total == 1


@pytest.mark.asyncio
async def test_a_promoted_draft_is_recognised_by_its_draft_marker(
    client: AsyncClient, db_session: AsyncSession
):
    """The same protection when the template carries no identifier of its own."""
    headers, person = await _signed_in(client, db_session, "orca-import-promoted-marker")

    template = _preset("Nameless Template")
    template["external_id"] = None
    marker = f"draft_{person.id}_" + hashlib.md5(b"Nameless Template").hexdigest()[:8]

    # Published under its own name, as a promoted preset is: were it still
    # called what the template is called, the search by name would find it
    # first and this lookup would never be reached.
    promoted = Preset(
        name="Shop PLA, tuned",
        user_id=person.id,
        extruder_temp=215,
        bed_temp=60,
        active=True,
        moderation_status=PresetModerationStatus.APPROVED,
        orcaslicer_settings={"derived_from_draft_id": marker},
    )
    db_session.add(promoted)
    await db_session.commit()

    response = await _import(client, headers, template)

    assert response.json()["results"][0]["status"] == "skipped"
    total = await db_session.scalar(
        select(func.count()).select_from(Preset).where(Preset.user_id == person.id)
    )
    assert total == 1


@pytest.mark.asyncio
async def test_one_batch_of_the_same_preset_leaves_one_row(
    client: AsyncClient, db_session: AsyncSession
):
    """A plugin that repeats itself within a single send must not multiply."""
    headers, person = await _signed_in(client, db_session, "orca-import-batch-dup")

    response = await _import(client, headers, *[_preset("Dup PLA") for _ in range(6)])

    assert response.status_code == 200
    statuses = [item["status"] for item in response.json()["results"]]
    assert statuses.count("created") == 1
    assert "error" not in statuses

    total = await db_session.scalar(
        select(func.count()).select_from(Preset).where(Preset.user_id == person.id)
    )
    assert total == 1


@pytest.mark.asyncio
async def test_one_bad_preset_does_not_cost_the_others(
    client: AsyncClient, db_session: AsyncSession
):
    """A name OrcaSlicer could never have saved is refused on its own."""
    headers, person = await _signed_in(client, db_session, "orca-import-mixed")

    response = await _import(
        client,
        headers,
        _preset("Good One"),
        _preset("Bad/Name*Here"),
        _preset("Good Two"),
    )

    assert response.status_code == 200
    statuses = [item["status"] for item in response.json()["results"]]
    assert statuses[0] == "created"
    assert statuses[1] == "error"
    assert statuses[2] == "created"

    total = await db_session.scalar(
        select(func.count()).select_from(Preset).where(Preset.user_id == person.id)
    )
    assert total == 2


@pytest.mark.asyncio
async def test_an_oversized_batch_is_refused_whole(
    client: AsyncClient, db_session: AsyncSession
):
    """Past the batch limit nothing is written at all, not the first fifty."""
    headers, person = await _signed_in(client, db_session, "orca-import-oversized")

    response = await _import(
        client, headers, *[_preset(f"Bulk {number}") for number in range(51)]
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ERR_TOO_MANY_PROFILES"

    total = await db_session.scalar(
        select(func.count()).select_from(Preset).where(Preset.user_id == person.id)
    )
    assert total == 0


@pytest.mark.asyncio
async def test_import_can_be_switched_off_per_account(
    client: AsyncClient, db_session: AsyncSession
):
    headers, person = await _signed_in(client, db_session, "orca-import-disabled")
    person.allow_filament_presets_import = False
    await db_session.commit()

    response = await _import(client, headers, _preset("Refused PLA"))

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ERR_IMPORT_FILAMENT_DISABLED"
