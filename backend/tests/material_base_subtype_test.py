"""Base polymer and subtype of a filament's material type."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.brand import Brand
from app.models.filament import Filament
from app.services.catalog_duplicates import same_filament_kind
from app.services.material_types import resolve_material_type


async def _catalog(db: AsyncSession, *material_types: str) -> Brand:
    brand = Brand(name="Test Brand", slug="test-brand", verified=False, active=True)
    db.add(brand)
    await db.flush()
    for index, material_type in enumerate(material_types):
        db.add(
            Filament(
                brand_id=brand.id,
                name=f"Material {index}",
                slug=f"material-{index}",
                material_type=material_type,
                color_name="Black",
                color_hex="#000000",
                diameter=1.75,
            )
        )
    await db.commit()
    return brand


@pytest.mark.parametrize(
    ("material_type", "base", "subtype"),
    [
        ("PLA Plus", "PLA", "PLA+"),
        ("PLA SILK", "PLA", "PLA"),
        ("PA6-CF", "PA", "PA6"),
        ("Nylon", "PA", "PA"),
        ("PA6/66", "PA", None),
        ("PA612", "PA", None),
        ("PCTG", "PCTG", "PCTG"),
        ("CPE", "CPE", "CPE"),
        ("PLA Basic", "PLA", None),
        ("PA6+CF", "PA", "PA6"),
        ("PLA+Silk", "PLA", "PLA+"),
        ("PETG+", "PETG", "PETG+"),
        ("ABS Plus", "ABS", "ABS+"),
        ("ASA+ GF", "ASA", "ASA+"),
        ("ABS+PC", "ABS", "ABS/PC"),
        ("PLA/PETG", "PLA", None),
        ("Wood", None, None),
    ],
)
def test_material_type_resolves_without_guessing(material_type, base, subtype):
    resolution = resolve_material_type(material_type)

    assert (resolution.base, resolution.subtype) == (base, subtype)


@pytest.mark.parametrize(
    ("left", "right", "same"),
    [
        ("PLA Plus", "PLA+", True),
        ("PA6", "PA12", False),
        ("PA6", "PA6-CF", False),
        ("PETG", "PCTG", False),
        ("PA6+CF", "PA6-CF", True),
        ("PETG Carbon Fiber", "PETG-CF", True),
        ("ABS Plus", "ABS+", True),
        ("ABS+", "ABS", False),
    ],
)
def test_duplicate_check_merges_spellings_but_not_grades(left, right, same):
    assert same_filament_kind(left, 1.75, right, 1.75) is same


@pytest.mark.asyncio
async def test_family_filter_shows_every_pla_while_exact_type_filter_is_unchanged(
    client: AsyncClient, db_session: AsyncSession
):
    await _catalog(db_session, "PLA", "PLA+", "PLA Plus", "PLA SILK", "PETG")

    family = await client.get("/api/v1/filaments/", params={"material_base": "PLA"})
    exact = await client.get("/api/v1/filaments/", params={"material_type": "PLA"})

    assert family.status_code == 200
    assert sorted(item["material_type"] for item in family.json()["items"]) == [
        "PLA",
        "PLA Plus",
        "PLA SILK",
        "PLA+",
    ]
    assert family.json()["total"] == 4
    assert [item["material_type"] for item in exact.json()["items"]] == ["PLA"]


@pytest.mark.asyncio
async def test_nylon_grades_share_a_family_but_stay_separate_types(
    client: AsyncClient, db_session: AsyncSession
):
    await _catalog(db_session, "PA6", "PA12", "Nylon")

    family = await client.get("/api/v1/filaments/", params={"material_base": "PA"})
    groups = await client.get(
        "/api/v1/filaments/material-types/groups", params={"include_reference": "false"}
    )

    subtypes = {item["material_type"]: item["material_subtype"] for item in family.json()["items"]}
    assert subtypes == {"PA6": "PA6", "PA12": "PA12", "Nylon": "PA"}
    assert groups.json() == [{"base": "PA", "types": ["Nylon", "PA12", "PA6"], "filament_count": 3}]


@pytest.mark.asyncio
async def test_old_client_sending_only_material_type_keeps_it_verbatim(
    auth_client: AsyncClient, db_session: AsyncSession
):
    brand = await _catalog(db_session)

    response = await auth_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "Carbon",
            "material_type": "PA12-CF",
            "color_name": "Black",
            "color_hex": "#000000",
            "diameter": 1.75,
        },
    )

    assert response.status_code == 201, response.json()
    body = response.json()
    assert (body["material_type"], body["base_material_type"], body["material_subtype"]) == (
        "PA12-CF",
        "PA",
        "PA12",
    )
    types = await auth_client.get("/api/v1/filaments/material-types")
    assert types.json() == ["PA12-CF"]


@pytest.mark.asyncio
async def test_same_product_typed_with_another_spelling_is_rejected(
    auth_client: AsyncClient, db_session: AsyncSession
):
    brand = await _catalog(db_session, "PLA+")

    response = await auth_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "Material 0",
            "material_type": "PLA Plus",
            "color_name": "Black",
            "color_hex": "#000000",
            "diameter": 1.75,
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ERR_FILAMENT_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_catalog_import_preview_shows_family_and_subtype_of_each_filament_row(
    client: AsyncClient, admin_user
):
    draft = {
        "filename": "catalog.xlsx",
        "brands": [
            {"_row": 2, "enabled": True, "brand_key": "b", "mode": "auto", "name": "Test Brand"}
        ],
        "filaments": [
            {
                "_row": 2,
                "enabled": True,
                "filament_key": "b:pla-plus",
                "brand_key": "b",
                "mode": "auto",
                "name": "Rapid",
                "material_type": "PLA+",
                "color_name": "Black",
            }
        ],
    }

    preview = await client.post(
        "/api/v1/admin/catalog/master-import/preview-draft",
        headers={"Authorization": f"Bearer {create_access_token({'sub': admin_user.email})}"},
        json=draft,
    )

    assert preview.status_code == 200, preview.json()
    row = next(row for row in preview.json()["rows"] if row["sheet"] == "Filaments")
    assert (row["material_base"], row["material_subtype"]) == ("PLA", "PLA+")
