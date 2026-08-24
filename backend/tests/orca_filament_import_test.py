"""The path presets actually travel: OrcaSlicer sends filament presets to FilamentHub.

This is the core of the product and it had no coverage at all. Three lookups in
the import read JSON through a PostgreSQL-only construct, so the whole endpoint
raised on the SQLite test engine and could only ever be checked by hand against
a development server. The lookups are portable now, and this is what they were
blocking.

Nothing here proves anything about the account lock that serialises concurrent
imports: that is a PostgreSQL advisory lock and SQLite has no such thing. The
lock is verified against a real database.
"""

import hashlib
import json

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament
from app.models.filament_country_cell import FilamentCountryCell
from app.models.preset import Preset, PresetModerationStatus
from app.models.user import User
from tests.conftest import registration_payload

IMPORT_URL = "/api/v1/orcaslicer/filaments/import"


async def _signed_in(client: AsyncClient, db: AsyncSession, suffix: str) -> tuple[dict, User]:
    email = f"{suffix}@example.com"
    password = "testpassword123"
    registered = await client.post(
        "/api/v1/auth/register",
        json=registration_payload(
            email=email, username=f"user_{suffix}", password=password
        ),
    )
    assert registered.status_code == 201

    logged_in = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert logged_in.status_code == 200

    person = await db.scalar(select(User).where(User.email == email))
    return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}, person


def _preset(name: str, **overrides) -> dict:
    """A preset shaped the way the plugin sends one."""
    payload = {
        "name": name,
        "external_id": f"orca-{name.lower().replace(' ', '-')}",
        "extruder_temp": 210,
        "bed_temp": 60,
        "orcaslicer_settings": {
            "filament_type": ["PLA"],
            "filament_vendor": ["Test Vendor"],
            "nozzle_temperature": ["210"],
        },
    }
    payload.update(overrides)
    return payload


async def _import(client: AsyncClient, headers: dict, *profiles: dict):
    return await client.post(IMPORT_URL, headers=headers, json={"profiles": list(profiles)})


