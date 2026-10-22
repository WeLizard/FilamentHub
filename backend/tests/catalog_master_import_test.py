"""Administrative catalog master-import preview/apply tests."""

from io import BytesIO

import pytest
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models import (
    Brand,
    CatalogImportBatch,
    Filament,
    FilamentCountryCell,
    Preset,
    PresetPrinter,
    Printer,
)
from app.models.preset import PresetModerationStatus
from app.schemas.catalog_import import CatalogImportDraft
from app.services.catalog_master_import_service import (
    CatalogMasterImportError,
    apply_plan,
    build_plan,
    build_template,
    parse_workbook,
    summarize,
)

pytestmark = pytest.mark.asyncio


def _headers(user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}


def _draft() -> CatalogImportDraft:
    return CatalogImportDraft(
        filename="catalog.xlsx",
        brands=[
            {
                "_row": 2,
                "enabled": True,
                "brand_key": "example",
                "mode": "auto",
                "name": "Example Materials",
                "website": "https://example.test",
            }
        ],
        filaments=[
            {
                "_row": 2,
                "enabled": True,
                "filament_key": "example:pla:black",
                "brand_key": "example",
                "mode": "auto",
                "name": "Everyday PLA Black",
                "line": "Everyday PLA",
                "material_type": "PLA",
                "color_name": "Black",
                "color_hex": "#111111",
                "diameter": 1.75,
                "density": 1.24,
            }
        ],
        filament_markets=[
            {
                "_row": 2,
                "enabled": True,
                "filament_key": "example:pla:black",
                "country": "TR",
                "availability": "available",
                "price": 750,
                "currency": "TRY",
                "price_display_unit": "per_spool",
                "published": True,
            }
        ],
        presets=[
            {
                "_row": 2,
                "enabled": True,
                "preset_key": "example:pla:black:generic",
                "filament_key": "example:pla:black",
                "mode": "auto",
                "name": "Example PLA",
                "extruder_temp": 215,
                "bed_temp": 60,
                "flow_rate": 100,
                "fan_speed": 100,
            }
        ],
    )


async def test_master_import_preview_is_read_only_and_apply_is_idempotent(
    db_session: AsyncSession,
    admin_user,
) -> None:
    draft = _draft()
    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert summarize(plan) == {
        "create": 4,
        "update": 0,
        "noop": 0,
        "skipped": 0,
        "error": 0,
    }
    assert await db_session.scalar(select(func.count()).select_from(Brand)) == 0

    batch = await apply_plan(
        db_session,
        draft,
        plan,
        admin_user_id=admin_user.id,
    )
    await db_session.commit()
    assert batch.id is not None
    assert await db_session.scalar(select(func.count()).select_from(Brand)) == 1
    assert await db_session.scalar(select(func.count()).select_from(Filament)) == 1
    assert await db_session.scalar(select(func.count()).select_from(FilamentCountryCell)) == 1
    assert await db_session.scalar(select(func.count()).select_from(Preset)) == 1
    assert await db_session.scalar(select(func.count()).select_from(CatalogImportBatch)) == 1

    repeated = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert summarize(repeated) == {
        "create": 0,
        "update": 0,
        "noop": 4,
        "skipped": 0,
        "error": 0,
    }
    noop_batch = await apply_plan(db_session, draft, repeated, admin_user_id=admin_user.id)
    await db_session.commit()
    for saved_batch in (batch, noop_batch):
        targets = {
            (row["sheet"], row["key"]): row.get("target_id")
            for row in saved_batch.plan_snapshot["rows"]
            if row["sheet"] in {"Brands", "Filaments", "Presets"}
        }
        assert targets == {
            ("Brands", "example"): await db_session.scalar(select(Brand.id)),
            ("Filaments", "example:pla:black"): await db_session.scalar(select(Filament.id)),
            ("Presets", "example:pla:black:generic"): await db_session.scalar(select(Preset.id)),
        }


async def test_existing_values_require_explicit_overwrite(
    db_session: AsyncSession,
    admin_user,
) -> None:
    brand = Brand(
        name="Example Materials",
        slug="example-materials",
        website="https://old.example",
        currency="RUB",
        active=True,
        verified=False,
    )
    db_session.add(brand)
    await db_session.commit()

    draft = _draft()
    draft.filaments = []
    draft.filament_markets = []
    draft.presets = []
    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert summarize(plan)["error"] == 1
    assert "website" in (plan[0].get("message") or "")

    draft.brands[0]["overwrite"] = True
    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert summarize(plan)["update"] == 1


