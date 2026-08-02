"""Unknown OrcaSlicer field observation and admin review tests."""

import hashlib
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from app.models.orca_schema_observation import OrcaSchemaObservation
from app.services.orca_field_registry import ORCA_FIELD_REGISTRY_VERSION
from app.services.orca_schema_observer import (
    detect_unknown_orca_fields,
    observe_orca_schema_fields,
)


def test_registry_version_matches_bundled_orca_catalog() -> None:
    bundle_path = Path(__file__).resolve().parents[1] / "data/catalog_sources/orca/bundle.zip"
    expected = f"bundle-sha256:{hashlib.sha256(bundle_path.read_bytes()).hexdigest()}"

    assert ORCA_FIELD_REGISTRY_VERSION == expected


def test_detector_reports_only_unknown_top_level_field_metadata() -> None:
    settings = {
        "filament_type": ["PLA"],
        "filament_plugin_config_overrides": {"secret_nested_value": "must-not-be-inspected"},
        "future_orca_field": ["sensitive value"],
    }

    detected = detect_unknown_orca_fields(settings, "filament")

    assert [(item.field_name, item.value_shape) for item in detected] == [
        ("future_orca_field", "array:string"),
    ]
    assert all("sensitive" not in repr(item) for item in detected)
    assert all("secret_nested_value" not in item.field_name for item in detected)


def test_detector_is_bounded_and_ignores_filamenthub_private_fields() -> None:
    settings = {f"future_{index:03d}": index for index in range(100)}
    settings.update(
        {
            "fhub_id": 12,
            "bundle_id": "filamenthub:12",
            "slicing_pipeline_plugin": "FilamentHub",
            "slicing_pipeline_plugin_config_overrides": {"opaque": True},
        }
    )

    detected = detect_unknown_orca_fields(settings, "process")

    assert len(detected) == 64
    assert all(not item.field_name.startswith("fhub_") for item in detected)
    assert all(item.field_name != "bundle_id" for item in detected)
    assert all("slicing_pipeline_plugin" not in item.field_name for item in detected)


@pytest.mark.asyncio
async def test_observer_aggregates_repeated_field_shapes(db_session) -> None:
    settings = {"future_orca_field": ["value"]}

    await observe_orca_schema_fields(
        db=db_session, settings=settings, scope="machine", source="test_sync"
    )
    await observe_orca_schema_fields(
        db=db_session, settings=settings, scope="machine", source="test_sync"
    )
    await db_session.commit()

    row = (await db_session.execute(select(OrcaSchemaObservation))).scalar_one()
    assert row.scope == "machine"
    assert row.field_name == "future_orca_field"
    assert row.value_shape == "array:string"
    assert row.occurrences == 2
    assert row.status == "new"
    assert not hasattr(row, "sample_value")


@pytest.mark.asyncio
async def test_observer_reopens_reviewed_field_when_shape_changes(db_session) -> None:
    await observe_orca_schema_fields(
        db=db_session,
        settings={"future_orca_field": ["value"]},
        scope="machine",
        source="test_sync",
    )
    await db_session.commit()
    row = (await db_session.execute(select(OrcaSchemaObservation))).scalar_one()
    row.status = "reviewed"
    await db_session.commit()

    await observe_orca_schema_fields(
        db=db_session,
        settings={"future_orca_field": 42},
        scope="machine",
        source="test_sync",
    )
    await db_session.commit()
    db_session.expire_all()

    rows = (await db_session.execute(select(OrcaSchemaObservation))).scalars().all()
    assert len(rows) == 1
    assert rows[0].value_shape == "number"
    assert rows[0].status == "new"
    assert rows[0].reviewed_at is None
    assert rows[0].reviewed_by_user_id is None


@pytest.mark.asyncio
async def test_print_profile_sync_records_unknown_field_without_changing_payload(
    auth_client, db_session
) -> None:
    response = await auth_client.post(
        "/api/v1/orcaslicer/print-profiles/import",
        json={
            "profiles": [
                {
                    "external_id": "schema-watch-process",
                    "name": "Schema watch process",
                    "orcaslicer_settings": {
                        "layer_height": ["0.2"],
                        "future_orca_process_field": ["preserved"],
                    },
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["status"] == "created"
    observation = (await db_session.execute(select(OrcaSchemaObservation))).scalar_one()
    assert observation.field_name == "future_orca_process_field"

    from app.models.print_profile import PrintProfile

    profile = (await db_session.execute(select(PrintProfile))).scalar_one()
    assert profile.orcaslicer_settings["future_orca_process_field"] == ["preserved"]


@pytest.mark.asyncio
async def test_observer_failure_does_not_escape() -> None:
    db = Mock()
    db.begin_nested.side_effect = RuntimeError("observation storage unavailable")

    await observe_orca_schema_fields(
        db=db,
        settings={"future_orca_field": True},
        scope="filament",
    )


@pytest.mark.asyncio
async def test_admin_can_filter_and_review_observations(admin_client, db_session) -> None:
    db_session.add_all(
        [
            OrcaSchemaObservation(
                scope="filament",
                field_name="future_filament_field",
                value_shape="string",
                registry_version="test-registry",
                first_source="test",
                last_source="test",
            ),
            OrcaSchemaObservation(
                scope="process",
                field_name="future_process_field",
                value_shape="number",
                registry_version="test-registry",
                first_source="test",
                last_source="test",
                status="reviewed",
            ),
        ]
    )
    await db_session.commit()

    response = await admin_client.get(
        "/api/v1/admin/orca-schema-observations",
        params={"status": "new", "scope": "filament", "size": 10},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["new_count"] == 1
    assert payload["items"][0]["field_name"] == "future_filament_field"
    observation_id = payload["items"][0]["id"]

    update = await admin_client.patch(
        f"/api/v1/admin/orca-schema-observations/{observation_id}",
        json={"status": "reviewed"},
    )
    assert update.status_code == 200
    assert update.json()["status"] == "reviewed"
    assert update.json()["reviewed_by_user_id"] is not None

    legacy_update = await admin_client.patch(
        f"/api/v1/admin/orca-schema-observations/{observation_id}",
        json={"status": "ignored"},
    )
    assert legacy_update.status_code == 422


@pytest.mark.asyncio
async def test_admin_list_prunes_fields_now_covered_by_registry(
    admin_client, db_session
) -> None:
    db_session.add_all(
        [
            OrcaSchemaObservation(
                scope="filament",
                field_name="filament_type",
                value_shape="array:string",
                registry_version="old-registry",
                first_source="test",
                last_source="test",
                status="reviewed",
            ),
            OrcaSchemaObservation(
                scope="filament",
                field_name="future_filament_field",
                value_shape="string",
                registry_version="old-registry",
                first_source="test",
                last_source="test",
            ),
        ]
    )
    await db_session.commit()

    response = await admin_client.get("/api/v1/admin/orca-schema-observations")

    assert response.status_code == 200
    assert [item["field_name"] for item in response.json()["items"]] == [
        "future_filament_field"
    ]
    remaining = (
        await db_session.execute(select(OrcaSchemaObservation.field_name))
    ).scalars().all()
    assert remaining == ["future_filament_field"]


@pytest.mark.asyncio
async def test_regular_user_cannot_read_schema_observations(auth_client) -> None:
    response = await auth_client.get("/api/v1/admin/orca-schema-observations")
    assert response.status_code == 403