@pytest.mark.asyncio
async def test_a_users_own_preset_arrives_as_a_draft(
    client: AsyncClient, db_session: AsyncSession
):
    """Someone else's preset is not published — it waits as the author's draft."""
    headers, person = await _signed_in(client, db_session, "orca-import-draft")

    profile = _preset("Shop PLA")
    profile["source_version"] = "0.1.2"
    profile["capture_mode"] = "resolved_runtime"
    profile["orcaslicer_settings"]["future_orca_field"] = {
        "mode": "keep-shape",
        "values": [1, "two"],
    }
    profile["orcaslicer_settings"]["future_orca_option"] = ["keep me"]
    response = await _import(client, headers, profile)

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["status"] == "created"
    assert result["review_state"] == "needs_decision"
    assert result["important_decisions"] == 3
    assert result["preset_readiness_percent"] == 70
    assert result["catalog_readiness_percent"] == 55

    draft = await db_session.scalar(
        select(Preset).where(Preset.external_id == "orca-shop-pla")
    )
    assert draft is not None
    assert draft.user_id == person.id
    assert draft.active is False
    # A draft carries no material, so there is nothing to moderate until it is bound.
    assert draft.moderation_status == PresetModerationStatus.NOT_REQUIRED
    assert draft.extruder_temp == 210
    assert draft.orcaslicer_settings["fhub_draft_id"] == f"draft_{person.id}_orca-shop-pla"
    # Storage is the round-trip authority and keeps every unknown shape as sent.
    assert draft.orcaslicer_settings["future_orca_field"] == {
        "mode": "keep-shape",
        "values": [1, "two"],
    }
    assert draft.import_evidence["original"]["settings"] == profile["orcaslicer_settings"]
    assert "fhub_draft_id" not in draft.import_evidence["original"]["settings"]
    assert draft.import_evidence["original"]["source_version"] == "0.1.2"
    assert draft.import_evidence["original"]["capture_mode"] == "resolved_runtime"
    canonical = json.dumps(
        profile["orcaslicer_settings"],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    assert draft.import_evidence["original"]["settings_sha256"] == hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()

    analysis = await client.get(
        f"/api/v1/presets/{draft.id}/draft-analysis",
        headers=headers,
    )
    assert analysis.status_code == 200
    review = analysis.json()
    assert review["evidence_kind"] == "orca_capture"
    assert review["suggestions"]["brand_name"] == {
        "value": "Test Vendor",
        "source": "orca",
        "confidence": "high",
        "direct": True,
    }
    assert review["suggestions"]["material_type"]["value"] == "PLA"
    assert review["preset_readiness_percent"] == 70
    assert review["catalog_readiness_percent"] == 55
    assert review["preset_decisions"] == ["confirm_bed_temperature"]
    assert review["catalog_decisions"] == [
        "confirm_new_brand",
        "choose_or_create_filament",
    ]
    assert review["review_state"] == "needs_decision"
    assert review["technical_settings_count"] >= 4

    queue = await client.get("/api/v1/presets/draft-analyses", headers=headers)
    assert queue.status_code == 200
    assert queue.json()["total"] == 1
    assert queue.json()["needs_decision"] == 1
    assert queue.json()["items"][0]["preset_id"] == draft.id

    # The plugin writes this list into OrcaSlicer, and the draft came from there:
    # its original file is already on that machine, so shipping a managed copy
    # back would put two near-identical presets in the user's list. It becomes
    # syncable once it is bound to a filament and activated.
    global_sync = await client.get("/api/v1/auth/my-presets", headers=headers)
    assert global_sync.status_code == 200
    assert [item["id"] for item in global_sync.json()["items"]] == []

    exported = await client.get(
        f"/api/v1/presets/{draft.id}/export/orcaslicer.json",
        headers=headers,
    )
    assert exported.status_code == 404

    outsider_headers, _ = await _signed_in(
        client, db_session, "orca-import-draft-outsider"
    )
    hidden = await client.get(
        f"/api/v1/presets/{draft.id}/export/orcaslicer.json",
        headers=outsider_headers,
    )
    assert hidden.status_code == 404

    owner_list = await client.get(
        f"/api/v1/presets/?active_only=false&user_id={person.id}",
        headers=headers,
    )
    assert owner_list.status_code == 200
    assert [item["id"] for item in owner_list.json()["items"]] == [draft.id]

    outsider_list = await client.get(
        f"/api/v1/presets/?active_only=false&user_id={person.id}",
        headers=outsider_headers,
    )
    assert outsider_list.status_code == 200
    assert outsider_list.json()["items"] == []
    assert outsider_list.json()["total"] == 0

    hidden_detail = await client.get(
        f"/api/v1/presets/{draft.id}",
        headers=outsider_headers,
    )
    assert hidden_detail.status_code == 404


@pytest.mark.asyncio
async def test_publishing_a_draft_preserves_private_evidence_and_enables_managed_sync(
    client: AsyncClient, db_session: AsyncSession
):
    """Review publishes safe settings, never workstation secrets or personal G-code."""
    brand = Brand(name="Safe Vendor", slug="safe-vendor", active=True)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Safe PLA",
        slug="safe-pla",
        material_type="PLA",
        color_name="Blue",
        color_hex="#2244AA",
        diameter=1.75,
        active=True,
    )
    db_session.add(filament)
    await db_session.flush()
    headers, person = await _signed_in(client, db_session, "orca-publish-safe")
    person_id = person.id
    raw_settings = {
        "filament_type": ["PLA"],
        "nozzle_temperature": ["215"],
        "hot_plate_temp": ["55"],
        "filament_start_gcode": ["M118 private-workstation-macro"],
        "filament_notes": ["Bought for a private customer"],
        "print_host": "192.168.1.44",
        "service_token": "do-not-publish",
        "future_safe_option": ["private-until-schema-intake"],
        "future_container": {
            "service_token": "nested-secret",
            "printer_ip": "10.0.0.9",
            "unknown_personal_alias": "customer-a",
        },
    }
    imported = await _import(
        client,
        headers,
        _preset("Safe PLA tuned", orcaslicer_settings=raw_settings),
    )
    assert imported.status_code == 200
    draft_id = imported.json()["results"][0]["fhub_id"]

    published = await client.patch(
        f"/api/v1/presets/{draft_id}",
        headers=headers,
        json={
            "name": "Safe PLA tuned",
            "filament_id": filament.id,
            "active": True,
            "orcaslicer_settings": {
                **raw_settings,
                "fhub_draft_id": f"draft_{person.id}_orca-safe-pla-tuned",
            },
        },
    )

    assert published.status_code == 200
    db_session.expire_all()
    preset = await db_session.get(Preset, draft_id)
    assert preset is not None and preset.active is True
    assert preset.import_evidence["original"]["settings"] == raw_settings
    assert preset.import_evidence["promotion_identity"] == {
        "external_id": "orca-safe-pla-tuned",
        "draft_id": f"draft_{person_id}_orca-safe-pla-tuned",
    }
    assert "future_safe_option" not in preset.orcaslicer_settings
    assert "future_container" not in preset.orcaslicer_settings
    assert "filament_start_gcode" not in preset.orcaslicer_settings
    assert "filament_notes" not in preset.orcaslicer_settings
    assert "print_host" not in preset.orcaslicer_settings
    assert "service_token" not in preset.orcaslicer_settings
    assert "derived_from_external_id" not in preset.orcaslicer_settings
    assert "derived_from_draft_id" not in preset.orcaslicer_settings

    managed = await client.get("/api/v1/auth/my-presets", headers=headers)
    assert managed.status_code == 200
    assert [item["id"] for item in managed.json()["items"]] == [draft_id]

    exported = await client.get(
        f"/api/v1/presets/{draft_id}/export/orcaslicer.json",
        headers=headers,
    )
    assert exported.status_code == 200
    public_profile = exported.json()
    assert "future_safe_option" not in public_profile
    assert "future_container" not in public_profile
    assert "filament_start_gcode" not in public_profile
    assert "filament_notes" not in public_profile
    assert "print_host" not in public_profile
    assert "service_token" not in public_profile
    assert "derived_from_external_id" not in public_profile
    assert "derived_from_draft_id" not in public_profile


