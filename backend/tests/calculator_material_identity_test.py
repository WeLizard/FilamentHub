"""Critical stable-ID boundaries for calculator material resolution."""

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User
from app.models.user_saved_preset import UserSavedPreset
from app.schemas.calculator import CalculatorFhubIdentity, CalculatorGcodeParseResponse
from app.services.calculator_material_identity_service import (
    resolve_calculator_material_identities,
    resolve_calculator_material_identities_for_jobs,
)


def _parsed(stable_id: str, *, name: str = "Misleading profile name") -> CalculatorGcodeParseResponse:
    return CalculatorGcodeParseResponse(
        file_name="job.gcode",
        file_size_bytes=100,
        materials=[
            {
                "tool_index": 0,
                "name": name,
                "slicer_filament_id": stable_id,
                "weight_g": 10,
            }
        ],
    )


async def _filament(db: AsyncSession, brand: Brand, *, name: str, slug: str) -> Filament:
    filament = Filament(
        brand_id=brand.id,
        name=name,
        slug=slug,
        material_type="PLA",
        diameter=1.75,
    )
    db.add(filament)
    await db.flush()
    return filament


@pytest.mark.asyncio
async def test_filamenthub_gcode_id_resolves_catalog_material_before_name(
    db_session: AsyncSession,
    auth_user: User,
) -> None:
    brand = Brand(name="Stable ID Brand", slug="stable-id-brand")
    db_session.add(brand)
    await db_session.flush()
    filament = await _filament(
        db_session,
        brand,
        name="Actual catalog PLA",
        slug="actual-catalog-pla",
    )

    resolved = await resolve_calculator_material_identities(
        db_session,
        _parsed(f"FHUB_F_{filament.id:06d}"),
        user_id=auth_user.id,
    )

    resolution = resolved.materials[0].identity_resolution
    assert resolution is not None
    assert resolution.status == "resolved"
    assert resolution.source == "filamenthub_filament_id"
    assert resolution.filament_id == filament.id


@pytest.mark.asyncio
async def test_namespaced_managed_preset_resolves_before_orca_family_id(
    db_session: AsyncSession,
    auth_user: User,
) -> None:
    brand = Brand(name="Managed ID Brand", slug="managed-id-brand")
    db_session.add(brand)
    await db_session.flush()
    filament = await _filament(
        db_session,
        brand,
        name="Exact managed PETG",
        slug="exact-managed-petg",
    )
    preset = Preset(
        filament_id=filament.id,
        user_id=auth_user.id,
        name="Exact managed preset",
        extruder_temp=240,
        bed_temp=80,
        is_official=False,
        active=True,
    )
    db_session.add(preset)
    await db_session.flush()
    parsed = _parsed("OGFG99")
    parsed = parsed.model_copy(
        update={
            "fhub_identities": [
                CalculatorFhubIdentity(
                    kind="material_preset", entity_id=preset.id, tool_index=0
                )
            ]
        }
    )

    resolved = await resolve_calculator_material_identities(
        db_session,
        parsed,
        user_id=auth_user.id,
    )

    resolution = resolved.materials[0].identity_resolution
    assert resolution is not None
    assert resolution.source == "filamenthub_preset_id"
    assert resolution.preset_id == preset.id
    assert resolution.filament_id == filament.id
    assert resolved.fhub_identities[0].entity_id == preset.id


@pytest.mark.asyncio
async def test_private_foreign_preset_identity_is_not_trusted(
    db_session: AsyncSession,
    auth_user: User,
    admin_user: User,
) -> None:
    brand = Brand(name="Private ID Brand", slug="private-id-brand")
    db_session.add(brand)
    await db_session.flush()
    filament = await _filament(
        db_session,
        brand,
        name="Private managed PETG",
        slug="private-managed-petg",
    )
    preset = Preset(
        filament_id=filament.id,
        user_id=admin_user.id,
        name="Someone else's draft",
        extruder_temp=240,
        bed_temp=80,
        is_official=False,
        active=False,
    )
    db_session.add(preset)
    await db_session.flush()
    parsed = _parsed("OGFG99").model_copy(
        update={
            "fhub_identities": [
                CalculatorFhubIdentity(
                    kind="material_preset", entity_id=preset.id, tool_index=0
                )
            ]
        }
    )

    resolved = await resolve_calculator_material_identities(
        db_session,
        parsed,
        user_id=auth_user.id,
    )

    assert resolved.fhub_identities == []
    resolution = resolved.materials[0].identity_resolution
    assert resolution is not None
    assert resolution.status == "unresolved"
    assert resolution.stable_id == "OGFG99"


