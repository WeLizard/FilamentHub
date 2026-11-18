"""The catalog served as the Spoolman external filament database."""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints import spool_compat_external
from app.models.brand import Brand
from app.models.filament import Filament
from app.models.spool_compat_resource import SpoolCompatResource
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool

BASE = "/api/v1/spool_compat"
KEY = "external_db_device_key"


@pytest.fixture(autouse=True)
def _no_cached_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spool_compat_external, "_cache", {})


async def _catalog(db: AsyncSession) -> tuple[User, Filament, Filament]:
    user = User(email="external-db@example.com", username="external_db_user", password_hash="x", active=True)
    device = UserPrinterDevice(
        user=user, name="Voron", device_fingerprint="external-db-fp", api_key=KEY, supports_hh=True,
    )
    brand = Brand(name="Sunlu", slug="sunlu-external", verified=True, active=True)
    green = Filament(
        brand=brand, name="PETG Green", slug="sunlu-petg-green", material_type="PETG",
        color_name="Green", color_hex="#1A9B3A", diameter=1.75, density=1.27, spool_weight=1000.0,
        empty_spool_weight_g=135.0, recommended_nozzle_temp_min=230, recommended_nozzle_temp_max=250,
        recommended_bed_temp_min=70, recommended_bed_temp_max=80, active=True,
    )
    retired = Filament(
        brand=brand, name="PETG Retired", slug="sunlu-petg-retired", material_type="PETG",
        color_hex="#000000", diameter=1.75, active=False,
    )
    db.add_all([user, device, brand, green, retired])
    await db.commit()
    return user, green, retired


@pytest.mark.asyncio
async def test_catalog_is_served_in_the_shape_clients_match_tags_against(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    _user, green, _retired = await _catalog(db_session)

    listed = await client.get(f"{BASE}/{KEY}/api/v1/external/filament")

    assert listed.status_code == 200
    assert listed.json() == [{
        "id": f"filamenthub-{green.id}", "manufacturer": "Sunlu", "name": "PETG Green",
        "material": "PETG", "diameter": 1.75, "density": 1.27, "weight": 1000.0,
        "spool_weight": 135.0, "color_hex": "1a9b3a",
        # One recommended value out of the manufacturer's range, and its top.
        "extruder_temp": 240, "extruder_temp_max": 250, "bed_temp": 75,
    }]
    assert (await client.get(f"{BASE}/not-a-key/v1/external/filament")).status_code == 401
    materials = (await client.get(f"{BASE}/{KEY}/v1/external/material")).json()
    assert {"material": "PLA", "density": 1.24, "extruder_temp": 215, "bed_temp": 60} in materials


@pytest.mark.asyncio
async def test_a_matched_catalog_filament_is_handed_out_instead_of_being_copied(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    user, green, retired = await _catalog(db_session)
    external_id = f"filamenthub-{green.id}"

    # What Happy Hare does after matching a tag against the external database.
    found = (await client.get(f"{BASE}/{KEY}/v1/filament", params={"external_id": external_id})).json()
    posted = await client.post(f"{BASE}/{KEY}/v1/filament", json={
        "name": "Green", "material": "PETG", "density": 1.23, "diameter": 1.75, "weight": 1000.0,
        "color_hex": "1A9B3A", "external_id": external_id,
    })
    spool = await client.post(f"{BASE}/{KEY}/v1/spool", json={"filament_id": found[0]["id"]})

    assert [item["external_id"] for item in found] == [external_id]
    assert found[0]["vendor"]["name"] == "Sunlu"
    assert posted.status_code == 200 and posted.json()["id"] == found[0]["id"]
    # The catalog's data wins over what the client sent along.
    assert posted.json()["density"] == 1.27
    assert spool.status_code in {200, 201}, spool.text
    stored = await db_session.scalar(select(UserSpool).where(UserSpool.user_id == user.id))
    assert stored is not None and stored.filament_id == green.id
    imports = await db_session.scalar(
        select(func.count()).select_from(SpoolCompatResource).where(
            SpoolCompatResource.source_kind == "import"
        )
    )
    assert imports == 0

    # An id that names nothing in the active catalog is an ordinary private import.
    for unknown in (f"filamenthub-{retired.id}", "filamenthub-999999", "sunlu_petg_green_1000_175_p"):
        created = await client.post(f"{BASE}/{KEY}/v1/filament", json={
            "name": "Other", "material": "PETG", "density": 1.23, "diameter": 1.75, "external_id": unknown,
        })
        assert created.status_code == 201, created.text
        assert created.json()["external_id"] == unknown
