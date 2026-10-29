"""Curation cannot bypass source review, explicit identity or confirmation."""

from copy import deepcopy

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models import Brand, CatalogCurationProposal, CatalogImportBatch, Filament, Preset

pytestmark = pytest.mark.asyncio
BASE = "/api/v1/admin/catalog/curation/proposals"


def headers(user):
    return {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}


def proposal():
    draft = {
        "filename": "manufacturer.json",
        "brands": [{"brand_key": "maker", "mode": "create", "name": "Maker"}],
        "filaments": [
            {
                "filament_key": "maker:pla:black",
                "brand_key": "maker",
                "mode": "create",
                "name": "PLA Black",
                "material_type": "PLA",
                "color_name": "Black",
                "diameter": 1.75,
                "availability": "available",
            },
            {"filament_key": "maker:unknown", "enabled": False},
        ],
    }
    evidence = [
        {
            "sheet": sheet,
            "key": key,
            "field": field,
            "kind": "direct",
            "source_urls": ["https://maker.example/products/pla"],
        }
        for sheet, key, fields in (
            ("Brands", "maker", ["name"]),
            (
                "Filaments",
                "maker:pla:black",
                ["name", "material_type", "color_name", "diameter", "availability"],
            ),
        )
        for field in fields
    ]
    source_facts = [
        {
            "filament_key": "maker:pla:black",
            "property_name": field,
            "value_summary": f"Manufacturer specifies {field}",
            "source_urls": ["https://maker.example/products/pla"],
            "disposition": "mapped",
            "mapped_fields": [field],
        }
        for field in ("name", "material_type", "color_name", "diameter", "availability")
    ]
    return {
        "title": "Maker materials",
        "draft": draft,
        "evidence": evidence,
        "unmapped_facts": [],
        "source_facts": source_facts,
        "coverage_note": "Black PLA page reviewed; unknown variant excluded.",
    }


async def test_admin_review_partial_apply_preserves_audit_and_freezes_proposal(
    client: AsyncClient, db_session: AsyncSession, admin_user, auth_user
):
    payload = proposal()
    payload["draft"]["presets"] = [
        {
            "preset_key": "maker:pla:black:generic",
            "filament_key": "maker:pla:black",
            "mode": "create",
            "name": "Maker PLA",
            "extruder_temp": 215,
            "bed_temp": 60,
        }
    ]
    payload["evidence"].extend(
        {
            "sheet": "Presets",
            "key": "maker:pla:black:generic",
            "field": field,
            "kind": "direct",
            "source_urls": ["https://maker.example/products/pla"],
        }
        for field in ("name", "extruder_temp", "bed_temp")
    )
    assert (await client.post(BASE, json=payload)).status_code == 401
    assert (await client.post(BASE, json=payload, headers=headers(auth_user))).status_code == 403
    response = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert response.status_code == 201, response.text
    saved = response.json()
    path = f"{BASE}/{saved['id']}"
    assert saved["revision"] == 1
    assert await db_session.scalar(select(func.count()).select_from(Filament)) == 0
    assert (await client.get(path, headers=headers(auth_user))).status_code == 403
    listed = await client.get(BASE, params={"size": 1}, headers=headers(admin_user))
    assert listed.json()["total"] == 1
    assert "draft" not in listed.json()["items"][0]

    preview = await client.post(
        path + "/preview", json={"revision": 1}, headers=headers(admin_user)
    )
    assert preview.status_code == 200, preview.text
    review = preview.json()
    assert review["summary"]["error"] == 0, review["rows"]
    assert review["summary"]["skipped"] == 1
    assert await db_session.scalar(select(func.count()).select_from(Brand)) == 0
    result = await client.post(
        path + "/apply",
        headers=headers(admin_user),
        json={
            "revision": 1,
            "confirmation_token": review["confirmation_token"],
        },
    )
    assert result.status_code == 200, result.text
    assert await db_session.scalar(select(func.count()).select_from(Filament)) == 1
    batch = await db_session.get(CatalogImportBatch, result.json()["batch_id"])
    assert batch.plan_snapshot["curation"]["proposal_id"] == saved["id"]
    assert batch.plan_snapshot["curation"]["evidence"] == saved["evidence"]
    assert batch.plan_snapshot["curation"]["coverage_note"] == payload["coverage_note"]
    targets = {
        (row["sheet"], row["key"]): row["target_id"]
        for row in batch.plan_snapshot["rows"]
        if row["status"] != "skipped"
    }
    brand = await db_session.scalar(select(Brand))
    filament = await db_session.scalar(select(Filament))
    preset = await db_session.scalar(select(Preset))
    assert targets == {
        ("Brands", "maker"): brand.id,
        ("Filaments", "maker:pla:black"): filament.id,
        ("Presets", "maker:pla:black:generic"): preset.id,
    }
    applied = (await client.get(path, headers=headers(admin_user))).json()
    assert applied["status"] == "applied"
    assert applied["applied_batch_id"] == batch.id
    assert (
        await client.patch(
            path, json={"revision": 1, "title": "Changed"}, headers=headers(admin_user)
        )
    ).status_code == 409
    assert (
        await client.post(
            path + "/apply",
            json={"revision": 1, "confirmation_token": review["confirmation_token"]},
            headers=headers(admin_user),
        )
    ).status_code == 409
    assert await db_session.scalar(select(func.count()).select_from(CatalogImportBatch)) == 1


