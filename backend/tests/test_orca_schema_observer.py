"""Unknown OrcaSlicer field observation and admin review tests."""

import json
import zipfile
from pathlib import Path, PurePosixPath
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from app.models.orca_schema_observation import OrcaSchemaObservation
from app.services.orca_field_registry import ORCA_PRESET_FIELDS
from app.services.orca_schema_observer import (
    detect_unknown_orca_fields,
    observe_orca_schema_fields,
)

# The archive is deliberately not versioned (see .gitignore), so it is absent on a
# fresh checkout and in CI. The coverage check is worth keeping where the archive
# exists; where it does not, failing would say nothing about the code.
BUNDLE_PATH = Path(__file__).resolve().parents[1] / "data/catalog_sources/orca/bundle.zip"
requires_bundle = pytest.mark.skipif(
    not BUNDLE_PATH.is_file(),
    reason="Orca source archive is not versioned; fetch it with scripts/refresh_orca_catalog_source.py",
)


@requires_bundle
def test_every_current_bundle_field_is_accepted_by_the_registry() -> None:
    bundle_path = BUNDLE_PATH
    observed = {scope: set() for scope in ORCA_PRESET_FIELDS}

    with zipfile.ZipFile(bundle_path) as archive:
        for name in archive.namelist():
            path = PurePosixPath(name)
            scope = next(
                (candidate for candidate in observed if candidate in path.parts),
                None,
            )
            if scope is None or path.suffix.lower() != ".json":
                continue
            document = json.loads(archive.read(name))
            if isinstance(document, dict):
                observed[scope].update(document)

    assert {
        scope: sorted(fields - ORCA_PRESET_FIELDS[scope])
        for scope, fields in observed.items()
    } == {"filament": [], "process": [], "machine": []}


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


def test_detector_accepts_reviewed_orca_fields_exposed_by_the_editors() -> None:
    filament_settings = {
        key: ["fixture"]
        for key in {
            "initial_layer_fan_speed",
            "filament_retract_restart_extra_toolchange",
            "filament_retract_length_toolchange",
            "filament_retract_after_wipe",
            "filament_change_extrusion_role_gcode",
            "chamber_minimal_temperature",
            "activate_air_filtration_on_completion",
            "activate_air_filtration_during_print",
        }
    }
    process_settings = {
        key: "fixture"
        for key in {
            "sparse_infill_smooth_factor",
            "enable_mixed_color_sublayer",
            "brim_ears_outer_only",
            "zaa_minimize_perimeter_height",
            "zaa_min_z",
            "zaa_enabled",
            "zaa_dont_alternate_fill_direction",
            "wall_maximum_resolution",
            "wall_maximum_deviation",
            "top_surface_fill_order",
            "top_surface_expansion_margin",
            "top_surface_expansion_direction",
            "top_surface_expansion",
            "top_layer_direction",
            "toolchange_ordering",
            "small_support_perimeter_threshold",
            "small_support_perimeter_speed",
            "separated_infills",
        }
    }
    reviewed_forward_compatible = {
        "filament": {
            "_comment",
            "filament_colour",
            "is_custom_defined",
            "plugins",
        },
        "process": {
            "bottom_layer_direction",
            "bottom_surface_fill_order",
            "bridge_line_width",
            "brim_flow_ratio",
            "center_of_surface_pattern",
            "combine_brims",
            "elefant_foot_layers_density",
            "even_loops_flow_ratio",
            "even_loops_speed",
            "fuzzy_skin_layers_between_ripple_offset",
            "fuzzy_skin_ripple_offset",
            "fuzzy_skin_ripples_per_layer",
            "gyroid_optimized",
            "hole_to_polyhole_max_edges",
            "initial_layer_travel_jerk",
            "ironing_expansion",
            "lightning_overhang_angle",
            "lightning_prune_angle",
            "lightning_straightening_angle",
            "loop_sequence",
            "outermost_wall_control",
            "plugin_config_overrides",
            "plugins",
            "print_plugin_config_overrides",
            "process_change_extrusion_role_gcode",
            "relative_bridge_angle",
            "staggered_perimeter_flow_ratio",
            "staggered_perimeters",
        },
        "machine": {
            "is_custom_defined",
            "belt_frame_tilt_angle",
            "belt_frame_tilt_decouple",
            "belt_preslice_global",
            "belt_printer",
            "belt_printer_infinite_y",
            "belt_slice_rotation",
            "belt_slice_rotation_angle",
            "belt_slice_rotation_global",
            "belt_support_floor_mode",
            "belt_support_floor_offset",
            "belt_support_z_offset_mode",
            "build_plate_tilt_x",
            "build_plate_tilt_y",
            "extruder_nozzle_stats",
            "first_layer_plane",
            "first_layer_plane_offset",
            "first_layer_plane_thickness",
            "flashforge_serial_number",
            "gcode_back_transform",
            "gcode_remap_x",
            "gcode_remap_y",
            "gcode_remap_z",
            "gcode_skip_config_block",
            "input_shaping_damp_x",
            "input_shaping_damp_y",
            "input_shaping_emit",
            "input_shaping_freq_x",
            "input_shaping_freq_y",
            "input_shaping_type",
            "part_cooling_fan_min_pwm",
            "plugin_config_overrides",
            "preslice_remap_global",
            "preslice_remap_x",
            "preslice_remap_y",
            "preslice_remap_z",
            "printer_plugin_config_overrides",
            "retract_after_wipe",
            "tool_change_on_wipe_tower",
        },
    }

    assert detect_unknown_orca_fields(filament_settings, "filament") == []
    assert detect_unknown_orca_fields(process_settings, "process") == []
    for scope, fields in reviewed_forward_compatible.items():
        assert detect_unknown_orca_fields(
            {field: "fixture" for field in fields},
            scope,
        ) == []


def test_detector_is_bounded_and_ignores_filamenthub_private_fields() -> None:
    settings = {f"future_{index:03d}": index for index in range(100)}
    settings.update(
        {
            "fhub_id": 12,
            "bundle_id": "filamenthub:12",
            "slicing_pipeline_plugin": "FilamentHub",
            "slicing_pipeline_plugin_config_overrides": {"opaque": True},
            "derived_from_external_id": "legacy-external-id",
            "derived_from_draft_id": "legacy-draft-id",
            "enrichment": {"material_type": "PLA"},
        }
    )

    detected = detect_unknown_orca_fields(settings, "process")

    assert len(detected) == 64
    assert all(not item.field_name.startswith("fhub_") for item in detected)
    assert all(item.field_name != "bundle_id" for item in detected)
    assert all("slicing_pipeline_plugin" not in item.field_name for item in detected)
    assert all(not item.field_name.startswith("derived_from_") for item in detected)
    assert all(item.field_name != "enrichment" for item in detected)


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
            OrcaSchemaObservation(
                scope="filament",
                field_name="derived_from_external_id",
                value_shape="string",
                registry_version="old-registry",
                first_source="test",
                last_source="test",
            ),
            OrcaSchemaObservation(
                scope="filament",
                field_name="derived_from_draft_id",
                value_shape="string",
                registry_version="old-registry",
                first_source="test",
                last_source="test",
            ),
            OrcaSchemaObservation(
                scope="process",
                field_name="enable_mixed_color_sublayer",
                value_shape="string",
                registry_version="old-registry",
                first_source="test",
                last_source="test",
            ),
            OrcaSchemaObservation(
                scope="machine",
                field_name="is_custom_defined",
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