@pytest.mark.asyncio
async def test_legacy_active_preset_projects_raw_settings_safely(
    client: AsyncClient, db_session: AsyncSession
):
    """Rows published before evidence separation must not leak their old raw blob."""
    brand = Brand(name="Legacy Safe Vendor", slug="legacy-safe-vendor", active=True)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Legacy Safe PLA",
        slug="legacy-safe-pla",
        material_type="PLA",
        diameter=1.75,
        active=True,
    )
    db_session.add(filament)
    await db_session.flush()
    owner_headers, owner = await _signed_in(client, db_session, "legacy-safe-owner")
    outsider_headers, _ = await _signed_in(client, db_session, "legacy-safe-outsider")
    legacy = Preset(
        filament_id=filament.id,
        user_id=owner.id,
        name="Legacy Safe PLA tuned",
        extruder_temp=215,
        bed_temp=55,
        active=True,
        moderation_status=PresetModerationStatus.APPROVED,
        orcaslicer_settings={
            "filament_type": ["PLA"],
            "nozzle_temperature": ["215"],
            "service_token": "legacy-secret",
            "print_host": "192.168.1.90",
            "filament_start_gcode": ["M118 legacy-private"],
            "legacy_unknown_note": "private customer",
        },
    )
    db_session.add(legacy)
    await db_session.commit()

    detail = await client.get(
        f"/api/v1/presets/{legacy.id}",
        headers=outsider_headers,
    )
    assert detail.status_code == 200
    public_settings = detail.json()["orcaslicer_settings"]
    assert public_settings["nozzle_temperature"] == ["215"]
    assert "service_token" not in public_settings
    assert "print_host" not in public_settings
    assert "filament_start_gcode" not in public_settings
    assert "legacy_unknown_note" not in public_settings

    exported = await client.get(
        f"/api/v1/presets/{legacy.id}/export/orcaslicer.json",
        headers=outsider_headers,
    )
    assert exported.status_code == 200
    exported_settings = exported.json()
    assert exported_settings["nozzle_temperature"] == ["215"]
    assert "service_token" not in exported_settings
    assert "print_host" not in exported_settings
    assert "filament_start_gcode" not in exported_settings
    assert "legacy_unknown_note" not in exported_settings

    owner_exported = await client.get(
        f"/api/v1/presets/{legacy.id}/export/orcaslicer.json",
        headers=owner_headers,
    )
    assert owner_exported.status_code == 200
    owner_settings = owner_exported.json()
    assert owner_settings["service_token"] == "legacy-secret"
    assert owner_settings["print_host"] == "192.168.1.90"
    assert owner_settings["filament_start_gcode"] == ["M118 legacy-private"]
    assert owner_settings["legacy_unknown_note"] == "private customer"

    outsider_batch = await client.post(
        "/api/v1/orcaslicer/presets/batch-export",
        headers=outsider_headers,
        json={"preset_ids": [legacy.id]},
    )
    assert outsider_batch.status_code == 200
    outsider_batch_settings = outsider_batch.json()["profiles"][0]["config"]
    assert outsider_batch_settings["nozzle_temperature"] == ["215"]
    assert "service_token" not in outsider_batch_settings
    assert "legacy_unknown_note" not in outsider_batch_settings

    owner_batch = await client.post(
        "/api/v1/orcaslicer/presets/batch-export",
        headers=owner_headers,
        json={"preset_ids": [legacy.id]},
    )
    assert owner_batch.status_code == 200
    owner_batch_settings = owner_batch.json()["profiles"][0]["config"]
    assert owner_batch_settings["service_token"] == "legacy-secret"
    assert owner_batch_settings["legacy_unknown_note"] == "private customer"

    for temperature, token in ((216, "legacy-secret-v1"), (217, "legacy-secret-v2")):
        updated = await client.patch(
            f"/api/v1/presets/{legacy.id}",
            headers=owner_headers,
            json={
                "orcaslicer_settings": {
                    **legacy.orcaslicer_settings,
                    "nozzle_temperature": [str(temperature)],
                    "service_token": token,
                }
            },
        )
        assert updated.status_code == 200

    versions = await client.get(
        f"/api/v1/presets/{legacy.id}/versions",
        headers=outsider_headers,
    )
    assert versions.status_code == 200
    public_versions = versions.json()["items"]
    assert len(public_versions) == 2
    newest_id = public_versions[0]["id"]
    oldest_id = public_versions[1]["id"]

    public_version = await client.get(
        f"/api/v1/presets/{legacy.id}/versions/{newest_id}",
        headers=outsider_headers,
    )
    assert public_version.status_code == 200
    public_version_settings = public_version.json()["snapshot_orcaslicer_settings"]
    assert public_version_settings["nozzle_temperature"] == ["217"]
    assert "service_token" not in public_version_settings
    assert "legacy_unknown_note" not in public_version_settings

    owner_version = await client.get(
        f"/api/v1/presets/{legacy.id}/versions/{newest_id}",
        headers=owner_headers,
    )
    assert owner_version.json()["snapshot_orcaslicer_settings"]["service_token"] == (
        "legacy-secret-v2"
    )

    public_diff = await client.get(
        f"/api/v1/presets/{legacy.id}/versions/{oldest_id}/diff/{newest_id}",
        headers=outsider_headers,
    )
    assert public_diff.status_code == 200
    serialized_diff = json.dumps(public_diff.json(), ensure_ascii=False)
    assert "service_token" not in serialized_diff
    assert "legacy-secret" not in serialized_diff

    await db_session.refresh(legacy)
    assert legacy.orcaslicer_settings["service_token"] == "legacy-secret-v2"


