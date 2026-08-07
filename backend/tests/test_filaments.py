"""Tests for filaments endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.filament_review import FilamentReview
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User
from app.services.organization_access import grant_brand_owner_membership


@pytest.mark.asyncio
async def test_list_filaments_empty(client: AsyncClient):
    """Test listing filaments when database is empty."""
    response = await client.get("/api/v1/filaments/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []
    assert data["page"] == 1
    assert data["size"] == 50


@pytest.mark.asyncio
async def test_create_filament(auth_client: AsyncClient, db_session: AsyncSession):
    """Test creating a filament."""
    # Create brand first
    brand = Brand(
        name="Test Brand",
        slug="test-brand",
        verified=False,
        active=True,
    )
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    # Create filament
    filament_data = {
        "brand_id": brand.id,
        "name": "Test Filament",
        "material_type": "PLA",
        "color_name": "Red",
        "color_hex": "#FF0000",
        "ral_code": "RAL 3020",
        "diameter": 1.75,
        "density": 1.24,
        "price_per_kg": 800.0,
        "spool_weight": 1000.0,
        "description": "Test filament description",
    }
    response = await auth_client.post("/api/v1/filaments/", json=filament_data)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == filament_data["name"]
    assert data["material_type"] == filament_data["material_type"]
    assert data["ral_code"] == "3020"
    assert data["id"] is not None
    assert data["availability"] == "available"

    search_response = await auth_client.get("/api/v1/filaments/?search=RAL%203020")
    assert search_response.status_code == 200
    assert [item["id"] for item in search_response.json()["items"]] == [data["id"]]


@pytest.mark.asyncio
async def test_community_user_can_add_filament_to_verified_brand(
    auth_client: AsyncClient,
    db_session: AsyncSession,
):
    """Brand verification grants management rights but does not close catalog contributions."""
    brand = Brand(
        name="Verified Open Catalog Brand",
        slug="verified-open-catalog-brand",
        verified=True,
        active=True,
    )
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    response = await auth_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "Community Added PETG",
            "material_type": "PETG",
            "color_name": "Purple",
            "color_hex": "#7C3AED",
        },
    )

    assert response.status_code == 201
    assert response.json()["brand_id"] == brand.id
    assert response.json()["name"] == "Community Added PETG"


@pytest.mark.asyncio
async def test_create_filament_custom_filler_rejected_for_unverified(
    auth_client: AsyncClient, db_session: AsyncSession
):
    """A custom filler is rejected when the brand is not verified."""
    brand = Brand(name="Unverified Filler", slug="unverified-filler", verified=False, active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    response = await auth_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "Custom Filler Filament",
            "material_type": "PLA",
            "visual_settings": {"filler": "ceramic"},
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ERR_CUSTOM_FILLER_VERIFIED_ONLY"


@pytest.mark.asyncio
async def test_create_filament_custom_filler_allowed_for_verified(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """A verified brand (or admin) can set a custom filler."""
    brand = Brand(name="Verified Filler", slug="verified-filler", verified=True, active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    response = await admin_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "Custom Filler Filament",
            "material_type": "PLA",
            "visual_settings": {"filler": "ceramic"},
        },
    )
    assert response.status_code == 201
    assert response.json()["visual_settings"]["filler"] == "ceramic"
    assert response.json()["visual_settings"]["effects"] == ["ceramic"]


@pytest.mark.asyncio
async def test_create_filament_with_combined_material_features(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """Composition, claims, and independent visual effects round-trip together."""
    brand = Brand(name="Feature Brand", slug="feature-brand", verified=True, active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    response = await admin_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "PA612-CF ESD Sparkle",
            "material_type": "PA612",
            "visual_settings": {"effects": ["carbon", "glitter"]},
            "additives": [
                {"code": "carbon_fiber", "content_percent": 10, "content_basis": "weight"},
                {"code": "carbon_nanotubes"},
            ],
            "property_claims": [
                {"code": "esd", "standard": "IEC 61340", "rating": "10^6-10^9 ohm"},
            ],
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["visual_settings"]["filler"] == "carbon"
    assert data["visual_settings"]["effects"] == ["carbon", "glitter"]
    assert [item["code"] for item in data["additives"]] == ["carbon_fiber", "carbon_nanotubes"]
    assert data["property_claims"][0]["standard"] == "IEC 61340"

    update = await admin_client.patch(
        f"/api/v1/filaments/{data['id']}",
        json={
            "visual_settings": {
                "filler": "carbon",
                "effects": ["carbon", "glitter"],
            },
            "additives": [{"code": "glass_fiber", "content_percent": 15}],
            "property_claims": [{"code": "flame_retardant", "rating": "UL94 V-0"}],
        },
    )
    assert update.status_code == 200
    updated = update.json()
    assert updated["visual_settings"]["effects"] == ["carbon", "glitter"]
    assert updated["additives"] == [
        {"code": "glass_fiber", "content_percent": 15.0, "content_basis": None}
    ]
    assert updated["property_claims"][0]["rating"] == "UL94 V-0"


@pytest.mark.asyncio
async def test_custom_material_feature_rejected_for_unverified_brand(
    auth_client: AsyncClient, db_session: AsyncSession
):
    brand = Brand(name="Closed Features", slug="closed-features", verified=False, active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    response = await auth_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "Unknown Blend",
            "material_type": "PLA",
            "additives": [{"code": "moon_dust"}],
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ERR_CUSTOM_MATERIAL_FEATURE_VERIFIED_ONLY"


@pytest.mark.asyncio
async def test_filament_line_create_and_assign(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """A line can be created, a filament assigned to it, and grouping data returned."""
    brand = Brand(name="Line Brand", slug="line-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    line_resp = await admin_client.post(
        f"/api/v1/filament-lines?brand_id={brand.id}", json={"name": "Pro Series"}
    )
    assert line_resp.status_code == 201
    line_id = line_resp.json()["id"]

    fil_resp = await admin_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "Pro Red",
            "material_type": "PLA",
            "line_id": line_id,
        },
    )
    assert fil_resp.status_code == 201
    assert fil_resp.json()["line_id"] == line_id

    lines = await admin_client.get(f"/api/v1/filament-lines?brand_id={brand.id}")
    assert lines.status_code == 200
    assert lines.json()[0]["filaments_count"] == 1

    fil_list = await admin_client.get(f"/api/v1/filaments/?brand_id={brand.id}")
    assert any(item["line_name"] == "Pro Series" for item in fil_list.json()["items"])


@pytest.mark.asyncio
async def test_filament_import_csv(admin_client: AsyncClient, db_session: AsyncSession):
    """CSV import creates filaments, auto-creates a shared line, reports errors and dedups."""
    brand = Brand(name="Import Brand", slug="import-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    csv_content = (
        "name,material_type,color_name,color_hex,price_per_kg,spool_weight,line,availability\n"
        "Imp Red,PLA,Red,#FF0000,1500,1000,Imp Line,available\n"
        "Imp Blue,PETG,Blue,#0000FF,1800,1000,Imp Line,available\n"
        ",PLA,Bad,,,,,\n"
    )
    files = {"file": ("import.csv", csv_content.encode("utf-8"), "text/csv")}
    resp = await admin_client.post(f"/api/v1/filament-import?brand_id={brand.id}", files=files)
    assert resp.status_code == 200
    data = resp.json()
    assert data["created"] == 2
    assert data["errors"] == 1

    lines = await admin_client.get(f"/api/v1/filament-lines?brand_id={brand.id}")
    assert len(lines.json()) == 1
    assert lines.json()[0]["filaments_count"] == 2

    again = await admin_client.post(f"/api/v1/filament-import?brand_id={brand.id}", files=files)
    assert again.json()["skipped"] == 2
    assert again.json()["created"] == 0


@pytest.mark.asyncio
async def test_filament_line_palette(admin_client: AsyncClient, db_session: AsyncSession):
    """Palette endpoint creates one filament per color, auto-naming '<Line> <Color>' and deduping."""
    brand = Brand(name="Palette Brand", slug="palette-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    line_resp = await admin_client.post(
        f"/api/v1/filament-lines?brand_id={brand.id}", json={"name": "PLA Basic"}
    )
    line_id = line_resp.json()["id"]

    payload = {
        "material_type": "PLA",
        "visual_settings": {"effects": ["metallic", "glitter"]},
        "additives": [{"code": "glass_fiber", "content_percent": 10}],
        "property_claims": [{"code": "flame_retardant", "rating": "UL94 V-0"}],
        "diameter": 1.75,
        "price_per_kg": 1500,
        "variants": [
            {"color_name": "Red", "color_hex": "#FF0000"},
            {"color_name": "Blue", "color_hex": "#0000FF"},
            {"color_name": "Green", "color_hex": "#00FF00", "name": "Custom Green"},
        ],
    }
    resp = await admin_client.post(f"/api/v1/filament-lines/{line_id}/variants", json=payload)
    assert resp.status_code == 200
    assert resp.json()["created"] == 3

    fil_list = await admin_client.get(f"/api/v1/filaments/?brand_id={brand.id}")
    names = {item["name"] for item in fil_list.json()["items"]}
    assert "PLA Basic Red" in names
    assert "PLA Basic Blue" in names
    assert "Custom Green" in names
    for item in fil_list.json()["items"]:
        assert item["visual_settings"]["effects"] == ["metallic", "glitter"]
        assert item["additives"][0]["code"] == "glass_fiber"
        assert item["property_claims"][0]["rating"] == "UL94 V-0"

    lines = await admin_client.get(f"/api/v1/filament-lines?brand_id={brand.id}")
    assert lines.json()[0]["filaments_count"] == 3

    again = await admin_client.post(
        f"/api/v1/filament-lines/{line_id}/variants",
        json={"material_type": "PLA", "variants": [{"color_name": "Red", "color_hex": "#FF0000"}]},
    )
    assert again.json()["skipped"] == 1
    assert again.json()["created"] == 0


@pytest.mark.asyncio
async def test_create_filament_with_availability(
    admin_client: AsyncClient, db_session: AsyncSession
):
    """A brand-set availability status is stored and returned."""
    brand = Brand(name="Avail Brand", slug="avail-brand")
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    response = await admin_client.post(
        "/api/v1/filaments/",
        json={
            "brand_id": brand.id,
            "name": "Discontinued PLA",
            "material_type": "PLA",
            "availability": "discontinued",
        },
    )
    assert response.status_code == 201
    filament_id = response.json()["id"]
    assert response.json()["availability"] == "discontinued"

    patch = await admin_client.patch(
        f"/api/v1/filaments/{filament_id}", json={"availability": "out_of_stock"}
    )
    assert patch.status_code == 200
    assert patch.json()["availability"] == "out_of_stock"


@pytest.mark.asyncio
async def test_get_filament(client: AsyncClient, db_session: AsyncSession):
    """Test getting a filament by ID."""
    # Create brand and filament
    brand = Brand(
        name="Test Brand 2",
        slug="test-brand-2",
        verified=False,
        active=True,
    )
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    filament = Filament(
        brand_id=brand.id,
        name="Test Filament 2",
        slug="test-filament-2",
        material_type="PETG",
        color_name="Blue",
        color_hex="#0000FF",
        diameter=1.75,
        density=1.27,
        price_per_kg=950.0,
        spool_weight=1000.0,
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)
    
    # Get filament via API
    response = await client.get(f"/api/v1/filaments/{filament.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == filament.id
    assert data["name"] == filament.name
    assert data["material_type"] == filament.material_type


@pytest.mark.asyncio
async def test_get_filament_not_found(client: AsyncClient):
    """Test getting non-existent filament."""
    response = await client.get("/api/v1/filaments/99999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_filaments_filter_by_brand(
    client: AsyncClient, db_session: AsyncSession
):
    """Test filtering filaments by brand."""
    # Create brands
    brand1 = Brand(name="Brand 1", slug="brand-1", active=True)
    brand2 = Brand(name="Brand 2", slug="brand-2", active=True)
    db_session.add_all([brand1, brand2])
    await db_session.commit()
    await db_session.refresh(brand1)
    await db_session.refresh(brand2)
    
    # Create filaments
    filament1 = Filament(
        brand_id=brand1.id,
        name="Filament 1",
        slug="filament-1",
        material_type="PLA",
        active=True,
    )
    filament2 = Filament(
        brand_id=brand2.id,
        name="Filament 2",
        slug="filament-2",
        material_type="PETG",
        active=True,
    )
    db_session.add_all([filament1, filament2])
    await db_session.commit()
    
    # Filter by brand1
    response = await client.get(f"/api/v1/filaments/?brand_id={brand1.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == filament1.id


@pytest.mark.asyncio
async def test_list_filaments_filter_by_material_type(
    client: AsyncClient, db_session: AsyncSession
):
    """Test filtering filaments by material type."""
    # Create brand
    brand = Brand(name="Test Brand", slug="test-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    # Create filaments with different types
    filament1 = Filament(
        brand_id=brand.id,
        name="PLA Filament",
        slug="pla-filament",
        material_type="PLA",
        active=True,
    )
    filament2 = Filament(
        brand_id=brand.id,
        name="PETG Filament",
        slug="petg-filament",
        material_type="PETG",
        active=True,
    )
    db_session.add_all([filament1, filament2])
    await db_session.commit()
    
    # Filter by PLA
    response = await client.get("/api/v1/filaments/?material_type=PLA")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["material_type"] == "PLA"


@pytest.mark.asyncio
async def test_list_filaments_searches_catalog_fields(
    client: AsyncClient, db_session: AsyncSession
):
    """Search covers material, brand, type, the original color name and filler."""
    searchable_brand = Brand(
        name="Polymaker Search Brand",
        slug="polymaker-search-brand",
        active=True,
    )
    other_brand = Brand(name="Other Search Brand", slug="other-search-brand", active=True)
    db_session.add_all([searchable_brand, other_brand])
    await db_session.commit()
    await db_session.refresh(searchable_brand)
    await db_session.refresh(other_brand)

    db_session.add_all(
        [
            Filament(
                brand_id=searchable_brand.id,
                name="Engineering Material",
                slug="engineering-material",
                material_type="PETG-CF",
                color_name="Galaxy Black",
                visual_settings={"filler": "carbon", "effects": ["carbon"]},
                additives=[{"code": "carbon_fiber"}, {"code": "carbon_nanotubes"}],
                property_claims=[{"code": "esd", "standard": "IEC 61340"}],
                active=True,
            ),
            Filament(
                brand_id=other_brand.id,
                name="Decorative Material",
                slug="decorative-material",
                material_type="PLA",
                color_name="Sakura Pink",
                active=True,
            ),
        ]
    )
    await db_session.commit()

    for term, expected_name in [
        ("Polymaker", "Engineering Material"),
        ("engineering", "Engineering Material"),
        ("petg-cf", "Engineering Material"),
        ("Sakura", "Decorative Material"),
        ("carbon", "Engineering Material"),
        ("nanotubes", "Engineering Material"),
        ("IEC 61340", "Engineering Material"),
    ]:
        response = await client.get("/api/v1/filaments/", params={"search": term})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == expected_name


@pytest.mark.asyncio
async def test_list_filaments_can_reach_items_after_first_hundred(
    client: AsyncClient, db_session: AsyncSession
):
    """Catalog pagination exposes records beyond the former frontend limit of 100."""
    brand = Brand(name="Large Catalog Brand", slug="large-catalog-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)

    db_session.add_all(
        [
            Filament(
                brand_id=brand.id,
                name=f"Material {index:03d}",
                slug=f"material-{index:03d}",
                material_type="PLA",
                active=True,
            )
            for index in range(105)
        ]
    )
    await db_session.commit()

    response = await client.get("/api/v1/filaments/", params={"page": 2, "size": 100})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 105
    assert data["pages"] == 2
    assert [item["name"] for item in data["items"]] == [
        "Material 100",
        "Material 101",
        "Material 102",
        "Material 103",
        "Material 104",
    ]


@pytest.mark.asyncio
async def test_get_filament_presets(client: AsyncClient, db_session: AsyncSession):
    """Test getting presets for a filament."""
    # Create brand and filament
    brand = Brand(name="Test Brand", slug="test-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    filament = Filament(
        brand_id=brand.id,
        name="Test Filament",
        slug="test-filament",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)
    
    # Get presets
    response = await client.get(f"/api/v1/filaments/{filament.id}/presets")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_update_filament(admin_client: AsyncClient, db_session: AsyncSession):
    """Test updating a filament."""
    # Create brand and filament
    brand = Brand(name="Test Brand", slug="test-brand", active=True)
    db_session.add(brand)
    await db_session.commit()
    await db_session.refresh(brand)
    
    filament = Filament(
        brand_id=brand.id,
        name="Original Name",
        slug="original-name",
        material_type="PLA",
        active=True,
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)
    
    # Update filament (using PATCH for partial update)
    update_data = {
        "name": "Updated Name",
        "description": "Updated description",
    }
    response = await admin_client.patch(
        f"/api/v1/filaments/{filament.id}", json=update_data
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == update_data["name"]
    assert data["description"] == update_data["description"]



async def _brand_with_employee(
    db_session: AsyncSession, employee: User, admin_user: User
) -> Brand:
    """A verified brand whose catalog the employee may edit."""
    brand = Brand(name="Creality", slug="creality", active=True, verified=True)
    db_session.add(brand)
    await db_session.flush()
    await grant_brand_owner_membership(
        db_session, brand=brand, user=employee, granted_by_id=admin_user.id
    )
    await db_session.commit()
    return brand


@pytest.mark.asyncio
async def test_brand_employee_may_delete_a_filament_nobody_contributed_to(
    auth_client: AsyncClient,
    auth_user: User,
    admin_user: User,
    db_session: AsyncSession,
):
    """An untouched entry carries nothing, so removing it costs nobody anything."""
    brand = await _brand_with_employee(db_session, auth_user, admin_user)
    filament = Filament(
        brand_id=brand.id, name="Generic PLA", slug="generic-pla", material_type="PLA"
    )
    db_session.add(filament)
    await db_session.commit()
    await db_session.refresh(filament)

    response = await auth_client.delete(f"/api/v1/filaments/{filament.id}")
    assert response.status_code == 204
    assert await db_session.get(Filament, filament.id) is None


@pytest.mark.asyncio
async def test_brand_employee_may_not_delete_a_filament_with_presets(
    auth_client: AsyncClient,
    auth_user: User,
    admin_user: User,
    db_session: AsyncSession,
):
    """Deleting the entry would take the community's presets with it."""
    brand = await _brand_with_employee(db_session, auth_user, admin_user)
    filament = Filament(
        brand_id=brand.id, name="Generic PLA", slug="generic-pla", material_type="PLA"
    )
    db_session.add(filament)
    await db_session.flush()
    db_session.add(
        Preset(
            filament_id=filament.id,
            name="Generic PLA on Ender 3",
            extruder_temp=205,
            bed_temp=60,
        )
    )
    await db_session.commit()
    await db_session.refresh(filament)

    response = await auth_client.delete(f"/api/v1/filaments/{filament.id}")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ERR_FILAMENT_HAS_CONTRIBUTIONS"
    assert await db_session.get(Filament, filament.id) is not None


