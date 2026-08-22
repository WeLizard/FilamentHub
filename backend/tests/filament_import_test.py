"""Brand CSV import must preview before it mutates the catalogue."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.filament_country_cell import FilamentCountryCell
from app.models.filament_line import FilamentLine

pytestmark = pytest.mark.asyncio


CSV = (
    "name,material_type,color_name,color_hex,line,availability\n"
    "Aurora PLA,PLA,Polar Blue,#3366FF,Aurora,available\n"
).encode()


async def _brand(db: AsyncSession) -> Brand:
    brand = Brand(name="Preview First", slug="preview-first", active=True)
    db.add(brand)
    await db.commit()
    await db.refresh(brand)
    return brand


def _upload(content: bytes = CSV) -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("materials.csv", content, "text/csv")}


async def test_preview_is_read_only_then_confirmation_applies(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    brand = await _brand(db_session)
    brand_id = brand.id

    preview = await admin_client.post(
        "/api/v1/filament-import/preview",
        params={"brand_id": brand_id},
        files=_upload(),
    )

    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["created"] == 1
    assert body["rows"][0] == {
        "row": 1,
        "status": "created",
        "name": "Aurora PLA",
        "material_type": "PLA",
        "color_name": "Polar Blue",
        "filament_id": None,
        "message": None,
    }
    assert body["source_rows"][0]["name"] == "Aurora PLA"
    assert body["source_rows"][0]["material_type"] == "PLA"
    assert set(body["source_rows"][0]) == {
        "name",
        "material_type",
        "color_name",
        "market_color_name",
        "color_hex",
        "ral_code",
        "price_per_kg",
        "currency",
        "spool_weight",
        "line",
        "availability",
        "product_url",
        "market_note",
    }
    assert await db_session.scalar(select(Filament.id)) is None
    assert await db_session.scalar(select(FilamentLine.id)) is None

    applied = await admin_client.post(
        "/api/v1/filament-import",
        params={"brand_id": brand_id},
        files=_upload(),
        data={"confirmation_token": body["confirmation_token"]},
    )

    assert applied.status_code == 200, applied.text
    assert applied.json()["created"] == 1
    filament = await db_session.scalar(select(Filament))
    assert filament is not None
    assert filament.name == "Aurora PLA"
    assert filament.material_type == "PLA"
    assert filament.color_name == "Polar Blue"
    assert await db_session.scalar(select(FilamentLine.id)) is not None


async def test_import_rejects_a_changed_file_without_writes(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    brand = await _brand(db_session)
    brand_id = brand.id
    preview = await admin_client.post(
        "/api/v1/filament-import/preview",
        params={"brand_id": brand_id},
        files=_upload(),
    )
    token = preview.json()["confirmation_token"]
    changed = CSV.replace(b"Aurora PLA", b"Aurora PETG").replace(b",PLA,", b",PETG,")

    applied = await admin_client.post(
        "/api/v1/filament-import",
        params={"brand_id": brand_id},
        files=_upload(changed),
        data={"confirmation_token": token},
    )

    assert applied.status_code == 409
    assert applied.json()["detail"] == {"code": "ERR_FILAMENT_IMPORT_CONFIRMATION_INVALID"}
    assert await db_session.scalar(select(Filament.id)) is None


async def test_corrected_draft_is_repreviewed_before_it_can_be_applied(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    brand = await _brand(db_session)
    brand_id = brand.id
    invalid = (
        "name,material_type,color_name,color_hex,line,availability\n"
        ",PLA,Polar Blue,#3366FF,Aurora,available\n"
    ).encode()
    first_preview = await admin_client.post(
        "/api/v1/filament-import/preview",
        params={"brand_id": brand_id},
        files=_upload(invalid),
    )
    assert first_preview.status_code == 200
    assert first_preview.json()["errors"] == 1

    corrected = invalid.replace(b",PLA,Polar Blue", b"Aurora PLA,PLA,Polar Blue")
    corrected_preview = await admin_client.post(
        "/api/v1/filament-import/preview",
        params={"brand_id": brand_id},
        files=_upload(corrected),
    )
    assert corrected_preview.status_code == 200
    corrected_body = corrected_preview.json()
    assert corrected_body["created"] == 1
    assert corrected_body["errors"] == 0

    applied = await admin_client.post(
        "/api/v1/filament-import",
        params={"brand_id": brand_id},
        files=_upload(corrected),
        data={"confirmation_token": corrected_body["confirmation_token"]},
    )
    assert applied.status_code == 200
    assert applied.json()["created"] == 1
    assert await db_session.scalar(select(Filament.name)) == "Aurora PLA"


async def test_country_preview_rolls_back_market_cell_then_confirmation_applies(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    brand = await _brand(db_session)
    filament = Filament(
        brand_id=brand.id,
        name="Aurora PLA",
        slug="aurora-pla-polar-blue",
        material_type="PLA",
        color_name="Polar Blue",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    brand_id = brand.id

    country_csv = (
        "name,material_type,color_name,availability,price_per_kg,currency\n"
        "Aurora PLA,PLA,Polar Blue,available,24.90,EUR\n"
    ).encode()
    preview = await admin_client.post(
        "/api/v1/filament-import/preview",
        params={"brand_id": brand_id, "country": "de"},
        files=_upload(country_csv),
    )

    assert preview.status_code == 200, preview.text
    assert preview.json()["updated"] == 1
    assert await db_session.scalar(select(FilamentCountryCell.id)) is None

    applied = await admin_client.post(
        "/api/v1/filament-import",
        params={"brand_id": brand_id, "country": "de"},
        files=_upload(country_csv),
        data={"confirmation_token": preview.json()["confirmation_token"]},
    )

    assert applied.status_code == 200, applied.text
    cell = await db_session.scalar(select(FilamentCountryCell))
    assert cell is not None
    assert cell.country == "DE"
    assert float(cell.price) == 24.9
    assert cell.currency == "EUR"


async def test_import_rejects_a_plan_that_changed_after_preview(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    brand = await _brand(db_session)
    brand_id = brand.id
    preview = await admin_client.post(
        "/api/v1/filament-import/preview",
        params={"brand_id": brand_id},
        files=_upload(),
    )
    token = preview.json()["confirmation_token"]

    db_session.add(
        Filament(
            brand_id=brand_id,
            name="Aurora PLA",
            slug="aurora-pla-polar-blue",
            material_type="PLA",
            color_name="Polar Blue",
            active=True,
        )
    )
    await db_session.commit()

    applied = await admin_client.post(
        "/api/v1/filament-import",
        params={"brand_id": brand_id},
        files=_upload(),
        data={"confirmation_token": token},
    )

    assert applied.status_code == 409
    assert applied.json()["detail"] == {"code": "ERR_FILAMENT_IMPORT_CONFIRMATION_INVALID"}
    filaments = list(await db_session.scalars(select(Filament)))
    assert len(filaments) == 1


async def test_import_requires_explicit_confirmation(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    brand = await _brand(db_session)

    applied = await admin_client.post(
        "/api/v1/filament-import",
        params={"brand_id": brand.id},
        files=_upload(),
    )

    assert applied.status_code == 422
    assert await db_session.scalar(select(Filament.id)) is None


async def test_preview_rejects_oversized_or_unrelated_csv(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    brand = await _brand(db_session)

    invalid = await admin_client.post(
        "/api/v1/filament-import/preview",
        params={"brand_id": brand.id},
        files=_upload(b"foo,bar\n1,2\n"),
    )
    oversized = await admin_client.post(
        "/api/v1/filament-import/preview",
        params={"brand_id": brand.id},
        files=_upload(b"name,material_type\n" + b"x" * (2 * 1024 * 1024)),
    )

    assert invalid.status_code == 400
    assert invalid.json()["detail"] == {"code": "ERR_FILAMENT_IMPORT_INVALID_CSV"}
    assert oversized.status_code == 413
    assert oversized.json()["detail"] == {"code": "ERR_FILAMENT_IMPORT_FILE_TOO_LARGE"}