async def test_edit_invalidates_preview_and_confirmation_is_bound_to_proposal(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    admin = headers(admin_user)
    one = (await client.post(BASE, json=proposal(), headers=admin)).json()
    two = (await client.post(BASE, json=proposal(), headers=admin)).json()
    first = f"{BASE}/{one['id']}"
    second = f"{BASE}/{two['id']}"
    preview = (await client.post(first + "/preview", json={"revision": 1}, headers=admin)).json()
    token = preview["confirmation_token"]
    wrong = await client.post(
        second + "/apply", json={"revision": 1, "confirmation_token": token}, headers=admin
    )
    assert wrong.status_code == 409
    edited = await client.patch(
        first, json={"revision": 1, "coverage_note": "Reviewed again"}, headers=admin
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["revision"] == 2
    assert (
        await client.patch(first, json={"revision": 1, "title": "Lost update"}, headers=admin)
    ).status_code == 409
    assert (
        await client.post(first + "/preview", json={"revision": 1}, headers=admin)
    ).status_code == 409
    stale = await client.post(
        first + "/apply", json={"revision": 2, "confirmation_token": token}, headers=admin
    )
    assert stale.status_code == 409
    assert await db_session.scalar(select(func.count()).select_from(CatalogImportBatch)) == 0


async def test_unmapped_facts_are_editable_digest_bound_and_preserved_in_apply_audit(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    admin = headers(admin_user)
    payload = proposal()
    payload["unmapped_facts"] = [
        {
            "filament_key": "maker:pla:black",
            "property_name": "Chemical resistance",
            "value_summary": "Resistant to weak acids",
            "explanation": "The manufacturer describes this on the material page.",
            "source_urls": ["https://maker.example/products/pla"],
        }
    ]
    created = await client.post(BASE, json=payload, headers=admin)
    assert created.status_code == 201, created.text
    path = f"{BASE}/{created.json()['id']}"
    loaded = await client.get(path, headers=admin)
    stored_fact = {
        **payload["unmapped_facts"][0],
        "public_action": "none",
        "kind": None,
        "quote": None,
        "unit": None,
        "conditions": None,
        "subject": None,
        "image_url": None,
    }
    assert loaded.json()["unmapped_facts"] == [stored_fact]

    before = await client.post(path + "/preview", json={"revision": 1}, headers=admin)
    assert before.status_code == 200, before.text
    token = before.json()["confirmation_token"]
    edited_notes = [
        {
            **payload["unmapped_facts"][0],
            "value_summary": "Resistant to weak acids and alkalis",
        }
    ]
    edited = await client.patch(
        path,
        json={"revision": 1, "unmapped_facts": edited_notes},
        headers=admin,
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["revision"] == 2
    after = await client.post(path + "/preview", json={"revision": 2}, headers=admin)
    assert after.status_code == 200, after.text
    expected_edited_notes = [
        {
            **edited_notes[0],
            "public_action": "none",
            "kind": None,
            "quote": None,
            "unit": None,
            "conditions": None,
            "subject": None,
            "image_url": None,
        }
    ]
    assert after.json()["unmapped_facts"] == expected_edited_notes
    stale_apply = await client.post(
        path + "/apply",
        headers=admin,
        json={"revision": 2, "confirmation_token": token},
    )
    assert stale_apply.status_code == 409
    result = await client.post(
        path + "/apply",
        headers=admin,
        json={"revision": 2, "confirmation_token": after.json()["confirmation_token"]},
    )
    assert result.status_code == 200, result.text
    batch = await db_session.get(CatalogImportBatch, result.json()["batch_id"])
    assert batch.plan_snapshot["curation"]["unmapped_facts"] == edited_notes
    assert await db_session.scalar(select(func.count()).select_from(Filament)) == 1


async def test_public_additional_properties_apply_per_exact_filament_and_serialize(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    admin = headers(admin_user)
    payload = proposal()
    payload["draft"]["filaments"].append(
        {"filament_key": "maker:disabled", "enabled": False}
    )
    payload["unmapped_facts"] = [
        {
            "filament_key": "maker:pla:black",
            "property_name": "Chemical resistance",
            "value_summary": "Resists weak acids",
            "source_urls": ["https://maker.example/products/pla"],
            "public_action": "publish",
            "kind": "direct",
        },
        {
            "filament_key": "maker:pla:black",
            "property_name": "Surface texture",
            "value_summary": "Silk-like finish",
            "source_urls": ["https://maker.example/products/pla"],
            "public_action": "publish",
            "kind": "inferred",
            "explanation": "The manufacturer describes the filament as silk PLA.",
        },
        {
            "filament_key": "maker:pla:black",
            "property_name": "Private note",
            "value_summary": "Not approved for publication",
            "source_urls": ["https://maker.example/products/pla"],
        },
        {
            "filament_key": "maker:disabled",
            "property_name": "Skipped material property",
            "value_summary": "Must not be applied",
            "source_urls": ["https://maker.example/products/pla"],
            "public_action": "publish",
            "kind": "direct",
        },
    ]

    async def apply_proposal(data: dict) -> None:
        created = await client.post(BASE, json=data, headers=admin)
        assert created.status_code == 201, created.text
        path = f"{BASE}/{created.json()['id']}"
        preview = await client.post(path + "/preview", json={"revision": 1}, headers=admin)
        assert preview.status_code == 200, preview.text
        applied = await client.post(
            path + "/apply",
            json={"revision": 1, "confirmation_token": preview.json()["confirmation_token"]},
            headers=admin,
        )
        assert applied.status_code == 200, applied.text

    await apply_proposal(payload)
    filament = await db_session.scalar(select(Filament))
    assert filament is not None
    public = await client.get(f"/api/v1/filaments/{filament.id}")
    assert public.status_code == 200, public.text
    properties = public.json()["additional_properties"]
    assert [item["property_name"] for item in properties] == [
        "Chemical resistance",
        "Surface texture",
    ]
    assert properties[0]["kind"] == "direct"
    assert "explanation" not in properties[1]
    assert all(item["source_urls"] for item in properties)

    update_payload = proposal()
    update_payload["draft"]["brands"][0].update(
        mode="update", existing_brand=str(filament.brand_id)
    )
    update_payload["draft"]["filaments"][0].update(
        mode="update", existing_filament=str(filament.id)
    )
    update_payload["unmapped_facts"] = [
        {
            "filament_key": "maker:pla:black",
            "property_name": "chemical RESISTANCE",
            "value_summary": "Resists weak acids and alkalis",
            "source_urls": ["https://maker.example/products/pla"],
            "public_action": "remove",
        },
        {
            "filament_key": "maker:pla:black",
            "property_name": "SURFACE TEXTURE",
            "value_summary": "Silk-like finish with revised description",
            "source_urls": ["https://maker.example/products/pla"],
            "public_action": "publish",
            "kind": "inferred",
            "explanation": "Updated manufacturer description remains tied to this material.",
        },
    ]
    await apply_proposal(update_payload)
    refreshed = await client.get(f"/api/v1/filaments/{filament.id}")
    assert refreshed.status_code == 200, refreshed.text
    updated_properties = refreshed.json()["additional_properties"]
    assert len(updated_properties) == 1
    assert updated_properties[0]["property_name"] == "SURFACE TEXTURE"
    assert updated_properties[0]["value_summary"].startswith("Silk-like finish with revised")


async def test_public_additional_property_requires_evidence_kind_and_inference_explanation(
    client: AsyncClient, admin_user
):
    payload = proposal()
    fact = {
        "filament_key": "maker:pla:black",
        "property_name": "Chemical resistance",
        "value_summary": "Resists weak acids",
        "source_urls": ["https://maker.example/products/pla"],
        "public_action": "publish",
    }
    payload["unmapped_facts"] = [fact]
    missing_kind = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert missing_kind.status_code == 422

    payload["unmapped_facts"] = [{**fact, "kind": "inferred"}]
    missing_explanation = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert missing_explanation.status_code == 422


@pytest.mark.parametrize(
    "fact,match",
    [
        ({"filament_key": "maker:missing"}, "proposed filament row"),
        ({"source_urls": ["javascript:alert(1)"]}, "valid URL"),
        ({"source_urls": ["https://user:secret@maker.example/material"]}, "credentials"),
        ({"source_urls": []}, "at least 1 item"),
    ],
)
async def test_unmapped_fact_rejects_orphan_rows_and_invalid_sources(
    client: AsyncClient, admin_user, fact, match
):
    payload = proposal()
    item = {
        "filament_key": "maker:pla:black",
        "property_name": "Chemical resistance",
        "value_summary": "Resistant to weak acids",
        "source_urls": ["https://maker.example/products/pla"],
    }
    item.update(fact)
    payload["unmapped_facts"] = [item]
    response = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert response.status_code == 422, response.text


async def test_unmapped_facts_require_unique_property_per_material(client: AsyncClient, admin_user):
    payload = proposal()
    fact = {
        "filament_key": "maker:pla:black",
        "property_name": "Chemical resistance",
        "value_summary": "Resistant to weak acids",
        "source_urls": ["https://maker.example/products/pla"],
    }
    payload["unmapped_facts"] = [fact, {**fact, "value_summary": "Same property"}]
    response = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert response.status_code == 422, response.text


async def test_source_fact_contract_requires_evidence_mapping_and_unsupported_link(
    client: AsyncClient, admin_user
):
    payload = proposal()
    payload["source_facts"] = [
        {
            "filament_key": "maker:pla:black",
            "property_name": "Nozzle temperature range",
            "value_summary": "200–220 C",
            "source_urls": ["https://maker.example/products/pla"],
            "disposition": "mapped",
            "mapped_fields": ["recommended_nozzle_temp_min", "recommended_nozzle_temp_max"],
        }
    ]
    response = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert response.status_code == 422
    assert "proposed value" in response.text

    payload["draft"]["filaments"][0].update(
        recommended_nozzle_temp_min=200,
        recommended_nozzle_temp_max=220,
    )
    response = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert response.status_code == 422
    assert "field evidence" in response.text

    payload["evidence"].extend(
        {
            "sheet": "Filaments",
            "key": "maker:pla:black",
            "field": field,
            "kind": "direct",
            "source_urls": ["https://maker.example/products/pla"],
        }
        for field in ("recommended_nozzle_temp_min", "recommended_nozzle_temp_max")
    )
    payload["source_facts"] = [
        {
            **payload["source_facts"][0],
            "disposition": "unsupported",
            "mapped_fields": [],
        }
    ]
    response = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert response.status_code == 422
    assert "matching unmapped fact" in response.text


async def test_source_facts_require_distinct_property_and_known_filament_rows(
    client: AsyncClient, admin_user
):
    payload = proposal()
    fact = payload["source_facts"][0]
    payload["source_facts"] = [fact, {**fact, "value_summary": "Second summary"}]
    duplicate = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert duplicate.status_code == 422

    payload["source_facts"] = [{**fact, "filament_key": "maker:missing"}]
    orphan = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert orphan.status_code == 422


async def test_source_fact_urls_must_be_http_credential_free_and_bounded(
    client: AsyncClient, admin_user
):
    for urls in (
        ["javascript:alert(1)"],
        ["https://user:secret@maker.example/product"],
        [],
        [f"https://maker.example/{index}" for index in range(11)],
    ):
        payload = proposal()
        payload["source_facts"][0]["source_urls"] = urls
        response = await client.post(BASE, json=payload, headers=headers(admin_user))
        assert response.status_code == 422, response.text


async def test_unsupported_source_facts_count_toward_accounted_coverage(
    client: AsyncClient, admin_user
):
    payload = proposal()
    payload["source_facts"] = [
        {
            "filament_key": "maker:pla:black",
            "property_name": "Product identity",
            "value_summary": "PLA Black is the product name, PLA composition, and Black color",
            "source_urls": ["https://maker.example/products/pla"],
            "disposition": "mapped",
            "mapped_fields": ["name", "material_type", "color_name"],
        },
        {
            "filament_key": "maker:pla:black",
            "property_name": "Diameter",
            "value_summary": "1.75 mm",
            "source_urls": ["https://maker.example/products/pla"],
            "disposition": "mapped",
            "mapped_fields": ["diameter"],
        },
        {
            "filament_key": "maker:pla:black",
            "property_name": "Availability",
            "value_summary": "Available",
            "source_urls": ["https://maker.example/products/pla"],
            "disposition": "mapped",
            "mapped_fields": ["availability"],
        },
        {
            "filament_key": "maker:pla:black",
            "property_name": "Chemical resistance",
            "value_summary": "Resistant to weak acids",
            "source_urls": ["https://maker.example/products/pla"],
            "disposition": "unsupported",
            "mapped_fields": [],
        },
    ]
    payload["unmapped_facts"] = [
        {
            "filament_key": "maker:pla:black",
            "property_name": "Chemical resistance",
            "value_summary": "Resistant to weak acids",
            "source_urls": ["https://maker.example/products/pla"],
        }
    ]
    created = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert created.status_code == 201, created.text
    path = f"{BASE}/{created.json()['id']}"
    preview = await client.post(
        path + "/preview", json={"revision": 1}, headers=headers(admin_user)
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["summary"]["error"] == 0
    assert preview.json()["confirmation_token"]
    review = preview.json()["source_facts_review"]
    assert review == [
        {
            "filament_key": "maker:pla:black",
            "total": 4,
            "mapped": 3,
            "unsupported": 1,
            "unresolved": 0,
            "captured": 4,
            "coverage_percent": 100,
        }
    ]


async def test_source_fact_ranges_count_once_and_unresolved_blocks_row(
    client: AsyncClient, admin_user
):
    payload = proposal()
    row = payload["draft"]["filaments"][0]
    row.update(recommended_nozzle_temp_min=200, recommended_nozzle_temp_max=220)
    payload["evidence"].extend(
        {
            "sheet": "Filaments",
            "key": row["filament_key"],
            "field": field,
            "kind": "direct",
            "source_urls": ["https://maker.example/products/pla"],
        }
        for field in ("recommended_nozzle_temp_min", "recommended_nozzle_temp_max")
    )
    payload["source_facts"] = [
        {
            "filament_key": row["filament_key"],
            "property_name": f"Mapped property {index}",
            "value_summary": f"Value {index}",
            "source_urls": ["https://maker.example/products/pla"],
            "disposition": "mapped",
            "mapped_fields": fields,
        }
        for index, fields in enumerate(
            (["name"], ["material_type"], ["recommended_nozzle_temp_min", "recommended_nozzle_temp_max"])
        )
    ]
    payload["source_facts"].append(
        {
            "filament_key": row["filament_key"],
            "property_name": "Unresolved property",
            "value_summary": "A clear source value without a catalog mapping",
            "source_urls": ["https://maker.example/products/pla"],
            "disposition": "unresolved",
            "mapped_fields": [],
        }
    )
    created = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert created.status_code == 201, created.text
    path = f"{BASE}/{created.json()['id']}"
    preview = await client.post(
        path + "/preview", json={"revision": 1}, headers=headers(admin_user)
    )
    assert preview.status_code == 200, preview.text
    row_result = next(
        item for item in preview.json()["rows"] if item["key"] == row["filament_key"]
    )
    assert row_result["status"] == "error"
    assert "3/4" in row_result["message"]
    assert "at least 80%" in row_result["message"]
    assert "unresolved manufacturer source fact" in row_result["message"]
    assert preview.json()["source_facts_review"] == [
        {
            "filament_key": row["filament_key"],
            "total": 4,
            "mapped": 3,
            "unsupported": 0,
            "unresolved": 1,
            "captured": 3,
            "coverage_percent": 75,
        }
    ]


async def test_fact_review_allows_selective_apply_and_invalidates_old_confirmation(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    auth = headers(admin_user)
    payload = proposal()
    blue_key = "maker:pla:blue"
    blue_row = {
        **payload["draft"]["filaments"][0],
        "filament_key": blue_key,
        "name": "PLA Blue",
        "color_name": "Blue",
    }
    payload["draft"]["filaments"].append(blue_row)
    blue_evidence = [
        {
            **item,
            "key": blue_key,
        }
        for item in payload["evidence"]
        if item["sheet"] == "Filaments" and item["key"] == "maker:pla:black"
    ]
    payload["evidence"].extend(blue_evidence)
    payload["source_facts"].extend(
        {**fact, "filament_key": blue_key, "property_name": "Blue " + fact["property_name"]}
        for fact in list(payload["source_facts"])
    )
    created = await client.post(BASE, json=payload, headers=auth)
    assert created.status_code == 201, created.text
    path = f"{BASE}/{created.json()['id']}"
    initial = await client.post(
        path + "/preview", json={"revision": 1}, headers=auth
    )
    assert initial.status_code == 200, initial.text
    old_token = initial.json()["confirmation_token"]
    assert old_token

    source_facts = [
        fact
        for fact in payload["source_facts"]
        if fact["filament_key"] == blue_key
    ]
    omitted = await client.patch(
        path,
        json={"revision": 1, "source_facts": source_facts},
        headers=auth,
    )
    assert omitted.status_code == 200, omitted.text
    partial = await client.post(
        path + "/preview", json={"revision": 2}, headers=auth
    )
    assert partial.status_code == 200, partial.text
    black_review = next(
        item for item in partial.json()["rows"] if item["key"] == "maker:pla:black"
    )
    blue_review = next(item for item in partial.json()["rows"] if item["key"] == blue_key)
    assert black_review["status"] == "error"
    assert blue_review["status"] != "error"
    assert partial.json()["confirmation_token"] is None

    updated_draft = omitted.json()["draft"]
    black = next(row for row in updated_draft["filaments"] if row["filament_key"] == "maker:pla:black")
    black["enabled"] = False
    disabled = await client.patch(
        path,
        json={"revision": 2, "draft": updated_draft},
        headers=auth,
    )
    assert disabled.status_code == 200, disabled.text
    final = await client.post(
        path + "/preview", json={"revision": 3}, headers=auth
    )
    assert final.status_code == 200, final.text
    assert final.json()["summary"]["error"] == 0
    assert final.json()["confirmation_token"]
    stale = await client.post(
        path + "/apply",
        json={"revision": 3, "confirmation_token": old_token},
        headers=auth,
    )
    assert stale.status_code == 409
    applied = await client.post(
        path + "/apply",
        json={"revision": 3, "confirmation_token": final.json()["confirmation_token"]},
        headers=auth,
    )
    assert applied.status_code == 200, applied.text
    batch = await db_session.get(CatalogImportBatch, applied.json()["batch_id"])
    filament_rows = {
        row["key"]: row["status"]
        for row in batch.plan_snapshot["rows"]
        if row["sheet"] == "Filaments"
    }
    assert filament_rows["maker:pla:black"] == "skipped"
    assert filament_rows[blue_key] not in {"skipped", "error"}


async def test_update_fact_review_requires_accounted_and_resolved_source_facts(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    auth = headers(admin_user)
    brand = Brand(name="Maker", slug="maker", active=True, verified=False)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Old PLA Black",
        material_type="PLA",
        slug="old-pla-black",
        color_name="Black",
        diameter=1.75,
    )
    db_session.add(filament)
    await db_session.commit()

    payload = proposal()
    mapped_facts = payload["source_facts"]
    payload["source_facts"] = []
    payload["draft"]["brands"][0].update(mode="update", existing_brand=str(brand.id))
    payload["draft"]["filaments"][0].update(
        mode="update", existing_filament=str(filament.id), overwrite=True
    )
    created = await client.post(BASE, json=payload, headers=auth)
    assert created.status_code == 201, created.text
    path = f"{BASE}/{created.json()['id']}"

    missing = await client.post(path + "/preview", json={"revision": 1}, headers=auth)
    assert missing.status_code == 200, missing.text
    assert missing.json()["source_facts_review"][0]["total"] == 0
    assert missing.json()["summary"]["error"] > 0
    assert missing.json()["confirmation_token"] is None

    unresolved = {
        "filament_key": "maker:pla:black",
        "property_name": "Unknown manufacturer property",
        "value_summary": "Unresolved meaning",
        "source_urls": ["https://maker.example/products/pla"],
        "disposition": "unresolved",
        "mapped_fields": [],
    }
    edited = await client.patch(
        path,
        json={"revision": 1, "source_facts": [*mapped_facts, unresolved]},
        headers=auth,
    )
    assert edited.status_code == 200, edited.text
    blocked = await client.post(path + "/preview", json={"revision": 2}, headers=auth)
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["source_facts_review"][0]["coverage_percent"] == 83
    assert blocked.json()["source_facts_review"][0]["unresolved"] == 1
    assert blocked.json()["summary"]["error"] > 0
    assert blocked.json()["confirmation_token"] is None

    note = {
        "filament_key": "maker:pla:black",
        "property_name": unresolved["property_name"],
        "value_summary": unresolved["value_summary"],
        "source_urls": unresolved["source_urls"],
        "explanation": "Manufacturer property has no matching card field.",
    }
    edited = await client.patch(
        path,
        json={
            "revision": 2,
            "source_facts": [*mapped_facts, {**unresolved, "disposition": "unsupported"}],
            "unmapped_facts": [note],
        },
        headers=auth,
    )
    assert edited.status_code == 200, edited.text
    ready = await client.post(path + "/preview", json={"revision": 3}, headers=auth)
    assert ready.status_code == 200, ready.text
    assert ready.json()["source_facts_review"][0] == {
        "filament_key": "maker:pla:black",
        "total": 6,
        "mapped": 5,
        "unsupported": 1,
        "unresolved": 0,
        "captured": 6,
        "coverage_percent": 100,
    }
    assert ready.json()["summary"]["error"] == 0, ready.text
    assert ready.json()["confirmation_token"]


async def test_missing_evidence_and_implicit_matching_cannot_be_confirmed(
    client: AsyncClient, admin_user
):
    payload = proposal()
    payload["evidence"] = []
    payload["source_facts"] = []
    payload["draft"]["filaments"][0]["mode"] = "auto"
    created = await client.post(BASE, json=payload, headers=headers(admin_user))
    path = f"{BASE}/{created.json()['id']}"
    preview = await client.post(
        path + "/preview", json={"revision": 1}, headers=headers(admin_user)
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["confirmation_token"] is None
    assert preview.json()["summary"]["error"] == 2
    assert any(
        "explicit create or update" in (row["message"] or "") for row in preview.json()["rows"]
    )


@pytest.mark.parametrize("issue", ["omitted", "empty"])
async def test_create_without_availability_defaults_to_available(
    client: AsyncClient, db_session: AsyncSession, admin_user, issue
):
    payload = proposal()
    if issue == "omitted":
        payload["draft"]["filaments"][0].pop("availability")
    else:
        payload["draft"]["filaments"][0]["availability"] = ""
    payload["evidence"] = [item for item in payload["evidence"] if item["field"] != "availability"]
    payload["source_facts"] = [
        fact for fact in payload["source_facts"] if "availability" not in fact["mapped_fields"]
    ]
    created = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert created.status_code == 201, created.text
    path = f"{BASE}/{created.json()['id']}"
    preview = await client.post(
        path + "/preview", json={"revision": 1}, headers=headers(admin_user)
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["summary"]["error"] == 0, preview.json()["rows"]
    applied = await client.post(
        path + "/apply",
        json={"revision": 1, "confirmation_token": preview.json()["confirmation_token"]},
        headers=headers(admin_user),
    )
    assert applied.status_code == 200, applied.text
    filament = await db_session.scalar(select(Filament))
    assert filament.availability == "available"


@pytest.mark.parametrize("field", ["diameter"])
@pytest.mark.parametrize("issue", ["omitted", "blank", "unproven"])
async def test_create_requires_explicit_evidenced_diameter(
    client: AsyncClient, db_session: AsyncSession, admin_user, field, issue
):
    payload = proposal()
    if issue == "omitted":
        payload["draft"]["filaments"][0].pop(field)
    elif issue == "blank":
        payload["draft"]["filaments"][0][field] = "  "
    payload["evidence"] = [item for item in payload["evidence"] if item["field"] != field]
    payload["source_facts"] = [
        fact for fact in payload["source_facts"] if field not in fact["mapped_fields"]
    ]
    created = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert created.status_code == 201, created.text
    path = f"{BASE}/{created.json()['id']}"
    preview = await client.post(
        path + "/preview", json={"revision": 1}, headers=headers(admin_user)
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["confirmation_token"] is None
    assert preview.json()["summary"]["error"] == 1
    row = next(row for row in preview.json()["rows"] if row["key"] == "maker:pla:black")
    assert field in row["message"]
    assert await db_session.scalar(select(func.count()).select_from(Filament)) == 0


async def test_curation_keeps_planner_error_when_evidence_is_also_missing(
    client: AsyncClient, admin_user
):
    payload = proposal()
    payload["draft"]["filaments"][0]["diameter"] = -1
    payload["evidence"] = []
    payload["source_facts"] = []
    created = await client.post(BASE, json=payload, headers=headers(admin_user))
    preview = await client.post(
        f"{BASE}/{created.json()['id']}/preview", json={"revision": 1}, headers=headers(admin_user)
    )
    assert preview.status_code == 200, preview.text
    row = next(row for row in preview.json()["rows"] if row["key"] == "maker:pla:black")
    assert "greater than" in row["message"]
    assert "Missing evidence for:" in row["message"]
    assert preview.json()["confirmation_token"] is None


@pytest.mark.parametrize(
    "existing_visual", ["new", "complete", "clear_effects", "partial", "missing"]
)
async def test_visual_facts_are_complete_or_preserved_during_curation(
    client: AsyncClient, db_session: AsyncSession, admin_user, existing_visual
):
    payload = proposal()
    previous = {
        "color_type": "two",
        "colors": ["#000000", "#FF0000"],
        "finish": "glossy",
        "effects": ["glitter"],
        "transparency": True,
        "filler": "glitter",
    }
    filament = None
    if existing_visual != "new":
        brand = Brand(name="Maker", slug="maker", active=True, verified=False)
        db_session.add(brand)
        await db_session.flush()
        filament = Filament(
            brand_id=brand.id,
            name="PLA Black",
            material_type="PLA",
            slug="pla-black",
            color_name="Black",
            diameter=1.75,
            visual_settings=(
                previous
                if existing_visual in {"complete", "clear_effects"}
                else ({"colors": previous["colors"]} if existing_visual == "partial" else None)
            ),
            additives=[{"code": "carbon_fiber"}],
            property_claims=[{"code": "heat_resistant"}],
            bed_adhesives=["pva"],
            post_processing_chemicals=[{"name": "Water"}],
            price_display_unit="per_spool",
        )
        db_session.add(filament)
        await db_session.commit()
        payload["draft"]["brands"][0].update(mode="update", existing_brand=str(brand.id))
        payload["draft"]["filaments"][0].update(
            mode="update", existing_filament=str(filament.id), overwrite=True
        )
    row = payload["draft"]["filaments"][0]
    row["finish"] = "matte"
    payload["evidence"].append(
        {
            "sheet": "Filaments",
            "key": row["filament_key"],
            "field": "finish",
            "kind": "direct",
            "source_urls": ["https://maker.example/products/pla"],
        }
    )
    if existing_visual == "clear_effects":
        row["effects"] = []
        payload["evidence"].append(
            {
                "sheet": "Filaments",
                "key": row["filament_key"],
                "field": "effects",
                "kind": "direct",
                "source_urls": ["https://maker.example/products/pla"],
            }
        )
    created = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert created.status_code == 201, created.text
    path = f"{BASE}/{created.json()['id']}"
    revision = 1
    preview = await client.post(
        path + "/preview", json={"revision": revision}, headers=headers(admin_user)
    )
    assert preview.status_code == 200, preview.text
    if existing_visual not in {"complete", "clear_effects"}:
        assert preview.json()["confirmation_token"] is None
        invalid = next(
            item for item in preview.json()["rows"] if item["key"] == row["filament_key"]
        )
        assert "Visual settings require explicit values for:" in invalid["message"]
        assert "transparency" in invalid["message"]
        assert await db_session.scalar(select(func.count()).select_from(CatalogImportBatch)) == 0
        row.update(
            {
                field: previous[field]
                for field in ("color_type", "colors", "effects", "transparency")
            }
        )
        payload["evidence"].extend(
            {
                "sheet": "Filaments",
                "key": row["filament_key"],
                "field": field,
                "kind": "direct",
                "source_urls": ["https://maker.example/products/pla"],
            }
            for field in ("color_type", "colors", "effects", "transparency")
        )
        edited = await client.patch(
            path,
            json={"revision": 1, "draft": payload["draft"], "evidence": payload["evidence"]},
            headers=headers(admin_user),
        )
        assert edited.status_code == 200, edited.text
        revision = 2
        preview = await client.post(
            path + "/preview", json={"revision": revision}, headers=headers(admin_user)
        )
    assert preview.json()["summary"]["error"] == 0, preview.text
    applied = await client.post(
        path + "/apply",
        json={"revision": revision, "confirmation_token": preview.json()["confirmation_token"]},
        headers=headers(admin_user),
    )
    assert applied.status_code == 200, applied.text
    saved = await db_session.scalar(select(Filament))
    await db_session.refresh(saved)
    expected_visual = {**previous, "finish": "matte"}
    if existing_visual == "clear_effects":
        expected_visual.update(effects=[], filler="none")
    assert saved.visual_settings == expected_visual
    if filament is not None:
        assert saved.additives == [{"code": "carbon_fiber"}]
        assert saved.property_claims == [{"code": "heat_resistant"}]
        assert saved.bed_adhesives == ["pva"]
        assert saved.post_processing_chemicals == [{"name": "Water"}]
        assert saved.price_display_unit == "per_spool"


@pytest.mark.parametrize("overwrite", [False, True])
async def test_preset_patch_preserves_unproposed_settings(
    client: AsyncClient, db_session: AsyncSession, admin_user, overwrite
):
    brand = Brand(name="Maker", slug="maker", active=True, verified=False)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="PLA Black",
        material_type="PLA",
        slug="pla-black",
        color_name="Black",
        diameter=1.75,
    )
    db_session.add(filament)
    await db_session.flush()
    preset = Preset(
        filament_id=filament.id,
        user_id=admin_user.id,
        created_by_user_id=admin_user.id,
        name="Maker PLA",
        extruder_temp=210,
        bed_temp=60,
        description=None if not overwrite else "Existing notes",
        flow_rate=98,
        fan_speed=85,
        retraction_length=0.8,
        retraction_speed=35,
        orcaslicer_settings={"filament_max_volumetric_speed": ["12"]},
        external_id="existing-external-id",
    )
    db_session.add(preset)
    await db_session.commit()
    payload = proposal()
    payload["draft"]["brands"][0].update(mode="update", existing_brand=str(brand.id))
    payload["draft"]["filaments"][0].update(mode="update", existing_filament=str(filament.id))
    payload["draft"]["presets"] = [
        {
            "preset_key": "maker:pla:black:generic",
            "filament_key": "maker:pla:black",
            "mode": "update",
            "existing_preset": str(preset.id),
            "overwrite": overwrite,
            "description": "Reviewed notes",
        }
    ]
    payload["evidence"].append(
        {
            "sheet": "Presets",
            "key": "maker:pla:black:generic",
            "field": "description",
            "kind": "direct",
            "source_urls": ["https://maker.example/products/pla"],
        }
    )
    created = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert created.status_code == 201, created.text
    path = f"{BASE}/{created.json()['id']}"
    preview = await client.post(
        path + "/preview", json={"revision": 1}, headers=headers(admin_user)
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["summary"]["error"] == 0, preview.text
    row = next(item for item in preview.json()["rows"] if item["sheet"] == "Presets")
    assert set(row["changes"]) == {"description"}
    applied = await client.post(
        path + "/apply",
        json={"revision": 1, "confirmation_token": preview.json()["confirmation_token"]},
        headers=headers(admin_user),
    )
    assert applied.status_code == 200, applied.text
    await db_session.refresh(preset)
    assert preset.description == "Reviewed notes"
    assert preset.extruder_temp == 210
    assert preset.bed_temp == 60
    assert preset.flow_rate == 98
    assert preset.fan_speed == 85
    assert preset.retraction_length == 0.8
    assert preset.retraction_speed == 35
    assert preset.orcaslicer_settings == {"filament_max_volumetric_speed": ["12"]}
    assert preset.external_id == "existing-external-id"


@pytest.mark.parametrize(
    "change",
    ["price", "inference", "url", "orphan", "verified"],
)
async def test_invalid_source_claims_and_prices_are_rejected(
    client: AsyncClient, admin_user, change
):
    payload = deepcopy(proposal())
    if change == "price":
        payload["draft"]["filament_markets"] = [
            {"filament_key": "maker:pla:black", "country": "TR", "price": 500}
        ]
    elif change == "inference":
        payload["evidence"][0]["kind"] = "inferred"
    elif change == "url":
        payload["evidence"][0]["source_urls"] = ["javascript:alert(1)"]
    elif change == "verified":
        payload["draft"]["brands"][0]["verified"] = True
    else:
        payload["evidence"][0]["field"] = "fabricated_field"
    response = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert response.status_code == 422, response.text


async def test_explicit_wrong_update_reference_cannot_fallback_to_natural_identity(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    brand = Brand(name="Maker", slug="maker", active=True, verified=False)
    db_session.add(brand)
    await db_session.flush()
    filament = Filament(
        brand_id=brand.id,
        name="PLA Black",
        material_type="PLA",
        slug="pla-black",
        color_name="Black",
        diameter=1.75,
    )
    db_session.add(filament)
    await db_session.commit()
    payload = proposal()
    payload["draft"]["brands"][0].update(mode="update", existing_brand=str(brand.id))
    payload["draft"]["filaments"][0].update(mode="update", existing_filament="999999")
    created = await client.post(BASE, json=payload, headers=headers(admin_user))
    preview = await client.post(
        f"{BASE}/{created.json()['id']}/preview", json={"revision": 1}, headers=headers(admin_user)
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["confirmation_token"] is None
    assert any(
        "Existing filament was not found" in (row["message"] or "")
        for row in preview.json()["rows"]
    )
    assert await db_session.scalar(select(func.count()).select_from(CatalogCurationProposal)) == 1


def _with_packagings(payload: dict, evidenced: list[str]) -> dict:
    row = payload["draft"]["filaments"][0]
    row["packagings"] = [
        {"net_weight_g": 1000, "empty_spool_weight_g": 210, "spool_material": "plastic"},
        {"net_weight_g": 750},
    ]
    payload["evidence"] += [
        {
            "sheet": "Filaments",
            "key": "maker:pla:black",
            "field": field,
            "kind": "direct",
            "source_urls": ["https://maker.example/products/pla"],
        }
        for field in evidenced
    ]
    return payload


async def test_each_packaging_needs_its_own_evidence(client: AsyncClient, admin_user):
    # One quote for the whole list must not vouch for every weight.
    payload = _with_packagings(proposal(), ["packagings", "packagings[spool:1000]"])
    created = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert created.status_code == 201, created.text
    preview = await client.post(
        f"{BASE}/{created.json()['id']}/preview", json={"revision": 1}, headers=headers(admin_user)
    )
    row = next(row for row in preview.json()["rows"] if row["key"] == "maker:pla:black")
    assert row["status"] == "error"
    assert "packagings[spool:750]" in row["message"]
    assert "packagings[spool:1000]" not in row["message"]


async def test_evidenced_packagings_apply_and_fill_the_main_spool(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    payload = _with_packagings(proposal(), ["packagings[spool:1000]", "packagings[spool:750]"])
    created = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert created.status_code == 201, created.text
    path = f"{BASE}/{created.json()['id']}"
    preview = await client.post(path + "/preview", json={"revision": 1}, headers=headers(admin_user))
    assert preview.json()["summary"]["error"] == 0, preview.json()["rows"]
    applied = await client.post(
        path + "/apply",
        json={"revision": 1, "confirmation_token": preview.json()["confirmation_token"]},
        headers=headers(admin_user),
    )
    assert applied.status_code == 200, applied.text
    filament = await db_session.scalar(select(Filament))
    assert [item["net_weight_g"] for item in filament.packagings] == [1000, 750]
    assert (filament.spool_weight, filament.empty_spool_weight_g) == (1000, 210)


async def test_each_technical_property_is_evidenced_and_applied(
    client: AsyncClient, db_session: AsyncSession, admin_user
):
    payload = proposal()
    payload["draft"]["filaments"][0]["technical_properties"] = [
        {"code": "hdt", "value": 55, "unit": "°C", "conditions": {"load_mpa": 0.45}},
        {"code": "hdt", "value": 50, "unit": "°C", "conditions": {"load_mpa": 1.8}},
    ]
    payload["evidence"].append(
        {
            "sheet": "Filaments",
            "key": "maker:pla:black",
            "field": "technical_properties[hdt;load_mpa=0.45]",
            "kind": "direct",
            "source_urls": ["https://maker.example/products/pla"],
        }
    )
    created = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert created.status_code == 201, created.text
    path = f"{BASE}/{created.json()['id']}"
    preview = await client.post(path + "/preview", json={"revision": 1}, headers=headers(admin_user))
    row = next(row for row in preview.json()["rows"] if row["key"] == "maker:pla:black")
    assert "technical_properties[hdt;load_mpa=1.8]" in row["message"]

    payload["evidence"].append(
        {**payload["evidence"][-1], "field": "technical_properties[hdt;load_mpa=1.8]"}
    )
    revised = await client.patch(
        path,
        json={"revision": 1, "evidence": payload["evidence"]},
        headers=headers(admin_user),
    )
    assert revised.status_code == 200, revised.text
    preview = await client.post(path + "/preview", json={"revision": 2}, headers=headers(admin_user))
    assert preview.json()["summary"]["error"] == 0, preview.json()["rows"]
    applied = await client.post(
        path + "/apply",
        json={"revision": 2, "confirmation_token": preview.json()["confirmation_token"]},
        headers=headers(admin_user),
    )
    assert applied.status_code == 200, applied.text
    filament = await db_session.scalar(select(Filament))
    assert [item["conditions"] for item in filament.technical_properties] == [
        {"load_mpa": 0.45},
        {"load_mpa": 1.8},
    ]


async def test_malformed_list_items_are_a_row_error_not_a_server_error(
    client: AsyncClient, admin_user
):
    payload = proposal()
    payload["draft"]["filaments"][0]["packagings"] = [{"net_weight_g": "1 кг"}]
    payload["draft"]["filaments"][0]["technical_properties"] = [
        {"code": "hdt", "value": 55, "unit": "°C", "conditions": ["load"]}
    ]
    created = await client.post(BASE, json=payload, headers=headers(admin_user))
    assert created.status_code == 201, created.text
    preview = await client.post(
        f"{BASE}/{created.json()['id']}/preview", json={"revision": 1}, headers=headers(admin_user)
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["summary"]["error"] == 1