@pytest.mark.asyncio
async def test_linking_a_draft_without_explicit_publish_keeps_it_private(
    client: AsyncClient, db_session: AsyncSession
):
    """Catalog selection is review state, not an implicit Publish action."""
    brand = Brand(name="Private Link Vendor", slug="private-link-vendor", active=True)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Private Link PLA",
        slug="private-link-pla",
        material_type="PLA",
        diameter=1.75,
        active=True,
    )
    db_session.add(filament)
    await db_session.flush()
    owner_headers, owner = await _signed_in(client, db_session, "orca-link-private")
    outsider_headers, _ = await _signed_in(client, db_session, "orca-link-outsider")
    imported = await _import(
        client,
        owner_headers,
        _preset(
            "Private Link PLA",
            orcaslicer_settings={
                "filament_type": ["PLA"],
                "nozzle_temperature": ["215"],
                "service_token": "raw-private-token",
            },
        ),
    )
    draft_id = imported.json()["results"][0]["fhub_id"]

    linked = await client.patch(
        f"/api/v1/presets/{draft_id}",
        headers=owner_headers,
        json={"filament_id": filament.id},
    )

    assert linked.status_code == 200
    assert linked.json()["active"] is False
    preset = await db_session.get(Preset, draft_id)
    assert preset is not None and preset.active is False
    assert preset.orcaslicer_settings["service_token"] == "raw-private-token"
    assert preset.user_id == owner.id

    assert (
        await client.get(f"/api/v1/presets/{draft_id}", headers=outsider_headers)
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/presets/{draft_id}/export/orcaslicer.json",
            headers=outsider_headers,
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/api/v1/presets/{draft_id}/versions",
            headers=outsider_headers,
        )
    ).status_code == 403
    managed = await client.get("/api/v1/auth/my-presets", headers=owner_headers)
    assert managed.status_code == 200
    assert [item["id"] for item in managed.json()["items"]] == []


@pytest.mark.asyncio
async def test_real_default_looking_values_remain_orca_evidence(
    client: AsyncClient, db_session: AsyncSession
):
    """200/60 may be intentional and must never be rewritten as a dummy."""
    headers, _ = await _signed_in(client, db_session, "orca-real-defaults")
    profile = _preset(
        "Workshop PETG",
        extruder_temp=None,
        bed_temp=None,
        orcaslicer_settings={
            "filament_type": ["PETG"],
            "nozzle_temperature": ["200"],
            "hot_plate_temp": ["60"],
        },
    )

    response = await _import(client, headers, profile)
    assert response.status_code == 200
    draft = await db_session.scalar(
        select(Preset).where(Preset.external_id == "orca-workshop-petg")
    )
    assert draft is not None
    assert draft.extruder_temp == 200
    assert draft.bed_temp == 60
    assert "enrichment" not in draft.orcaslicer_settings
    assert draft.import_evidence["original"]["settings"] == profile["orcaslicer_settings"]

    analysis = await client.get(
        f"/api/v1/presets/{draft.id}/draft-analysis",
        headers=headers,
    )
    suggestions = analysis.json()["suggestions"]
    assert suggestions["extruder_temp"]["value"] == 200
    assert suggestions["extruder_temp"]["direct"] is True
    assert suggestions["bed_temp"]["value"] == 60
    assert suggestions["bed_temp"]["direct"] is True


@pytest.mark.asyncio
async def test_generic_vendor_stays_an_explicit_catalog_decision(
    client: AsyncClient, db_session: AsyncSession
):
    headers, _ = await _signed_in(client, db_session, "orca-generic-review")
    response = await _import(
        client,
        headers,
        _preset(
            "Generic PLA @System - Copy",
            orcaslicer_settings={
                "filament_vendor": ["Generic"],
                "filament_type": ["PLA"],
                "nozzle_temperature": ["215"],
                "hot_plate_temp": ["55"],
            },
        ),
    )
    draft_id = response.json()["results"][0]["fhub_id"]

    analysis = await client.get(
        f"/api/v1/presets/{draft_id}/draft-analysis",
        headers=headers,
    )

    assert analysis.status_code == 200
    review = analysis.json()
    assert review["generic_source"] is True
    assert "brand_name" not in review["suggestions"]
    assert "filament_name" not in review["suggestions"]
    assert review["catalog_decisions"][0] == "identify_brand"
    assert review["review_state"] == "ambiguous"