@pytest.mark.asyncio
async def test_historical_approved_preset_identity_remains_resolvable(
    db_session: AsyncSession,
    auth_user: User,
) -> None:
    brand = Brand(name="Historical ID Brand", slug="historical-id-brand")
    db_session.add(brand)
    await db_session.flush()
    filament = await _filament(
        db_session,
        brand,
        name="Historical managed ABS",
        slug="historical-managed-abs",
    )
    preset = Preset(
        filament_id=filament.id,
        user_id=None,
        name="Former catalog preset",
        extruder_temp=250,
        bed_temp=100,
        is_official=False,
        active=False,
        moderation_status=PresetModerationStatus.APPROVED,
    )
    db_session.add(preset)
    await db_session.flush()
    parsed = _parsed("OGFB99").model_copy(
        update={
            "fhub_identities": [
                CalculatorFhubIdentity(
                    kind="material_preset", entity_id=preset.id, tool_index=0
                )
            ]
        }
    )

    resolved = await resolve_calculator_material_identities(
        db_session,
        parsed,
        user_id=auth_user.id,
    )

    resolution = resolved.materials[0].identity_resolution
    assert resolution is not None
    assert resolution.source == "filamenthub_preset_id"
    assert resolution.preset_id == preset.id
    assert resolution.filament_id == filament.id


@pytest.mark.asyncio
async def test_legacy_filamenthub_gcode_id_remains_readable(
    db_session: AsyncSession,
    auth_user: User,
) -> None:
    """Old G-code remains usable after separating preset and material IDs."""
    brand = Brand(name="Legacy ID Brand", slug="legacy-id-brand")
    db_session.add(brand)
    await db_session.flush()
    filament = await _filament(
        db_session,
        brand,
        name="Legacy catalog PLA",
        slug="legacy-catalog-pla",
    )

    resolved = await resolve_calculator_material_identities(
        db_session,
        _parsed(f"FHUB{filament.id:06d}"),
        user_id=auth_user.id,
    )

    resolution = resolved.materials[0].identity_resolution
    assert resolution is not None
    assert resolution.status == "resolved"
    assert resolution.source == "filamenthub_filament_id"
    assert resolution.filament_id == filament.id


@pytest.mark.asyncio
async def test_orca_family_id_shared_by_presets_is_never_an_identity(
    db_session: AsyncSession,
    auth_user: User,
) -> None:
    """A library family id (OFYPdQJh) is carried by every preset derived from it."""
    brand = Brand(name="Family ID Brand", slug="family-id-brand")
    db_session.add(brand)
    await db_session.flush()
    only = await _filament(db_session, brand, name="Only PETG", slug="only-family-petg")
    db_session.add(
        Preset(
            filament_id=only.id,
            user_id=auth_user.id,
            name="Single family preset",
            extruder_temp=240,
            bed_temp=80,
            is_official=False,
            active=True,
            orcaslicer_settings={"filament_id": "OFYPdQJh"},
        )
    )
    db_session.add(
        Preset(
            filament_id=only.id,
            user_id=None,
            name="Catalog family preset",
            extruder_temp=240,
            bed_temp=80,
            is_official=True,
            active=True,
            orcaslicer_settings={"filament_id": "GFB00"},
        )
    )
    await db_session.flush()

    for family_id in ("OFYPdQJh", "GFB00"):
        resolved = await resolve_calculator_material_identities(
            db_session,
            _parsed(family_id),
            user_id=auth_user.id,
        )

        resolution = resolved.materials[0].identity_resolution
        assert resolution is not None
        assert resolution.status == "unresolved"
        assert resolution.source is None
        assert resolution.filament_id is None


async def _managed_preset(
    db: AsyncSession,
    owner: User | None,
    brand: Brand,
    *,
    material_type: str,
    filament_name: str,
    preset_name: str,
    slug: str,
    family_id: str | None = "OFYPdQJh",
    saved_by: User | None = None,
    sync: bool = True,
) -> Preset:
    filament = Filament(
        brand_id=brand.id,
        name=filament_name,
        slug=slug,
        material_type=material_type,
        diameter=1.75,
    )
    db.add(filament)
    await db.flush()
    preset = Preset(
        filament_id=filament.id,
        user_id=owner.id if owner else None,
        name=preset_name,
        extruder_temp=240,
        bed_temp=80,
        is_official=False,
        active=True,
        moderation_status=PresetModerationStatus.APPROVED,
        orcaslicer_settings={"filament_id": family_id} if family_id else None,
    )
    db.add(preset)
    await db.flush()
    if saved_by is not None:
        db.add(UserSavedPreset(user_id=saved_by.id, preset_id=preset.id, sync=sync))
        await db.flush()
    return preset