@pytest.mark.asyncio
async def test_brand_employee_may_not_delete_a_filament_with_reviews(
    auth_client: AsyncClient,
    auth_user: User,
    admin_user: User,
    db_session: AsyncSession,
):
    """A review is somebody's work too, even when no preset was ever made."""
    brand = await _brand_with_employee(db_session, auth_user, admin_user)
    filament = Filament(
        brand_id=brand.id, name="Generic PLA", slug="generic-pla", material_type="PLA"
    )
    db_session.add(filament)
    await db_session.flush()
    db_session.add(
        FilamentReview(
            filament_id=filament.id,
            user_id=admin_user.id,
            success=True,
            rating=4,
            comment="Prints fine out of the box.",
        )
    )
    await db_session.commit()

    response = await auth_client.delete(f"/api/v1/filaments/{filament.id}")
    assert response.status_code == 409
    assert await db_session.get(Filament, filament.id) is not None


@pytest.mark.asyncio
async def test_brand_employee_may_take_a_contributed_filament_off_the_shelf(
    auth_client: AsyncClient,
    auth_user: User,
    admin_user: User,
    db_session: AsyncSession,
):
    """The way out of a bad entry: it leaves the catalog, the work stays."""
    brand = await _brand_with_employee(db_session, auth_user, admin_user)
    filament = Filament(
        brand_id=brand.id, name="Generic PLA", slug="generic-pla", material_type="PLA"
    )
    db_session.add(filament)
    await db_session.flush()
    db_session.add(
        Preset(
            filament_id=filament.id,
            name="Generic PLA on Ender 3",
            extruder_temp=205,
            bed_temp=60,
        )
    )
    await db_session.commit()

    response = await auth_client.patch(
        f"/api/v1/filaments/{filament.id}", json={"active": False}
    )
    assert response.status_code == 200
    assert response.json()["active"] is False

    listed = await auth_client.get("/api/v1/filaments/")
    assert all(item["id"] != filament.id for item in listed.json()["items"])