@pytest.mark.asyncio
async def test_old_draft_without_evidence_uses_its_stored_snapshot(
    client: AsyncClient, db_session: AsyncSession
):
    headers, person = await _signed_in(client, db_session, "orca-old-draft")
    draft = Preset(
        user_id=person.id,
        name="Old PETG profile",
        active=False,
        moderation_status=PresetModerationStatus.NOT_REQUIRED,
        extruder_temp=235,
        bed_temp=75,
        orcaslicer_settings={
            "filament_vendor": ["Old Vendor"],
            "filament_type": ["PETG"],
            "filament_colour": ["#8000FF"],
            "filament_diameter": ["1.75"],
            "filament_density": ["1.27"],
            "future_setting": ["preserve me"],
        },
    )
    db_session.add(draft)
    await db_session.flush()

    analysis = await client.get(
        f"/api/v1/presets/{draft.id}/draft-analysis",
        headers=headers,
    )

    assert analysis.status_code == 200
    review = analysis.json()
    assert review["evidence_kind"] == "stored_snapshot"
    for field, value in {
        "brand_name": "Old Vendor",
        "material_type": "PETG",
        "color_hex": "#8000FF",
        "diameter": 1.75,
        "density": 1.27,
    }.items():
        assert review["suggestions"][field] == {
            "value": value,
            "source": "stored_snapshot",
            "confidence": "suggested",
            "direct": False,
        }
    assert review["confirmed_fields"] == []
    assert review["catalog_decisions"] == [
        "confirm_new_brand",
        "confirm_material_type",
        "choose_or_create_filament",
    ]
    assert review["technical_settings_count"] == 6


@pytest.mark.asyncio
async def test_old_snapshot_match_requires_an_explicit_catalog_choice(
    client: AsyncClient, db_session: AsyncSession
):
    brand = Brand(name="Legacy Vendor", slug="legacy-vendor", verified=True, active=True)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="PETG Violet",
        slug="petg-violet",
        material_type="PETG",
        color_name="Violet",
        color_hex="#8000FF",
        diameter=1.75,
        active=True,
    )
    db_session.add(filament)
    await db_session.flush()
    headers, person = await _signed_in(client, db_session, "orca-old-match")
    draft = Preset(
        user_id=person.id,
        name="Legacy Vendor PETG Violet",
        extruder_temp=235,
        bed_temp=75,
        active=False,
        moderation_status=PresetModerationStatus.NOT_REQUIRED,
        orcaslicer_settings={
            "filament_vendor": ["Legacy Vendor"],
            "filament_type": ["PETG"],
            "filament_colour": ["#8000FF"],
            "filament_diameter": ["1.75"],
        },
    )
    db_session.add(draft)
    await db_session.flush()

    analysis = await client.get(
        f"/api/v1/presets/{draft.id}/draft-analysis",
        headers=headers,
    )

    assert analysis.status_code == 200
    review = analysis.json()
    assert review["evidence_kind"] == "stored_snapshot"
    assert review["filament_matches"][0]["id"] == filament.id
    assert review["filament_matches"][0]["confidence"] in {"exact", "strong"}
    assert "choose_catalog_filament" in review["catalog_decisions"]
    assert review["review_state"] != "ready"


@pytest.mark.asyncio
async def test_exact_catalog_product_is_proposed_without_creating_a_duplicate(
    client: AsyncClient, db_session: AsyncSession
):
    brand = Brand(name="eSUN", slug="esun", verified=True, active=True)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="PLA+ Fire Engine Red",
        slug="pla-fire-engine-red",
        material_type="PLA+",
        color_name="Fire Engine Red",
        color_hex="#D82727",
        diameter=1.75,
        active=True,
    )
    db_session.add(filament)
    await db_session.flush()
    headers, _ = await _signed_in(client, db_session, "orca-catalog-match")
    response = await _import(
        client,
        headers,
        _preset(
            "eSUN PLA+ Fire Engine Red @Voron",
            orcaslicer_settings={
                "filament_vendor": ["eSUN"],
                "filament_type": ["PLA+"],
                "filament_colour": ["#D82727"],
                "filament_diameter": ["1.75"],
                "nozzle_temperature": ["215"],
                "hot_plate_temp": ["55"],
            },
        ),
    )
    draft_id = response.json()["results"][0]["fhub_id"]

    analysis = await client.get(
        f"/api/v1/presets/{draft_id}/draft-analysis",
        headers=headers,
    )

    assert analysis.status_code == 200
    review = analysis.json()
    assert review["brand_match"]["id"] == brand.id
    for field in ("brand_name", "material_type", "color_hex", "diameter"):
        assert review["suggestions"][field]["source"] == "orca"
        assert review["suggestions"][field]["confidence"] == "high"
        assert review["suggestions"][field]["direct"] is True
    assert review["filament_matches"] == [{
        "id": filament.id,
        "name": filament.name,
        "brand_id": brand.id,
        "material_type": "PLA+",
        "color_name": "Fire Engine Red",
        "confidence": "exact",
        "reasons": ["product_name"],
    }]
    assert "choose_or_create_filament" not in review["catalog_decisions"]