def _managed_parsed(settings_id: str, *, family_id: str = "OFYPdQJh") -> CalculatorGcodeParseResponse:
    return CalculatorGcodeParseResponse(
        file_name="job.gcode",
        file_size_bytes=100,
        materials=[
            {
                "tool_index": 0,
                "type": "PETG",
                "name": settings_id,
                "settings_id": settings_id,
                "vendor": "Hi-Tech Plast",
                "slicer_filament_id": family_id,
                "weight_g": 10,
            }
        ],
    )


@pytest.mark.asyncio
async def test_managed_preset_name_resolves_among_presets_sharing_the_family_id(
    db_session: AsyncSession,
    auth_user: User,
) -> None:
    brand = Brand(name="Hi-Tech Plast", slug="hi-tech-plast")
    other_brand = Brand(name="SeedBrand", slug="seedbrand-managed")
    db_session.add_all([brand, other_brand])
    await db_session.flush()
    gold = await _managed_preset(
        db_session,
        auth_user,
        brand,
        material_type="PETG",
        filament_name="HTP PETG Gold",
        preset_name="HTP - PETG Gold",
        slug="htp-petg-gold",
        saved_by=auth_user,
    )
    # Same family id, different filament: the old id match would have hit these.
    for index in range(3):
        await _managed_preset(
            db_session,
            None,
            other_brand,
            material_type="PETG",
            filament_name=f"PETG White {index}",
            preset_name=f"PETG White {index}",
            slug=f"seed-petg-white-{index}",
        )

    resolved = await resolve_calculator_material_identities(
        db_session,
        _managed_parsed(
            "_local/filamenthub/PETG • hi-tech plast • HTP - PETG Gold "
        ),
        user_id=auth_user.id,
    )

    resolution = resolved.materials[0].identity_resolution
    assert resolution is not None
    assert resolution.status == "resolved"
    assert resolution.source == "filamenthub_managed_name"
    assert resolution.filament_id == gold.filament_id
    assert resolution.preset_id == gold.id


@pytest.mark.asyncio
async def test_managed_preset_name_survives_filename_sanitising(
    db_session: AsyncSession,
    auth_user: User,
) -> None:
    brand = Brand(name="Hi-Tech Plast", slug="hi-tech-plast-sanitised")
    db_session.add(brand)
    await db_session.flush()
    preset = await _managed_preset(
        db_session,
        auth_user,
        brand,
        material_type="PETG",
        filament_name="Slash PETG",
        preset_name="PETG 0.2/0.4: gold?",
        slug="slash-petg",
        saved_by=auth_user,
    )

    resolved = await resolve_calculator_material_identities(
        db_session,
        _managed_parsed("_local/filamenthub/PETG • Hi-Tech Plast • PETG 0.2_0.4_ gold"),
        user_id=auth_user.id,
    )

    resolution = resolved.materials[0].identity_resolution
    assert resolution is not None
    assert resolution.status == "resolved"
    assert resolution.preset_id == preset.id


@pytest.mark.asyncio
async def test_managed_duplicate_suffix_selects_the_exact_preset(
    db_session: AsyncSession,
    auth_user: User,
) -> None:
    brand = Brand(name="Twin Brand", slug="twin-brand")
    db_session.add(brand)
    await db_session.flush()
    first = await _managed_preset(
        db_session, auth_user, brand, material_type="PETG", filament_name="Twin A",
        preset_name="Twin", slug="twin-a", saved_by=auth_user,
    )
    second = await _managed_preset(
        db_session, auth_user, brand, material_type="PETG", filament_name="Twin B",
        preset_name="Twin", slug="twin-b", saved_by=auth_user,
    )

    by_name = await resolve_calculator_material_identities(
        db_session,
        _managed_parsed("_local/filamenthub/PETG • Twin Brand • Twin"),
        user_id=auth_user.id,
    )
    by_suffix = await resolve_calculator_material_identities(
        db_session,
        _managed_parsed(f"_local/filamenthub/PETG • Twin Brand • Twin (FH-{second.id})"),
        user_id=auth_user.id,
    )

    ambiguous = by_name.materials[0].identity_resolution
    assert ambiguous is not None
    assert ambiguous.status == "ambiguous"
    assert ambiguous.source == "filamenthub_managed_name"
    assert ambiguous.filament_id is None
    assert ambiguous.candidate_filament_ids == sorted([first.filament_id, second.filament_id])
    exact = by_suffix.materials[0].identity_resolution
    assert exact is not None
    assert exact.status == "resolved"
    assert exact.source == "filamenthub_managed_name"
    assert exact.preset_id == second.id
    assert exact.filament_id == second.filament_id