async def test_import_keeps_diameter_and_line_variants_distinct_and_reimports_safely(
    db_session: AsyncSession, admin_user
) -> None:
    draft = CatalogImportDraft(
        filename="variants.xlsx",
        brands=[{"brand_key": "variants", "name": "Variant Maker"}],
        filaments=[
            {
                "filament_key": f"{line}:{diameter}",
                "brand_key": "variants",
                "name": "PLA Black",
                "material_type": "PLA",
                "color_name": "Black",
                "line": line,
                "diameter": diameter,
            }
            for line in ("Everyday", "Premium")
            for diameter in (1.75, 2.85)
        ],
    )
    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert summarize(plan)["error"] == 0, plan
    assert summarize(plan)["create"] == 5
    await apply_plan(db_session, draft, plan, admin_user_id=admin_user.id)
    await db_session.commit()
    variants = (await db_session.scalars(select(Filament))).all()
    assert len(variants) == 4
    assert len({variant.slug for variant in variants}) == 4
    repeated = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert summarize(repeated) == {"create": 0, "update": 0, "noop": 5, "skipped": 0, "error": 0}

    # A legacy row without a line must never select an arbitrary matching line.
    incomplete = draft.model_copy(deep=True)
    incomplete.filaments = [dict(draft.filaments[0])]
    incomplete.filaments[0].pop("line")
    ambiguous = await build_plan(db_session, incomplete, admin_user_id=admin_user.id)
    assert summarize(ambiguous)["error"] == 1
    assert "ambiguous" in ambiguous[-1]["message"].lower()

    # An explicit target preserves omitted identity dimensions and remains usable.
    selected_id = repeated[1]["target_id"]
    incomplete.filaments[0]["existing_filament"] = selected_id
    incomplete.filaments[0].pop("diameter")
    explicit = await build_plan(db_session, incomplete, admin_user_id=admin_user.id)
    assert summarize(explicit)["error"] == 0, explicit
    assert explicit[-1]["target_id"] == selected_id


async def test_legacy_import_without_variant_dimensions_matches_only_unique_candidate(
    db_session: AsyncSession, admin_user
) -> None:
    draft = _draft()
    draft.brand_markets = []
    draft.filament_markets = []
    draft.presets = []
    draft.filaments[0]["diameter"] = 2.85
    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    await apply_plan(db_session, draft, plan, admin_user_id=admin_user.id)
    await db_session.commit()
    draft.filaments[0].pop("line")
    draft.filaments[0].pop("diameter")
    legacy = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert summarize(legacy)["error"] == 0, legacy
    assert legacy[-1]["status"] == "noop"

    draft.filaments[0]["existing_filament"] = "999999"
    missing = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert summarize(missing)["error"] == 1
    assert "Existing filament was not found" in missing[-1]["message"]


async def test_explicit_create_without_line_does_not_match_a_lined_variant(
    db_session: AsyncSession, admin_user
) -> None:
    draft = _draft()
    draft.brand_markets = []
    draft.filament_markets = []
    draft.presets = []
    draft.filaments = [
        {**draft.filaments[0], "filament_key": f"black:{diameter}", "diameter": diameter}
        for diameter in (1.75, 2.85)
    ]
    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    await apply_plan(db_session, draft, plan, admin_user_id=admin_user.id)
    await db_session.commit()
    draft.filaments = [dict(draft.filaments[1])]
    draft.filaments[0].pop("line")
    draft.filaments[0]["mode"] = "create"
    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert summarize(plan)["error"] == 0, plan
    assert plan[-1]["status"] == "create"
    await apply_plan(db_session, draft, plan, admin_user_id=admin_user.id)
    await db_session.commit()
    variants = (await db_session.scalars(select(Filament))).all()
    assert len(variants) == 3
    assert len({variant.slug for variant in variants}) == 3
    assert {variant.line_id is None for variant in variants} == {True, False}
    unlined = next(variant for variant in variants if variant.line_id is None)
    assert unlined.diameter == 2.85
    assert unlined.slug.endswith("-unlined")
    duplicate = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert summarize(duplicate)["error"] == 1
    assert "already exists" in duplicate[-1]["message"]