@pytest.mark.asyncio
async def test_country_color_name_matches_the_same_global_filament(
    client: AsyncClient, db_session: AsyncSession
):
    brand = Brand(name="Local Colors", slug="local-colors", active=True)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Everyday PLA",
        slug="everyday-pla",
        material_type="PLA",
        color_name="Warm Beige",
        color_hex="#D7C3A5",
        diameter=1.75,
        active=True,
    )
    db_session.add(filament)
    await db_session.flush()
    db_session.add(FilamentCountryCell(
        filament_id=filament.id,
        country="KZ",
        market_color_name="Светлая берёза",
    ))
    await db_session.flush()
    headers, _ = await _signed_in(client, db_session, "orca-local-color-match")

    response = await _import(
        client,
        headers,
        _preset(
            "Local Colors Everyday PLA Светлая берёза @Voron",
            orcaslicer_settings={
                "filament_vendor": ["Local Colors"],
                "filament_type": ["PLA"],
                "filament_colour": ["#D7C3A5"],
                "nozzle_temperature": ["215"],
                "hot_plate_temp": ["55"],
            },
        ),
    )
    draft_id = response.json()["results"][0]["fhub_id"]

    analysis = await client.get(
        f"/api/v1/presets/{draft_id}/draft-analysis",
        headers=headers,
    )

    assert analysis.status_code == 200
    matches = analysis.json()["filament_matches"]
    assert matches[0]["id"] == filament.id
    assert matches[0]["confidence"] in {"exact", "strong"}
    assert "choose_or_create_filament" not in analysis.json()["catalog_decisions"]


@pytest.mark.asyncio
async def test_sending_the_same_preset_again_updates_it(
    client: AsyncClient, db_session: AsyncSession
):
    headers, _ = await _signed_in(client, db_session, "orca-import-again")

    first = await _import(client, headers, _preset("Repeat PLA"))
    second = await _import(client, headers, _preset("Repeat PLA", extruder_temp=225))

    assert first.json()["results"][0]["status"] == "created"
    assert second.json()["results"][0]["status"] != "created"

    presets = (
        await db_session.execute(
            select(Preset).where(Preset.external_id == "orca-repeat-pla")
        )
    ).scalars().all()
    assert len(presets) == 1
    await db_session.refresh(presets[0])
    assert presets[0].extruder_temp == 225


@pytest.mark.asyncio
async def test_stable_plugin_identity_turns_a_rename_into_an_update(
    client: AsyncClient, db_session: AsyncSession
):
    headers, person = await _signed_in(client, db_session, "orca-import-rename")
    stable_id = (
        "orca-local-v1:aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa:"
        "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    )
    original = _preset("PLA workshop", external_id=stable_id)
    renamed = _preset("PLA workshop tuned", external_id=stable_id, extruder_temp=218)

    first = await _import(client, headers, original)
    second = await _import(client, headers, renamed)

    assert first.json()["results"][0]["status"] == "created"
    assert second.json()["results"][0]["status"] == "updated"
    rows = list(
        await db_session.scalars(
            select(Preset).where(
                Preset.user_id == person.id,
                Preset.external_id == stable_id,
            )
        )
    )
    assert len(rows) == 1
    await db_session.refresh(rows[0])
    assert rows[0].name == "PLA workshop tuned"
    assert rows[0].extruder_temp == 218
    assert rows[0].import_evidence["original"]["name"] == "PLA workshop"
    assert rows[0].import_evidence["latest"]["name"] == "PLA workshop tuned"


@pytest.mark.asyncio
async def test_official_round_trip_is_immutable_and_a_change_becomes_a_personal_fork(
    client: AsyncClient, db_session: AsyncSession
):
    """Orca may return an Organization asset, but it never transfers ownership."""
    brand = Brand(name="Round Trip Vendor", slug="round-trip-vendor", active=True)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Round Trip PLA",
        slug="round-trip-pla",
        material_type="PLA",
        diameter=1.75,
        active=True,
    )
    db_session.add(filament)
    await db_session.flush()
    official = Preset(
        filament_id=filament.id,
        organization_id=None,
        user_id=None,
        name="Round Trip Quality",
        extruder_temp=215,
        bed_temp=60,
        active=True,
        is_official=True,
        moderation_status=PresetModerationStatus.APPROVED,
        orcaslicer_settings={
            "filament_type": ["PLA"],
            "nozzle_temperature": ["215"],
        },
    )
    db_session.add(official)
    await db_session.flush()
    from app.services.preset_publication import apply_managed_orca_identity

    apply_managed_orca_identity(official)
    await db_session.commit()

    headers, person = await _signed_in(client, db_session, "orca-official-fork")
    unchanged_payload = _preset(
        "Round Trip Quality @fh",
        external_id="orca-official-round-trip",
        fhub_id=official.id,
        filament_id=filament.id,
        extruder_temp=215,
        bed_temp=60,
        orcaslicer_settings={
            "filament_type": ["PLA"],
            "nozzle_temperature": ["215"],
            "fhub_id": official.id,
            "fhub_source": "filamenthub",
        },
    )
    unchanged = await _import(client, headers, unchanged_payload)
    assert unchanged.status_code == 200, unchanged.text
    assert unchanged.json()["results"][0]["status"] == "skipped", unchanged.text
    assert unchanged.json()["results"][0]["fhub_id"] == official.id
    assert await db_session.scalar(
        select(func.count()).select_from(Preset).where(Preset.user_id == person.id)
    ) == 0

    changed_payload = {
        **unchanged_payload,
        "extruder_temp": 225,
        "orcaslicer_settings": {
            **unchanged_payload["orcaslicer_settings"],
            "nozzle_temperature": ["225"],
        },
    }
    changed = await _import(client, headers, changed_payload)
    assert changed.status_code == 200, changed.text
    assert changed.json()["results"][0]["status"] == "created"

    fork = await db_session.scalar(
        select(Preset).where(
            Preset.user_id == person.id,
            Preset.derived_from_preset_id == official.id,
        )
    )
    assert fork is not None
    assert fork.is_official is False
    assert fork.organization_id is None
    assert fork.extruder_temp == 225
    await db_session.refresh(official)
    assert official.user_id is None
    assert official.is_official is True
    assert official.extruder_temp == 215


