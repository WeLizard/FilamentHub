"""Legacy Spoolman list filters used by Happy Hare remain effective."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.user import User
from app.models.user_printer_device import UserPrinterDevice
from app.models.user_spool import UserSpool


@pytest.mark.asyncio
async def test_spool_list_filter_aliases_and_dotted_precedence(
    client: AsyncClient, db_session: AsyncSession,
) -> None:
    user = User(email="spool-alias@example.com", username="spoolalias",
                password_hash="unused", active=True)
    device = UserPrinterDevice(user=user, name="Alias Printer", device_fingerprint="alias-device",
                               api_key="alias-test-key", supports_hh=True)
    first_brand = Brand(name="Alias Maker One", slug="alias-maker-one", active=True)
    second_brand = Brand(name="Alias Maker Two", slug="alias-maker-two", active=True)
    first_filament = Filament(brand=first_brand, name="Alias PLA", slug="alias-pla",
        material_type="PLA", color_name="Red", color_hex="#FF0000", diameter=1.75,
        density=1.24, spool_weight=1000, active=True)
    second_filament = Filament(brand=second_brand, name="Alias PETG", slug="alias-petg",
        material_type="PETG", color_name="Blue", color_hex="#0000FF", diameter=1.75,
        density=1.24, spool_weight=1000, active=True)
    first_spool = UserSpool(user=user, filament=first_filament, initial_weight_g=1000,
                            used_weight_g=0, source="manual")
    second_spool = UserSpool(user=user, filament=second_filament, initial_weight_g=1000,
                             used_weight_g=0, source="manual")
    db_session.add_all([user, device, first_brand, second_brand, first_filament,
                        second_filament, first_spool, second_spool])
    await db_session.commit()
    base = "/api/v1/spool_compat"
    path = f"{base}/{device.api_key}/v1/spool"

    async def ids(params: dict, *, header: bool = False) -> set[int]:
        response = await client.get(f"{base}/v1/spool" if header else path,
            params=params, headers={"X-API-Key": device.api_key} if header else None)
        assert response.status_code == 200
        return {item["id"] for item in response.json()}

    assert await ids({"vendor_name": "No Such Maker"}) == set()
    assert await ids({"filament_material": "No Such Material"}) == set()
    assert await ids({"vendor_name": '"Alias Maker One"'}) == {first_spool.id}
    assert await ids({"filament_material": '"PETG"'}, header=True) == {second_spool.id}
    assert await ids({"vendor_name": "Alias Maker One",
                      "filament.vendor.name": '"Alias Maker Two"'}) == {second_spool.id}
    assert await ids({"filament_material": "PLA",
                      "filament.material": '"PETG"'}) == {second_spool.id}