async def test_template_round_trips_into_editable_draft() -> None:
    workbook = load_workbook(BytesIO(build_template()))
    brands = workbook["Brands"]
    filaments = workbook["Filaments"]
    brand_headers = [cell.value for cell in brands[1]]
    filament_headers = [cell.value for cell in filaments[1]]
    brand_row = {"enabled": True, "brand_key": "sample", "name": "Sample"}
    filament_row = {
        "enabled": True,
        "filament_key": "sample:pla:red",
        "brand_key": "sample",
        "name": "PLA Red",
        "material_type": "PLA",
    }
    brands.append([brand_row.get(header, "") for header in brand_headers])
    filaments.append([filament_row.get(header, "") for header in filament_headers])
    output = BytesIO()
    workbook.save(output)

    parsed = parse_workbook(output.getvalue(), "sample.xlsx")
    assert parsed.brands[0]["brand_key"] == "sample"
    assert parsed.filaments[0]["filament_key"] == "sample:pla:red"
    assert {
        "storage_temperature_min_c",
        "storage_temperature_max_c",
        "storage_relative_humidity_max_percent",
        "storage_relative_humidity_target_percent",
        "storage_airtight_required",
        "storage_desiccant_recommended",
        "storage_light_protection_required",
        "storage_after_opening_guidance",
        "unopened_shelf_life_months",
        "filler",
    } <= set(filament_headers)


async def test_master_import_creates_manufacturer_storage_facts(db_session, admin_user) -> None:
    draft = _draft()
    draft.filament_markets = []
    draft.presets = []
    draft.filaments[0].update(
        {
            "storage_temperature_min_c": 10,
            "storage_temperature_max_c": 30,
            "storage_relative_humidity_max_percent": 20,
            "storage_relative_humidity_target_percent": 10,
            "storage_airtight_required": "yes",
            "storage_desiccant_recommended": "no",
            "storage_light_protection_required": False,
            "storage_after_opening_guidance": "Reseal the bag after opening.",
            "unopened_shelf_life_months": "24",
        }
    )

    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id, curation=True)
    assert summarize(plan)["error"] == 0, plan
    await apply_plan(
        db_session, draft, plan, admin_user_id=admin_user.id, curation=True
    )
    await db_session.commit()

    filament = await db_session.scalar(select(Filament))
    assert filament is not None
    assert filament.storage_temperature_min_c == 10
    assert filament.storage_temperature_max_c == 30
    assert filament.storage_relative_humidity_max_percent == 20
    assert filament.storage_relative_humidity_target_percent == 10
    assert filament.storage_airtight_required is True
    assert filament.storage_desiccant_recommended is False
    assert filament.storage_light_protection_required is False
    assert filament.storage_after_opening_guidance == "Reseal the bag after opening."
    assert filament.unopened_shelf_life_months == 24


async def test_master_import_updates_only_supplied_storage_facts_and_validates_them(
    db_session, admin_user
) -> None:
    draft, filament = await _existing_catalog(db_session)
    filament.storage_temperature_min_c = 5
    filament.storage_temperature_max_c = 35
    filament.storage_airtight_required = True
    filament.description = "Existing description"
    await db_session.commit()

    row = draft.filaments[0]
    row.update(
        {
            "mode": "update",
            "storage_temperature_min_c": 8,
            "storage_temperature_max_c": 32,
            "storage_desiccant_recommended": False,
            "storage_after_opening_guidance": "Store in a sealed container.",
            "unopened_shelf_life_months": 18,
        }
    )
    # Empty existing storage fields can be populated without overwrite; omitted
    # properties remain untouched, and changed nonempty values need overwrite.
    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id, curation=True)
    assert summarize(plan)["error"] == 1
    assert "storage_temperature" in plan[-1]["message"]

    row["overwrite"] = True
    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id, curation=True)
    assert summarize(plan)["error"] == 0, plan
    await apply_plan(
        db_session, draft, plan, admin_user_id=admin_user.id, curation=True
    )
    await db_session.commit()
    await db_session.refresh(filament)
    assert filament.storage_temperature_min_c == 8
    assert filament.storage_temperature_max_c == 32
    assert filament.storage_airtight_required is True
    assert filament.storage_desiccant_recommended is False
    assert filament.storage_relative_humidity_max_percent is None
    assert filament.storage_after_opening_guidance == "Store in a sealed container."
    assert filament.unopened_shelf_life_months == 18
    assert filament.description == "Existing description"

    row.update(
        {
            "storage_temperature_min_c": 40,
            "storage_temperature_max_c": 20,
            "storage_relative_humidity_max_percent": 10,
            "storage_relative_humidity_target_percent": 15,
            "unopened_shelf_life_months": 0,
        }
    )
    invalid = await build_plan(db_session, draft, admin_user_id=admin_user.id, curation=True)
    assert summarize(invalid)["error"] == 1
    assert "unopened_shelf_life_months" in invalid[-1]["message"]

    row["unopened_shelf_life_months"] = 18
    invalid = await build_plan(db_session, draft, admin_user_id=admin_user.id, curation=True)
    assert summarize(invalid)["error"] == 1
    assert "storage temperature minimum" in invalid[-1]["message"]

    row["storage_temperature_min_c"] = 10
    row["storage_temperature_max_c"] = 20
    invalid = await build_plan(db_session, draft, admin_user_id=admin_user.id, curation=True)
    assert summarize(invalid)["error"] == 1
    assert "storage humidity target exceeds maximum" in invalid[-1]["message"]


