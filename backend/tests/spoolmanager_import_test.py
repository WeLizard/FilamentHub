"""OctoPrint SpoolManager CSV intake is previewed and idempotent."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.user_saved_preset import UserSavedPreset
from app.models.user_spool import UserSpool


HEADERS = (
    '"Spool Name","Color Name","Color Code [hex]","Vendor","Material",'
    '"Serialnumber","Density [g/cm3]","Diameter [mm]","Diameter Tolerance[mm]",'
    '"Flow rate compensation [%]","Temperature [C]","Bed Temperature [C]",'
    '"Enclosure Temperature [C]","Offset Temperature [C]",'
    '"Offset Bed Temperature [C]","Offset Enclosure Temperature [C]",'
    '"Total weight [g]","Spool weight [g]","Used weight [g]",'
    '"Total length [mm]","Used length [mm]","First use [dd.mm.yyyy hh:mm]",'
    '"Last use [dd.mm.yyyy hh:mm]","Purchased from",'
    '"Purchased on [dd.mm.yyyy]","Cost","Cost unit","Note"\n'
)


def _csv_row(
    *,
    name: str = "Signal Red PETG",
    vendor: str = "Import Brand",
    material: str = "PETG",
    serial: str = "SERIAL-001",
    color_hex: str = "#FF0000",
    total: str = "1000.0",
    used: str = "123.4",
) -> str:
    values = [
        name,
        "Signal red",
        color_hex,
        vendor,
        material,
        serial,
        "1.27",
        "1.75",
        "0.2",
        "110",
        "242",
        "80",
        "23",
        "-",
        "-",
        "-",
        total,
        "230.0",
        used,
        "1321",
        "234",
        "02.03.2020 10:33",
        "29.07.2026 18:23",
        "Example shop",
        "01.02.2020",
        "12.30",
        "€",
        "Imported note",
    ]
    return ",".join(f'"{value}"' for value in values) + "\n"


@pytest.mark.asyncio
async def test_spoolmanager_preview_import_and_repeat_are_safe(
    auth_client,
    auth_user,
    db_session: AsyncSession,
) -> None:
    brand = Brand(name="Import Brand", slug="import-brand", active=True)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Signal Red PETG",
        slug="import-brand-signal-red-petg",
        material_type="PETG",
        color_name="Signal red",
        color_hex="#FF0000",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)

    payload = (HEADERS + _csv_row()).encode("utf-8")
    preview = await auth_client.post(
        "/api/v1/spools/import/spoolmanager/preview",
        files={"file": ("spools.csv", payload, "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["total_rows"] == 1
    assert body["importable_rows"] == 1
    assert body["matched_rows"] == 1
    assert body["rows"][0]["suggested_filament"]["id"] == filament.id
    fingerprint = body["rows"][0]["fingerprint"]

    imported = await auth_client.post(
        "/api/v1/spools/import/spoolmanager",
        files={"file": ("spools.csv", payload, "text/csv")},
        data={"selected_fingerprints": json.dumps([fingerprint])},
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["created"] == 1
    assert len(imported.json()["created_draft_ids"]) == 1

    result = await db_session.execute(
        select(UserSpool).where(UserSpool.user_id == auth_user.id)
    )
    spool = result.scalar_one()
    assert spool.filament_id == filament.id
    assert spool.initial_weight_g == 1000.0
    assert spool.used_weight_g == 123.4
    assert spool.source == "octoprint_spoolmanager"
    assert spool.extra["display_name"] == "Signal Red PETG"
    assert spool.extra["empty_spool_weight_g"] == "230.0"
    assert spool.extra["currency"] == "€"
    preset = await db_session.scalar(
        select(Preset).where(Preset.id == imported.json()["created_draft_ids"][0])
    )
    assert preset is not None
    assert preset.filament_id == filament.id
    assert preset.active is False
    assert preset.moderation_status == PresetModerationStatus.PENDING
    assert preset.extruder_temp == 242.0
    assert preset.bed_temp == 80.0
    assert preset.flow_rate == 110.0
    assert preset.orcaslicer_settings["import_requires_review"] is True
    saved = await db_session.scalar(
        select(UserSavedPreset).where(UserSavedPreset.preset_id == preset.id)
    )
    assert saved is not None
    assert saved.sync is False

    repeated_preview = await auth_client.post(
        "/api/v1/spools/import/spoolmanager/preview",
        files={"file": ("spools.csv", payload, "text/csv")},
    )
    assert repeated_preview.status_code == 200
    assert repeated_preview.json()["duplicate_rows"] == 1
    assert repeated_preview.json()["rows"][0]["status"] == "already_imported"

    repeated_import = await auth_client.post(
        "/api/v1/spools/import/spoolmanager",
        files={"file": ("spools.csv", payload, "text/csv")},
        data={"selected_fingerprints": json.dumps([fingerprint])},
    )
    assert repeated_import.status_code == 201
    assert repeated_import.json()["created"] == 0
    assert repeated_import.json()["skipped_existing"] == 1
    assert repeated_import.json()["created_draft_ids"] == []


@pytest.mark.asyncio
async def test_spoolmanager_unmatched_row_stays_unlinked(
    auth_client,
    auth_user,
    db_session: AsyncSession,
) -> None:
    payload = (
        HEADERS
        + _csv_row(
            name="Unknown spool",
            vendor="Unknown vendor",
            serial="UNKNOWN-1",
            color_hex="#123456",
        )
    ).encode("utf-8")
    preview = await auth_client.post(
        "/api/v1/spools/import/spoolmanager/preview",
        files={"file": ("unknown.csv", payload, "text/csv")},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["unmatched_rows"] == 1
    assert body["rows"][0]["suggested_filament"] is None
    assert "unmatched_catalog" in body["rows"][0]["warnings"]

    imported = await auth_client.post(
        "/api/v1/spools/import/spoolmanager",
        files={"file": ("unknown.csv", payload, "text/csv")},
        data={
            "selected_fingerprints": json.dumps(
                [body["rows"][0]["fingerprint"]]
            )
        },
    )
    assert imported.status_code == 201

    listed = await auth_client.get("/api/v1/spools")
    assert listed.status_code == 200
    assert listed.json()[0]["filament_id"] is None
    assert listed.json()[0]["extra"]["display_name"] == "Unknown spool"
    draft = await db_session.scalar(
        select(Preset).where(
            Preset.user_id == auth_user.id,
            Preset.source == "octoprint_spoolmanager",
        )
    )
    assert draft is not None
    assert draft.filament_id is None
    assert draft.active is False


@pytest.mark.asyncio
async def test_spoolmanager_rejects_another_csv_shape(auth_client) -> None:
    response = await auth_client.post(
        "/api/v1/spools/import/spoolmanager/preview",
        files={"file": ("wrong.csv", b"name,weight\nspool,1000\n", "text/csv")},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ERR_SPOOL_IMPORT_UNSUPPORTED_COLUMNS"


@pytest.mark.asyncio
async def test_generic_import_detects_spoolmanager(auth_client) -> None:
    payload = (HEADERS + _csv_row()).encode("utf-8")
    response = await auth_client.post(
        "/api/v1/spools/import/preview",
        files={"file": ("spools.csv", payload, "text/csv")},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["detected_format"] == "octoprint_spoolmanager_csv"
    assert body["detected_label"] == "OctoPrint SpoolManager"
    assert body["mapping_required"] is False
    assert body["importable_rows"] == 1


@pytest.mark.asyncio
async def test_unknown_csv_requests_mapping_then_imports_safely(
    auth_client,
) -> None:
    payload = (
        "Name;Brand;Type;Remaining kg;Used kg;Colour;Comment\n"
        "Workshop PETG;Example;PETG;0,75;0,25;#336699;Shelf copy\n"
    ).encode("utf-8")
    first_preview = await auth_client.post(
        "/api/v1/spools/import/preview",
        files={"file": ("inventory.csv", payload, "text/csv")},
    )
    assert first_preview.status_code == 200, first_preview.text
    first_body = first_preview.json()
    assert first_body["detected_format"] is None
    assert first_body["mapping_required"] is True
    assert first_body["available_columns"] == [
        "Name",
        "Brand",
        "Type",
        "Remaining kg",
        "Used kg",
        "Colour",
        "Comment",
    ]
    assert first_body["suggested_mapping"]["fields"]["spool_name"] == "Name"
    assert first_body["suggested_mapping"]["fields"]["remaining_weight"] == (
        "Remaining kg"
    )
    assert first_body["suggested_mapping"]["units"]["remaining_weight"] == "kg"

    mapping = {
        "fields": {
            "spool_name": "Name",
            "vendor": "Brand",
            "material": "Type",
            "remaining_weight": "Remaining kg",
            "used_weight": "Used kg",
            "color_hex": "Colour",
            "note": "Comment",
        },
        "units": {
            "remaining_weight": "kg",
            "used_weight": "kg",
        },
    }
    mapped_preview = await auth_client.post(
        "/api/v1/spools/import/preview",
        files={"file": ("inventory.csv", payload, "text/csv")},
        data={"mapping": json.dumps(mapping)},
    )
    assert mapped_preview.status_code == 200, mapped_preview.text
    mapped_body = mapped_preview.json()
    assert mapped_body["detected_format"] == "custom_csv"
    assert mapped_body["mapping_required"] is False
    assert mapped_body["rows"][0]["initial_weight_g"] == 1000.0
    assert mapped_body["rows"][0]["used_weight_g"] == 250.0
    assert mapped_body["rows"][0]["remaining_weight_g"] == 750.0

    imported = await auth_client.post(
        "/api/v1/spools/import",
        files={"file": ("inventory.csv", payload, "text/csv")},
        data={
            "mapping": json.dumps(mapping),
            "selected_fingerprints": json.dumps(
                [mapped_body["rows"][0]["fingerprint"]]
            ),
        },
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["detected_format"] == "custom_csv"
    assert imported.json()["created"] == 1

    listed = await auth_client.get("/api/v1/spools")
    assert listed.status_code == 200
    spool = listed.json()[0]
    assert spool["source"] == "csv_import"
    assert spool["initial_weight_g"] == 1000.0
    assert spool["used_weight_g"] == 250.0
    assert spool["comment"] == "Shelf copy"
    assert spool["extra"]["import_provider"] == "csv_import"
    assert json.loads(spool["extra"]["source_row"])["Remaining kg"] == "0,75"


@pytest.mark.asyncio
async def test_custom_mapping_rejects_duplicate_column_assignment(auth_client) -> None:
    payload = b"name,weight\nspool,1000\n"
    response = await auth_client.post(
        "/api/v1/spools/import/preview",
        files={"file": ("wrong.csv", payload, "text/csv")},
        data={
            "mapping": json.dumps(
                {
                    "fields": {
                        "spool_name": "name",
                        "initial_weight": "weight",
                        "used_weight": "weight",
                    },
                    "units": {
                        "initial_weight": "g",
                        "used_weight": "g",
                    },
                }
            )
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == (
        "ERR_SPOOL_IMPORT_UNSUPPORTED_COLUMNS"
    )


@pytest.mark.asyncio
async def test_resolving_import_draft_links_the_physical_spool(
    auth_client,
    auth_user,
    db_session: AsyncSession,
) -> None:
    payload = (
        HEADERS
        + _csv_row(
            name="Resolve me",
            vendor="Unmatched import vendor",
            serial="RESOLVE-1",
        )
    ).encode("utf-8")
    preview = await auth_client.post(
        "/api/v1/spools/import/preview",
        files={"file": ("resolve.csv", payload, "text/csv")},
    )
    preview_body = preview.json()
    imported = await auth_client.post(
        "/api/v1/spools/import",
        files={"file": ("resolve.csv", payload, "text/csv")},
        data={
            "selected_fingerprints": json.dumps(
                [preview_body["rows"][0]["fingerprint"]]
            )
        },
    )
    assert imported.status_code == 201, imported.text
    draft_id = imported.json()["created_draft_ids"][0]
    spool_id = imported.json()["created_spool_ids"][0]

    refused = await auth_client.patch(
        f"/api/v1/presets/{draft_id}",
        json={"active": True},
    )
    assert refused.status_code == 400
    assert refused.json()["detail"]["code"] == "ERR_PRESET_FILAMENT_REQUIRED"

    brand = Brand(name="Resolved Brand", slug="resolved-brand", active=True)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Resolved PETG",
        slug="resolved-brand-resolved-petg",
        material_type="PETG",
        color_name="Signal red",
        color_hex="#FF0000",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)

    resolved = await auth_client.patch(
        f"/api/v1/presets/{draft_id}",
        json={
            "filament_id": filament.id,
            "active": True,
            "extruder_temp": 242,
            "bed_temp": 80,
        },
    )
    assert resolved.status_code == 200, resolved.text

    spool = await db_session.scalar(
        select(UserSpool).where(
            UserSpool.id == spool_id,
            UserSpool.user_id == auth_user.id,
        )
    )
    assert spool is not None
    await db_session.refresh(spool)
    assert spool.filament_id == filament.id
    assert spool.extra["import_draft_id"] == str(draft_id)
    assert spool.extra["import_resolved_filament_id"] == str(filament.id)