@pytest.mark.asyncio
async def test_a_draft_is_recognised_by_its_marker_after_orca_renumbers_it(
    client: AsyncClient, db_session: AsyncSession
):
    """OrcaSlicer's own identifiers have changed format more than once.

    The draft marker FilamentHub writes into the preset survives that, and
    finding a draft by it is one of the lookups that used to be unreachable
    from the tests. The preset is also renamed here on purpose: with the name
    unchanged the search by name would find it anyway and the marker would
    prove nothing.
    """
    headers, person = await _signed_in(client, db_session, "orca-import-marker")

    created = await _import(client, headers, _preset("Marker PLA"))
    assert created.json()["results"][0]["status"] == "created"
    marker = f"draft_{person.id}_orca-marker-pla"

    renumbered = _preset("Marker PLA, renamed by its owner")
    renumbered["external_id"] = "orca-brand-new-identifier"
    renumbered["orcaslicer_settings"] = {
        **renumbered["orcaslicer_settings"],
        "fhub_draft_id": marker,
    }
    again = await _import(client, headers, renumbered)

    assert again.json()["results"][0]["status"] != "created"
    total = await db_session.scalar(
        select(func.count()).select_from(Preset).where(Preset.user_id == person.id)
    )
    assert total == 1


@pytest.mark.asyncio
async def test_a_draft_already_promoted_is_left_alone(
    client: AsyncClient, db_session: AsyncSession
):
    """Once a draft becomes a published preset, re-sending the template must not undo it.

    The published preset remembers where it came from; that memory is the second
    of the lookups this file exists to cover.
    """
    headers, person = await _signed_in(client, db_session, "orca-import-promoted")

    promoted = Preset(
        name="Promoted PLA",
        user_id=person.id,
        extruder_temp=215,
        bed_temp=60,
        active=True,
        moderation_status=PresetModerationStatus.APPROVED,
        orcaslicer_settings={"derived_from_external_id": "orca-template-source"},
    )
    db_session.add(promoted)
    await db_session.commit()

    response = await _import(
        client, headers, _preset("Template PLA", external_id="orca-template-source")
    )

    result = response.json()["results"][0]
    assert result["status"] == "skipped"
    assert result["fhub_id"] == promoted.id

    total = await db_session.scalar(
        select(func.count()).select_from(Preset).where(Preset.user_id == person.id)
    )
    assert total == 1


@pytest.mark.asyncio
async def test_a_promoted_draft_is_recognised_by_its_draft_marker(
    client: AsyncClient, db_session: AsyncSession
):
    """The same protection when the template carries no identifier of its own."""
    headers, person = await _signed_in(client, db_session, "orca-import-promoted-marker")

    template = _preset("Nameless Template")
    template["external_id"] = None
    marker = f"draft_{person.id}_" + hashlib.md5(b"Nameless Template").hexdigest()[:8]

    # Published under its own name, as a promoted preset is: were it still
    # called what the template is called, the search by name would find it
    # first and this lookup would never be reached.
    promoted = Preset(
        name="Shop PLA, tuned",
        user_id=person.id,
        extruder_temp=215,
        bed_temp=60,
        active=True,
        moderation_status=PresetModerationStatus.APPROVED,
        orcaslicer_settings={"fhub_id": 999999, "fhub_source": "filamenthub"},
        import_evidence={"promotion_identity": {"draft_id": marker}},
    )
    db_session.add(promoted)
    await db_session.commit()

    response = await _import(client, headers, template)

    assert response.json()["results"][0]["status"] == "skipped"
    total = await db_session.scalar(
        select(func.count()).select_from(Preset).where(Preset.user_id == person.id)
    )
    assert total == 1