async def test_curation_import_creates_filler_and_effects_together(db_session, admin_user) -> None:
    draft = _draft()
    draft.filament_markets = []
    draft.presets = []
    draft.filaments[0].update(
        {
            "color_type": "single",
            "colors": ["#112233"],
            "finish": "glossy",
            "filler": "sparkle",
            "effects": ["sparkle", "glitter"],
            "transparency": False,
        }
    )
    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id, curation=True)
    assert summarize(plan)["error"] == 0, plan
    await apply_plan(db_session, draft, plan, admin_user_id=admin_user.id, curation=True)
    await db_session.commit()

    filament = await db_session.scalar(select(Filament))
    assert filament is not None
    assert filament.visual_settings["filler"] == "sparkle"
    assert filament.visual_settings["effects"] == ["sparkle", "glitter"]


async def test_curation_import_updates_filler_without_dropping_other_effects(
    db_session, admin_user
) -> None:
    draft, filament = await _existing_catalog(db_session)
    filament.visual_settings = {
        "color_type": "single",
        "colors": ["#112233"],
        "finish": "glossy",
        "filler": "glitter",
        "effects": ["glitter", "silk"],
        "transparency": False,
    }
    await db_session.commit()
    row = draft.filaments[0]
    row.update({"mode": "update", "filler": "sparkle", "overwrite": True})

    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id, curation=True)
    assert summarize(plan)["error"] == 0, plan
    await apply_plan(db_session, draft, plan, admin_user_id=admin_user.id, curation=True)
    await db_session.commit()
    await db_session.refresh(filament)
    assert filament.visual_settings["filler"] == "sparkle"
    assert filament.visual_settings["effects"] == ["sparkle", "silk"]
    assert filament.visual_settings["colors"] == ["#112233"]
    assert filament.visual_settings["finish"] == "glossy"