@pytest.mark.asyncio
async def test_administrator_may_still_delete_a_contributed_filament(
    admin_client: AsyncClient,
    admin_user: User,
    db_session: AsyncSession,
):
    """Someone has to be able to clear out genuine junk; that someone is us."""
    brand = Brand(name="Creality", slug="creality", active=True, verified=True)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id, name="Generic PLA", slug="generic-pla", material_type="PLA"
    )
    db_session.add(filament)
    await db_session.flush()
    db_session.add(
        Preset(
            filament_id=filament.id,
            name="Generic PLA on Ender 3",
            extruder_temp=205,
            bed_temp=60,
        )
    )
    await db_session.commit()

    response = await admin_client.delete(f"/api/v1/filaments/{filament.id}")
    assert response.status_code == 204
    assert await db_session.get(Filament, filament.id) is None


@pytest.mark.asyncio
async def test_a_review_its_author_deleted_no_longer_holds_the_filament(
    auth_client: AsyncClient,
    auth_user: User,
    admin_user: User,
    db_session: AsyncSession,
):
    """A review is removed by clearing a flag, and what is gone protects nothing."""
    brand = await _brand_with_employee(db_session, auth_user, admin_user)
    filament = Filament(
        brand_id=brand.id, name="Generic PLA", slug="generic-pla", material_type="PLA"
    )
    db_session.add(filament)
    await db_session.flush()
    db_session.add(
        FilamentReview(
            filament_id=filament.id,
            user_id=admin_user.id,
            success=True,
            rating=4,
            comment="Withdrawn later.",
            active=False,
        )
    )
    await db_session.commit()

    response = await auth_client.delete(f"/api/v1/filaments/{filament.id}")
    assert response.status_code == 204
    assert await db_session.get(Filament, filament.id) is None


@pytest.mark.asyncio
async def test_a_draft_awaiting_moderation_still_holds_the_filament(
    auth_client: AsyncClient,
    auth_user: User,
    admin_user: User,
    db_session: AsyncSession,
):
    """A preset hidden from the catalogue is not a preset nobody wrote."""
    brand = await _brand_with_employee(db_session, auth_user, admin_user)
    filament = Filament(
        brand_id=brand.id, name="Generic PLA", slug="generic-pla", material_type="PLA"
    )
    db_session.add(filament)
    await db_session.flush()
    db_session.add(
        Preset(
            filament_id=filament.id,
            user_id=admin_user.id,
            name="Imported from the slicer",
            extruder_temp=205,
            bed_temp=60,
            active=False,
            moderation_status=PresetModerationStatus.PENDING,
        )
    )
    await db_session.commit()

    response = await auth_client.delete(f"/api/v1/filaments/{filament.id}")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ERR_FILAMENT_HAS_CONTRIBUTIONS"
    assert await db_session.get(Filament, filament.id) is not None