@pytest.mark.asyncio
async def test_one_batch_of_the_same_preset_leaves_one_row(
    client: AsyncClient, db_session: AsyncSession
):
    """A plugin that repeats itself within a single send must not multiply."""
    headers, person = await _signed_in(client, db_session, "orca-import-batch-dup")

    response = await _import(client, headers, *[_preset("Dup PLA") for _ in range(6)])

    assert response.status_code == 200
    statuses = [item["status"] for item in response.json()["results"]]
    assert statuses.count("created") == 1
    assert "error" not in statuses

    total = await db_session.scalar(
        select(func.count()).select_from(Preset).where(Preset.user_id == person.id)
    )
    assert total == 1


@pytest.mark.asyncio
async def test_demand_signal_hides_small_groups_and_counts_distinct_users(
    client: AsyncClient, db_session: AsyncSession
):
    first_headers, _ = await _signed_in(client, db_session, "demand-first")
    second_headers, _ = await _signed_in(client, db_session, "demand-second")
    third_headers, _ = await _signed_in(client, db_session, "demand-third")
    payload = _preset(
        "Shared Candidate PLA",
        orcaslicer_settings={
            "filament_vendor": ["Candidate Vendor"],
            "filament_type": ["PLA"],
            "filament_colour": ["#336699"],
        },
    )

    first = await _import(client, first_headers, payload)
    await _import(client, second_headers, payload)
    first_id = first.json()["results"][0]["fhub_id"]
    hidden = await client.get(
        f"/api/v1/presets/{first_id}/draft-analysis",
        headers=first_headers,
    )
    assert hidden.status_code == 200
    assert hidden.json()["similar_import_users"] == 0

    await _import(client, third_headers, payload)
    await _import(client, first_headers, payload)
    visible = await client.get(
        f"/api/v1/presets/{first_id}/draft-analysis",
        headers=first_headers,
    )
    assert visible.status_code == 200
    assert visible.json()["similar_import_users"] == 3


@pytest.mark.asyncio
async def test_one_bad_preset_does_not_cost_the_others(
    client: AsyncClient, db_session: AsyncSession
):
    """A name OrcaSlicer could never have saved is refused on its own."""
    headers, person = await _signed_in(client, db_session, "orca-import-mixed")

    response = await _import(
        client,
        headers,
        _preset("Good One"),
        _preset("Bad/Name*Here"),
        _preset("Good Two"),
    )

    assert response.status_code == 200
    statuses = [item["status"] for item in response.json()["results"]]
    assert statuses[0] == "created"
    assert statuses[1] == "error"
    assert statuses[2] == "created"

    total = await db_session.scalar(
        select(func.count()).select_from(Preset).where(Preset.user_id == person.id)
    )
    assert total == 2


@pytest.mark.asyncio
async def test_an_oversized_batch_is_refused_whole(
    client: AsyncClient, db_session: AsyncSession
):
    """Past the batch limit nothing is written at all, not the first fifty."""
    headers, person = await _signed_in(client, db_session, "orca-import-oversized")

    response = await _import(
        client, headers, *[_preset(f"Bulk {number}") for number in range(51)]
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "ERR_TOO_MANY_PROFILES"

    total = await db_session.scalar(
        select(func.count()).select_from(Preset).where(Preset.user_id == person.id)
    )
    assert total == 0


@pytest.mark.asyncio
async def test_import_can_be_switched_off_per_account(
    client: AsyncClient, db_session: AsyncSession
):
    headers, person = await _signed_in(client, db_session, "orca-import-disabled")
    person.allow_filament_presets_import = False
    await db_session.commit()

    response = await _import(client, headers, _preset("Refused PLA"))

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ERR_IMPORT_FILAMENT_DISABLED"


@pytest.mark.asyncio
async def test_plugin_header_counts_only_what_reaches_the_slicer(
    client: AsyncClient, db_session: AsyncSession
):
    """The plugin shows "presets N (M synced)" from this endpoint.

    A draft never leaves the site, so counting it as synchronised made the
    plugin's header disagree with the same library on the website.
    """
    headers, person = await _signed_in(client, db_session, "orca-stats-draft")

    imported = await _import(client, headers, _preset("Stats PLA"))
    assert imported.status_code == 200

    draft = await db_session.scalar(select(Preset).where(Preset.user_id == person.id))
    assert draft is not None and draft.active is False

    stats = await client.get("/api/v1/auth/me/presets-stats", headers=headers)
    assert stats.status_code == 200
    body = stats.json()
    # The draft belongs to the library and is shown there, but it synchronises
    # nowhere until it is bound to a filament.
    assert body["total_presets"] == 1
    assert body["synced_presets"] == 0

    listed = await client.get("/api/v1/auth/my-presets", headers=headers)
    assert [item["id"] for item in listed.json()["items"]] == []