async def test_preview_confirmation_and_apply_work_through_admin_api(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user,
) -> None:
    draft = _draft()
    preview = await client.post(
        "/api/v1/admin/catalog/master-import/preview-draft",
        headers=_headers(admin_user),
        json=draft.model_dump(mode="json"),
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["summary"]["error"] == 0
    assert body["confirmation_token"]
    assert await db_session.scalar(select(func.count()).select_from(Brand)) == 0

    applied = await client.post(
        "/api/v1/admin/catalog/master-import/apply",
        headers=_headers(admin_user),
        json={
            "draft": body["draft"],
            "confirmation_token": body["confirmation_token"],
        },
    )
    assert applied.status_code == 200
    assert applied.json()["batch_id"] == 1
    assert await db_session.scalar(select(func.count()).select_from(Brand)) == 1

    history = await client.get(
        "/api/v1/admin/catalog/master-import/history",
        headers=_headers(admin_user),
    )
    assert history.status_code == 200
    assert history.json()["total"] == 1


async def _existing_catalog(db: AsyncSession) -> tuple[CatalogImportDraft, Filament]:
    brand = Brand(name="Example Materials", slug="example-materials")
    db.add(brand)
    await db.flush()
    filament = Filament(brand_id=brand.id, name="PLA Black", slug="pla-black", material_type="PLA")
    db.add(filament)
    await db.commit()
    return (
        CatalogImportDraft(
            filename="existing.xlsx",
            brands=[{"brand_key": "brand", "name": brand.name, "existing_brand": brand.id}],
            filaments=[
                {
                    "filament_key": "filament",
                    "brand_key": "brand",
                    "name": filament.name,
                    "material_type": filament.material_type,
                    "existing_filament": filament.id,
                }
            ],
        ),
        filament,
    )


@pytest.mark.parametrize("mode", ["auto", "update"])
@pytest.mark.parametrize("official", [False, True])
async def test_import_cannot_overwrite_another_owners_preset(
    db_session,
    admin_user,
    auth_user,
    mode,
    official,
) -> None:
    draft, filament = await _existing_catalog(db_session)
    source = Preset(
        filament_id=filament.id,
        user_id=None if official else auth_user.id,
        created_by_user_id=auth_user.id,
        name="Original",
        extruder_temp=200,
        bed_temp=50,
        is_official=official,
        moderation_status=PresetModerationStatus.APPROVED,
    )
    db_session.add(source)
    await db_session.commit()
    draft.presets = [
        {
            "preset_key": "copy",
            "filament_key": "filament",
            "mode": mode,
            "existing_preset": source.id,
            "overwrite": True,
            "name": "Replacement",
            "extruder_temp": 220,
            "bed_temp": 60,
        }
    ]
    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert plan[-1]["status"] == "error"
    assert "fork" in plan[-1]["message"]
    with pytest.raises(CatalogMasterImportError, match="invalid row"):
        await apply_plan(db_session, draft, plan, admin_user_id=admin_user.id)
    await db_session.refresh(source)
    assert source.name == "Original"
    assert source.extruder_temp == 200
    assert await db_session.scalar(select(func.count()).select_from(CatalogImportBatch)) == 0


async def test_explicit_fork_preserves_source_and_unspecified_settings(
    client,
    db_session,
    admin_user,
    auth_user,
) -> None:
    draft, filament = await _existing_catalog(db_session)
    printer = Printer(
        name="Source printer", manufacturer="Example", model="Model", slug="source-printer"
    )
    db_session.add(printer)
    source = Preset(
        filament_id=filament.id,
        user_id=auth_user.id,
        created_by_user_id=auth_user.id,
        name="Source recipe",
        extruder_temp=205,
        bed_temp=55,
        flow_rate=97,
        description="Source notes",
        fan_speed=80,
        retraction_length=0.8,
        retraction_speed=35,
        compat_context={"nozzle_type": "hardened"},
        orcaslicer_settings={
            "nozzle_temperature": ["205"],
            "filament_max_volumetric_speed": ["12"],
            "vendor_extension": ["kept"],
        },
        import_evidence={"type": "original", "payload": {"vendor_extension": ["kept"]}},
        source="orcaslicer",
        external_id="original-id",
        moderation_status=PresetModerationStatus.APPROVED,
    )
    db_session.add(source)
    await db_session.flush()
    db_session.add(PresetPrinter(preset_id=source.id, printer_id=printer.id, is_primary=True))
    await db_session.commit()
    original = {column.key: getattr(source, column.key) for column in Preset.__table__.columns}
    draft.presets = [
        {
            "preset_key": "copy",
            "filament_key": "filament",
            "mode": "fork",
            "existing_preset": source.id,
            "name": "Adapted recipe",
            "extruder_temp": 215,
        }
    ]
    preview = await client.post(
        "/api/v1/admin/catalog/master-import/preview-draft",
        headers=_headers(admin_user),
        json=draft.model_dump(mode="json"),
    )
    body = preview.json()
    assert body["summary"]["error"] == 0, body
    assert body["rows"][-1]["status"] == "create"
    assert body["rows"][-1]["derived_from_preset_id"] == source.id
    assert await db_session.scalar(select(func.count()).select_from(Preset)) == 1
    applied = await client.post(
        "/api/v1/admin/catalog/master-import/apply",
        headers=_headers(admin_user),
        json={"draft": body["draft"], "confirmation_token": body["confirmation_token"]},
    )
    assert applied.status_code == 200, applied.text
    await db_session.refresh(source)
    assert {
        column.key: getattr(source, column.key) for column in Preset.__table__.columns
    } == original
    fork = await db_session.scalar(select(Preset).where(Preset.user_id == admin_user.id))
    assert fork is not None and fork.id != source.id
    assert fork.derived_from_preset_id == source.id
    assert fork.created_by_user_id == admin_user.id
    assert not fork.is_official and not fork.is_weighted
    assert fork.organization_id is None
    assert not fork.active and fork.moderation_status == PresetModerationStatus.PENDING
    assert (fork.name, fork.extruder_temp, fork.bed_temp, fork.flow_rate) == (
        "Adapted recipe",
        215,
        55,
        97,
    )
    assert fork.description == source.description
    assert fork.compat_context == source.compat_context
    assert fork.orcaslicer_settings["nozzle_temperature"] == ["215"]
    assert fork.orcaslicer_settings["vendor_extension"] == ["kept"]
    assert fork.orcaslicer_settings["filament_max_volumetric_speed"] == ["12"]
    assert fork.import_evidence["source_snapshot"]["import_evidence"] == source.import_evidence
    assert fork.import_evidence["source_snapshot"]["extruder_temp"] == 205
    for preset_id in (source.id, fork.id):
        links = list(
            (
                await db_session.scalars(
                    select(PresetPrinter).where(PresetPrinter.preset_id == preset_id)
                )
            ).all()
        )
        assert [(link.printer_id, link.is_primary) for link in links] == [(printer.id, True)]


@pytest.mark.parametrize(
    "technical",
    [
        {"drying_temperature_c": 60},
        {"drying_duration_hours": 6},
        {"drying_required": True},
        {"drying_required": False, "drying_temperature_c": 60, "drying_duration_hours": 6},
        {"recommended_nozzle_temp_min": 250, "recommended_nozzle_temp_max": 200},
        {"recommended_bed_temp_min": 90, "recommended_bed_temp_max": 50},
        {"enclosure_requirement": "active"},
    ],
)
async def test_preview_rejects_inconsistent_exact_sku_before_confirmation(
    client,
    db_session,
    admin_user,
    technical,
) -> None:
    draft = _draft()
    draft.presets = []
    draft.filament_markets = []
    draft.filaments[0].update(technical)
    response = await client.post(
        "/api/v1/admin/catalog/master-import/preview-draft",
        headers=_headers(admin_user),
        json=draft.model_dump(mode="json"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["error"] == 1
    assert body["confirmation_token"] is None
    assert await db_session.scalar(select(func.count()).select_from(Brand)) == 0


async def test_import_validates_merged_exact_sku_for_partial_update(
    db_session,
    admin_user,
) -> None:
    draft, filament = await _existing_catalog(db_session)
    filament.drying_required = True
    filament.drying_temperature_c = 60
    filament.drying_duration_hours = 6
    filament.recommended_nozzle_temp_min = 200
    filament.recommended_nozzle_temp_max = 250
    await db_session.commit()
    draft.filaments[0].update(overwrite=True, drying_required=False)
    invalid = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert invalid[-1]["status"] == "error"
    draft.filaments[0].pop("drying_required")
    draft.filaments[0]["recommended_nozzle_temp_min"] = 260
    invalid_range = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert invalid_range[-1]["status"] == "error"
    draft.filaments[0].pop("recommended_nozzle_temp_min")
    draft.filaments[0]["drying_duration_hours"] = 8
    valid = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert valid[-1]["status"] == "update"
    await apply_plan(db_session, draft, valid, admin_user_id=admin_user.id)
    await db_session.commit()
    await db_session.refresh(filament)
    assert (
        filament.drying_required,
        filament.drying_temperature_c,
        filament.drying_duration_hours,
    ) == (
        True,
        60,
        8,
    )


async def test_two_rows_cannot_compose_an_invalid_exact_sku_update(db_session, admin_user) -> None:
    draft, _ = await _existing_catalog(db_session)
    first = draft.filaments[0]
    second = dict(first)
    first.update(
        overwrite=True, drying_required=True, drying_temperature_c=60, drying_duration_hours=6
    )
    second.update(
        filament_key="same-filament", name="Renamed PLA", overwrite=True, drying_required=False
    )
    draft.filaments.append(second)
    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    assert summarize(plan)["error"] == 1
    with pytest.raises(CatalogMasterImportError, match="invalid row"):
        await apply_plan(db_session, draft, plan, admin_user_id=admin_user.id)
    assert await db_session.scalar(select(func.count()).select_from(CatalogImportBatch)) == 0


async def test_fork_confirmation_covers_source_changes_and_private_sources_are_rejected(
    client,
    db_session,
    admin_user,
    auth_user,
) -> None:
    admin_id = admin_user.id
    draft, filament = await _existing_catalog(db_session)
    source = Preset(
        filament_id=filament.id,
        user_id=auth_user.id,
        name="Shared source",
        extruder_temp=205,
        bed_temp=55,
        active=True,
        moderation_status=PresetModerationStatus.APPROVED,
    )
    db_session.add(source)
    await db_session.commit()
    draft.presets = [
        {
            "preset_key": "copy",
            "filament_key": "filament",
            "mode": "fork",
            "existing_preset": source.id,
        }
    ]
    preview = await client.post(
        "/api/v1/admin/catalog/master-import/preview-draft",
        headers=_headers(admin_user),
        json=draft.model_dump(mode="json"),
    )
    body = preview.json()
    assert body["confirmation_token"] is not None
    source.extruder_temp = 225
    await db_session.commit()
    applied = await client.post(
        "/api/v1/admin/catalog/master-import/apply",
        headers=_headers(admin_user),
        json={"draft": body["draft"], "confirmation_token": body["confirmation_token"]},
    )
    assert applied.status_code == 409
    assert applied.json()["detail"]["code"] == "ERR_CATALOG_IMPORT_CONFIRMATION_INVALID"
    assert await db_session.scalar(select(func.count()).select_from(CatalogImportBatch)) == 0
    assert await db_session.scalar(select(func.count()).select_from(Preset)) == 1
    source = await db_session.scalar(select(Preset))
    source.active = False
    source.moderation_status = PresetModerationStatus.PENDING
    await db_session.commit()
    private = await build_plan(db_session, draft, admin_user_id=admin_id)
    assert private[-1]["status"] == "error"
    assert "public" in private[-1]["message"]


async def test_apply_rechecks_database_snapshot_even_when_session_cached_old_row(
    db_session,
    admin_user,
) -> None:
    draft, filament = await _existing_catalog(db_session)
    draft.brands[0].update(website="https://import.example", overwrite=True)
    plan = await build_plan(db_session, draft, admin_user_id=admin_user.id)
    await db_session.execute(
        update(Brand)
        .where(Brand.id == filament.brand_id)
        .values(website="https://other.example")
        .execution_options(synchronize_session=False)
    )
    await db_session.commit()
    with pytest.raises(CatalogMasterImportError) as caught:
        await apply_plan(db_session, draft, plan, admin_user_id=admin_user.id)
    assert caught.value.code == "ERR_CATALOG_IMPORT_STALE"
    assert await db_session.scalar(select(Brand.website)) == "https://other.example"
    assert await db_session.scalar(select(func.count()).select_from(CatalogImportBatch)) == 0


async def test_preview_and_apply_require_admin_and_bind_confirmation_to_actor(
    client,
    db_session,
    admin_user,
    auth_user,
) -> None:
    draft = _draft().model_dump(mode="json")
    base = "/api/v1/admin/catalog/master-import"
    for path, payload in (
        ("preview-draft", draft),
        ("apply", {"draft": draft, "confirmation_token": "invalid"}),
    ):
        anonymous = await client.post(f"{base}/{path}", json=payload)
        assert anonymous.status_code == 401
        regular = await client.post(f"{base}/{path}", headers=_headers(auth_user), json=payload)
        assert regular.status_code == 403
    preview = await client.post(f"{base}/preview-draft", headers=_headers(admin_user), json=draft)
    from app.models.user import UserRole

    auth_user.role = UserRole.ADMIN
    await db_session.commit()
    wrong_actor = await client.post(
        f"{base}/apply",
        headers=_headers(auth_user),
        json={"draft": draft, "confirmation_token": preview.json()["confirmation_token"]},
    )
    assert wrong_actor.status_code == 409
    assert wrong_actor.json()["detail"]["code"] == "ERR_CATALOG_IMPORT_CONFIRMATION_INVALID"
    assert await db_session.scalar(select(func.count()).select_from(CatalogImportBatch)) == 0
