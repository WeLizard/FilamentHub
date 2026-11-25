"""One preset is one colour: other colours get a separate copy.

These tests guard what other people rely on: the preset they use and its
history never change because someone copied it, nobody copies a draft that
is not theirs, and a published preset never moves to another colour.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.preset_version import PresetVersion
from app.models.user import User


async def _person(db: AsyncSession, name: str) -> dict[str, str]:
    from app.core.security import create_access_token
    from app.services.legal_acceptance_service import (
        CURRENT_PERSONAL_DATA_CONSENT_VERSION,
        CURRENT_TERMS_VERSION,
    )

    user = User(
        email=f"{name}@example.com",
        username=name,
        password_hash="$2b$12$test",
        active=True,
        email_verified=True,
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    db.add(user)
    await db.commit()
    return {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}


async def _material(db: AsyncSession) -> tuple[Filament, Filament, Filament]:
    """Red and blue of one material, and a different material of the brand."""
    brand = Brand(name="Copy Brand", slug="copy-brand", active=True)
    db.add(brand)
    await db.flush()
    red, blue, silk = (
        Filament(
            brand_id=brand.id,
            name=name,
            slug=slug,
            material_type="PLA",
            color_name=colour,
            color_hex=hex_value,
            active=True,
        )
        for name, slug, colour, hex_value in (
            ("Copy PLA", "copy-pla-red", "Red", "#FF0000"),
            ("Copy PLA", "copy-pla-blue", "Blue", "#0000FF"),
            ("Copy PLA Silk", "copy-pla-silk-red", "Red", "#FF0000"),
        )
    )
    db.add_all([red, blue, silk])
    await db.commit()
    return red, blue, silk


async def _publish(client: AsyncClient, headers: dict[str, str], filament: Filament) -> dict:
    response = await client.post(
        "/api/v1/presets/",
        json={
            "filament_id": filament.id,
            "name": "Copy PLA Red fast",
            "extruder_temp": 215.0,
            "bed_temp": 60.0,
            "orcaslicer_settings": {
                "filament_flow_ratio": ["0.97"],
                "filament_colour": [filament.color_hex],
                "default_filament_colour": [filament.color_hex],
            },
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _versions(db: AsyncSession, preset_id: int) -> list[tuple[int, str]]:
    rows = await db.execute(
        select(PresetVersion.id, PresetVersion.content_hash)
        .where(PresetVersion.preset_id == preset_id)
        .order_by(PresetVersion.id)
    )
    return [tuple(row) for row in rows]


@pytest.mark.asyncio
async def test_copy_for_another_colour_leaves_the_source_and_its_history_untouched(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    author = await _person(db_session, "copy_author")
    copier = await _person(db_session, "copy_reader")
    red, blue, _silk = await _material(db_session)
    source = await _publish(client, author, red)
    versions_before = await _versions(db_session, source["id"])

    response = await client.post(
        f"/api/v1/presets/{source['id']}/copies",
        json={"filament_id": blue.id},
        headers=copier,
    )

    assert response.status_code == 201, response.text
    copy = response.json()
    assert copy["id"] != source["id"]
    assert copy["filament_id"] == blue.id
    assert copy["active"] is False
    assert copy["derived_from_preset_id"] == source["id"]
    assert copy["derived_from_version_id"] == versions_before[-1][0]
    assert copy["name"] == "Copy PLA Blue fast"
    assert (copy["extruder_temp"], copy["bed_temp"]) == (215.0, 60.0)
    settings = copy["orcaslicer_settings"]
    assert settings["filament_flow_ratio"] == ["0.97"]
    assert settings["filament_colour"] == ["#0000FF"]
    assert settings["default_filament_colour"] == ["#0000FF"]
    assert settings["fhub_id"] == copy["id"]

    # Asking again does not pile up drafts.
    again = await client.post(
        f"/api/v1/presets/{source['id']}/copies",
        json={"filament_id": blue.id},
        headers=copier,
    )
    assert again.status_code == 200, again.text
    assert again.json()["id"] == copy["id"]

    stored = await db_session.get(Preset, source["id"])
    assert stored is not None
    await db_session.refresh(stored)
    assert stored.filament_id == red.id
    assert stored.name == source["name"]
    assert stored.active is True
    assert stored.orcaslicer_settings == source["orcaslicer_settings"]
    assert await _versions(db_session, source["id"]) == versions_before


@pytest.mark.asyncio
async def test_nobody_copies_a_draft_that_is_not_theirs(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    author = await _person(db_session, "draft_author")
    stranger = await _person(db_session, "draft_stranger")
    red, blue, silk = await _material(db_session)
    author_id = await db_session.scalar(
        select(User.id).where(User.email == "draft_author@example.com")
    )
    draft = Preset(
        filament_id=red.id,
        user_id=author_id,
        created_by_user_id=author_id,
        name="Private red tune",
        extruder_temp=210,
        bed_temp=55,
        orcaslicer_settings={"filament_flow_ratio": ["0.95"]},
        active=False,
        moderation_status=PresetModerationStatus.PENDING,
        source="orcaslicer",
    )
    db_session.add(draft)
    await db_session.commit()

    refused = await client.post(
        f"/api/v1/presets/{draft.id}/copies",
        json={"filament_id": blue.id},
        headers=stranger,
    )
    assert refused.status_code == 404, refused.text
    assert refused.json()["detail"]["code"] == "ERR_PRESET_NOT_FOUND"
    assert await db_session.scalar(
        select(Preset.id).where(Preset.derived_from_preset_id == draft.id)
    ) is None

    # A copy is for another colour of the same material, not any material.
    other_material = await client.post(
        f"/api/v1/presets/{draft.id}/copies",
        json={"filament_id": silk.id},
        headers=author,
    )
    assert other_material.status_code == 422, other_material.text
    assert other_material.json()["detail"]["code"] == "ERR_PRESET_COPY_NOT_VARIANT"

    own = await client.post(
        f"/api/v1/presets/{draft.id}/copies",
        json={"filament_id": blue.id},
        headers=author,
    )
    assert own.status_code == 201, own.text


@pytest.mark.asyncio
async def test_published_preset_never_moves_to_another_colour(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    author = await _person(db_session, "lock_author")
    red, blue, _silk = await _material(db_session)
    red_id, blue_id = red.id, blue.id
    published = await _publish(client, author, red)

    locked = await client.patch(
        f"/api/v1/presets/{published['id']}",
        json={"filament_id": blue_id},
        headers=author,
    )
    assert locked.status_code == 409, locked.text
    assert locked.json()["detail"]["code"] == "ERR_PRESET_COLOR_LOCKED"
    stored = await db_session.get(Preset, published["id"])
    assert stored is not None
    await db_session.refresh(stored)
    assert stored.filament_id == red_id

    # A draft nobody else has seen is still the author's to recolour.
    copy = await client.post(
        f"/api/v1/presets/{published['id']}/copies",
        json={"filament_id": blue_id},
        headers=author,
    )
    assert copy.status_code == 201, copy.text
    switched = await client.patch(
        f"/api/v1/presets/{copy.json()['id']}",
        json={"filament_id": red_id},
        headers=author,
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["filament_id"] == red_id


async def _other_material(db: AsyncSession, brand_id: int) -> int:
    petg = Filament(
        brand_id=brand_id,
        name="Copy PETG",
        slug="copy-petg-green",
        material_type="PETG",
        color_name="Green",
        color_hex="#00FF00",
        active=True,
    )
    db.add(petg)
    await db.commit()
    return petg.id


@pytest.mark.asyncio
async def test_replaced_material_stays_with_the_version_saved_for_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    author = await _person(db_session, "relink_author")
    reader = await _person(db_session, "relink_reader")
    red, _blue, _silk = await _material(db_session)
    red_id = red.id
    petg_id = await _other_material(db_session, red.brand_id)
    published = await _publish(client, author, red)
    first_version = (await _versions(db_session, published["id"]))[-1][0]

    relinked = await client.patch(
        f"/api/v1/presets/{published['id']}",
        json={"filament_id": petg_id},
        headers=author,
    )
    assert relinked.status_code == 200, relinked.text
    materials = dict(
        (
            await db_session.execute(
                select(PresetVersion.id, PresetVersion.filament_id).where(
                    PresetVersion.preset_id == published["id"]
                )
            )
        ).all()
    )
    assert materials[first_version] == red_id
    assert sorted(materials.values()) == sorted([red_id, petg_id])

    # Someone who stays on the first version keeps its material.
    pinned = await client.get(
        f"/api/v1/presets/{published['id']}/export/orcaslicer.json",
        params={"version_id": first_version},
        headers=reader,
    )
    assert pinned.status_code == 200, pinned.text
    assert pinned.json()["filament_type"] == ["PLA"]
    assert pinned.json()["filament_colour"] == ["#FF0000"]
    latest = await client.get(
        f"/api/v1/presets/{published['id']}/export/orcaslicer.json",
        headers=reader,
    )
    assert latest.json()["filament_type"] == ["PETG"]
    assert latest.json()["filament_colour"] == ["#00FF00"]

    restored = await client.post(
        f"/api/v1/presets/{published['id']}/versions/{first_version}/restore",
        headers=author,
    )
    assert restored.status_code == 200, restored.text
    stored = await db_session.get(Preset, published["id"])
    assert stored is not None
    await db_session.refresh(stored)
    assert stored.filament_id == red_id


@pytest.mark.asyncio
async def test_no_detour_moves_a_preset_people_use_to_another_colour(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    author = await _person(db_session, "detour_author")
    red, blue, _silk = await _material(db_session)
    red_id, blue_id = red.id, blue.id
    petg_id = await _other_material(db_session, red.brand_id)
    published = await _publish(client, author, red)

    async def relink(preset_id: int, filament_id: int) -> int:
        response = await client.patch(
            f"/api/v1/presets/{preset_id}",
            json={"filament_id": filament_id},
            headers=author,
        )
        return response.status_code

    # Through an unrelated material and on to another colour of the first.
    assert await relink(published["id"], petg_id) == 200
    assert await relink(published["id"], blue_id) == 409
    # Back to the material it was made for is not a colour change.
    assert await relink(published["id"], red_id) == 200

    # A copy recoloured while private and then published keeps the colour it
    # was published in: restoring the earlier colour is refused too.
    copy = await client.post(
        f"/api/v1/presets/{published['id']}/copies",
        json={"filament_id": blue_id},
        headers=author,
    )
    assert copy.status_code == 201, copy.text
    copy_id = copy.json()["id"]
    blue_version = (await _versions(db_session, copy_id))[-1][0]
    assert await relink(copy_id, red_id) == 200
    publish = await client.patch(
        f"/api/v1/presets/{copy_id}", json={"active": True}, headers=author
    )
    assert publish.status_code == 200, publish.text
    assert publish.json()["active"] is True

    refused = await client.post(
        f"/api/v1/presets/{copy_id}/versions/{blue_version}/restore",
        headers=author,
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"]["code"] == "ERR_PRESET_COLOR_LOCKED"
    stored = await db_session.get(Preset, copy_id)
    assert stored is not None
    await db_session.refresh(stored)
    assert stored.filament_id == red_id
