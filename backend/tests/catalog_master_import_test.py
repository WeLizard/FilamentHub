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