@pytest.mark.asyncio
async def test_managed_name_never_reaches_another_users_private_preset(
    db_session: AsyncSession,
    auth_user: User,
    admin_user: User,
) -> None:
    brand = Brand(name="Private Brand", slug="private-managed-brand")
    db_session.add(brand)
    await db_session.flush()
    foreign = await _managed_preset(
        db_session, admin_user, brand, material_type="PETG", filament_name="Foreign PETG",
        preset_name="Secret blend", slug="foreign-petg", saved_by=admin_user,
    )
    foreign.moderation_status = PresetModerationStatus.PENDING
    await db_session.flush()

    by_name = await resolve_calculator_material_identities(
        db_session,
        _managed_parsed("_local/filamenthub/PETG • Private Brand • Secret blend"),
        user_id=auth_user.id,
    )
    by_suffix = await resolve_calculator_material_identities(
        db_session,
        _managed_parsed(f"_local/filamenthub/PETG • Private Brand • Secret blend (FH-{foreign.id})"),
        user_id=auth_user.id,
    )

    for resolved in (by_name, by_suffix):
        resolution = resolved.materials[0].identity_resolution
        assert resolution is not None
        assert resolution.status == "unresolved"
        assert resolution.filament_id is None
        assert resolution.preset_id is None


@pytest.mark.asyncio
async def test_managed_name_ignores_presets_the_user_did_not_sync(
    db_session: AsyncSession,
    auth_user: User,
    admin_user: User,
) -> None:
    brand = Brand(name="Library Brand", slug="library-managed-brand")
    db_session.add(brand)
    await db_session.flush()
    await _managed_preset(
        db_session, admin_user, brand, material_type="PETG", filament_name="Public PETG",
        preset_name="Public blend", slug="public-petg", saved_by=auth_user, sync=False,
    )

    resolved = await resolve_calculator_material_identities(
        db_session,
        _managed_parsed("_local/filamenthub/PETG • Library Brand • Public blend"),
        user_id=auth_user.id,
    )

    resolution = resolved.materials[0].identity_resolution
    assert resolution is not None
    assert resolution.status == "unresolved"


@pytest.mark.asyncio
async def test_fhub_identity_wins_over_managed_name(
    db_session: AsyncSession,
    auth_user: User,
) -> None:
    brand = Brand(name="Priority Brand", slug="priority-brand")
    db_session.add(brand)
    await db_session.flush()
    named = await _managed_preset(
        db_session, auth_user, brand, material_type="PETG", filament_name="Named",
        preset_name="Named preset", slug="priority-named", saved_by=auth_user,
    )
    identified = await _managed_preset(
        db_session, auth_user, brand, material_type="PETG", filament_name="Identified",
        preset_name="Identified preset", slug="priority-identified", saved_by=auth_user,
    )
    parsed = _managed_parsed("_local/filamenthub/PETG • Priority Brand • Named preset").model_copy(
        update={
            "fhub_identities": [
                CalculatorFhubIdentity(
                    kind="material_preset", entity_id=identified.id, tool_index=0
                )
            ]
        }
    )

    resolved = await resolve_calculator_material_identities(
        db_session, parsed, user_id=auth_user.id
    )

    resolution = resolved.materials[0].identity_resolution
    assert resolution is not None
    assert resolution.source == "filamenthub_preset_id"
    assert resolution.preset_id == identified.id
    assert resolution.preset_id != named.id


@pytest.mark.asyncio
async def test_batch_resolution_uses_a_fixed_number_of_queries(
    db_session: AsyncSession,
    auth_user: User,
) -> None:
    brand = Brand(name="Batch Brand", slug="batch-brand")
    db_session.add(brand)
    await db_session.flush()
    presets = [
        await _managed_preset(
            db_session, auth_user, brand, material_type="PETG", filament_name=f"Batch {index}",
            preset_name=f"Batch {index}", slug=f"batch-{index}", saved_by=auth_user,
        )
        for index in range(4)
    ]
    jobs = [
        _managed_parsed(f"_local/filamenthub/PETG • Batch Brand • Batch {index}")
        for index in range(4)
    ]
    jobs.append(_managed_parsed(f"_local/filamenthub/PETG • Batch Brand • Batch 0 (FH-{presets[0].id})"))
    statements: list[str] = []

    def count(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    assert db_session.bind is not None
    event.listen(db_session.bind.sync_engine, "before_cursor_execute", count)
    try:
        resolved = await resolve_calculator_material_identities_for_jobs(
            db_session, jobs, user_id=auth_user.id
        )
    finally:
        event.remove(db_session.bind.sync_engine, "before_cursor_execute", count)

    assert [job.materials[0].identity_resolution.preset_id for job in resolved] == [
        *(preset.id for preset in presets),
        presets[0].id,
    ]
    assert len(statements) == 2
