"""Best-effort detection of OrcaSlicer fields outside the bundled baseline."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import case, delete, select, tuple_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orca_schema_observation import OrcaSchemaObservation
from app.services.orca_field_registry import (
    ORCA_FIELD_REGISTRY_VERSION,
    ORCA_PRESET_FIELDS,
)
from app.services.orca_transport import FILAMENTHUB_INTERNAL_KEYS

logger = logging.getLogger(__name__)

OrcaPresetScope = Literal["filament", "process", "machine"]

_KNOWN_RUNTIME_FIELDS = frozenset(
    {
        "bundle_id",
        "fhub_draft_id",
        "fhub_id",
        "fhub_source",
        "filament_plugin_config_overrides",
        "filament_plugin",
        "slicing_pipeline_plugin",
        "slicing_pipeline_plugin_config_overrides",
        "_inherits_chain",
    }
)
_MAX_FIELD_NAME_LENGTH = 200
_MAX_UNKNOWN_FIELDS_PER_PAYLOAD = 64


@dataclass(frozen=True)
class UnknownOrcaField:
    field_name: str
    value_shape: str


def _known_fields(scope: str) -> frozenset[str]:
    return (
        ORCA_PRESET_FIELDS.get(scope, frozenset())
        | _KNOWN_RUNTIME_FIELDS
        | FILAMENTHUB_INTERNAL_KEYS
    )


def _value_shape(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        if not value:
            return "array:empty"
        item_shapes = {_value_shape(item) for item in value[:20]}
        return f"array:{next(iter(item_shapes))}" if len(item_shapes) == 1 else "array:mixed"
    return "other"


def detect_unknown_orca_fields(
    settings: dict[str, Any], scope: OrcaPresetScope
) -> list[UnknownOrcaField]:
    """Return bounded top-level metadata only; values are never retained."""

    known_fields = _known_fields(scope)
    unknown: list[UnknownOrcaField] = []
    field_names = sorted(name for name in settings if isinstance(name, str))
    for field_name in field_names:
        if field_name in known_fields:
            continue
        if not field_name or len(field_name) > _MAX_FIELD_NAME_LENGTH or "\x00" in field_name:
            continue
        unknown.append(
            UnknownOrcaField(
                field_name=field_name,
                value_shape=_value_shape(settings[field_name]),
            )
        )
        if len(unknown) >= _MAX_UNKNOWN_FIELDS_PER_PAYLOAD:
            break
    return unknown


async def prune_known_orca_schema_observations(db: AsyncSession) -> int:
    """Remove observations that are covered by the current bundled registry."""

    result = await db.execute(
        select(
            OrcaSchemaObservation.id,
            OrcaSchemaObservation.scope,
            OrcaSchemaObservation.field_name,
        )
    )
    known_ids = [
        observation_id
        for observation_id, scope, field_name in result
        if field_name in _known_fields(scope)
    ]
    if not known_ids:
        return 0

    await db.execute(
        delete(OrcaSchemaObservation).where(OrcaSchemaObservation.id.in_(known_ids))
    )
    await db.flush()
    return len(known_ids)


async def observe_orca_schema_fields(
    *,
    db: AsyncSession,
    settings: dict[str, Any],
    scope: OrcaPresetScope,
    source: str = "orcaslicer_sync",
) -> None:
    """Aggregate unknown field metadata without ever making sync depend on it."""

    unknown = detect_unknown_orca_fields(settings, scope)
    if not unknown:
        return

    now = datetime.now(timezone.utc)
    keys = [(scope, item.field_name) for item in unknown]
    try:
        async with db.begin_nested():
            rows = [
                {
                    "scope": scope,
                    "field_name": item.field_name,
                    "value_shape": item.value_shape,
                    "status": "new",
                    "occurrences": 1,
                    "registry_version": ORCA_FIELD_REGISTRY_VERSION,
                    "first_source": source,
                    "last_source": source,
                    "first_seen_at": now,
                    "last_seen_at": now,
                }
                for item in unknown
            ]
            dialect_name = db.get_bind().dialect.name
            insert_factory = {
                "postgresql": postgresql_insert,
                "sqlite": sqlite_insert,
            }.get(dialect_name)
            if insert_factory is not None:
                insert_statement = insert_factory(OrcaSchemaObservation).values(rows)
                incoming_shape = insert_statement.excluded.value_shape
                shape_changed = OrcaSchemaObservation.value_shape != incoming_shape
                statement = insert_statement.on_conflict_do_update(
                    index_elements=["scope", "field_name"],
                    set_={
                        "value_shape": incoming_shape,
                        "status": case(
                            (shape_changed, "new"),
                            else_=OrcaSchemaObservation.status,
                        ),
                        "occurrences": OrcaSchemaObservation.occurrences + 1,
                        "registry_version": ORCA_FIELD_REGISTRY_VERSION,
                        "last_source": source,
                        "last_seen_at": now,
                        "reviewed_at": case(
                            (shape_changed, None),
                            else_=OrcaSchemaObservation.reviewed_at,
                        ),
                        "reviewed_by_user_id": case(
                            (shape_changed, None),
                            else_=OrcaSchemaObservation.reviewed_by_user_id,
                        ),
                    },
                )
                await db.execute(statement)
            else:
                existing_result = await db.execute(
                    select(OrcaSchemaObservation).where(
                        tuple_(
                            OrcaSchemaObservation.scope,
                            OrcaSchemaObservation.field_name,
                        ).in_(keys)
                    )
                )
                existing = {
                    (row.scope, row.field_name): row
                    for row in existing_result.scalars()
                }
                for item, row_values in zip(unknown, rows, strict=True):
                    key = (scope, item.field_name)
                    row = existing.get(key)
                    if row is None:
                        db.add(OrcaSchemaObservation(**row_values))
                    else:
                        if row.value_shape != item.value_shape:
                            row.value_shape = item.value_shape
                            row.status = "new"
                            row.reviewed_at = None
                            row.reviewed_by_user_id = None
                        row.occurrences += 1
                        row.last_seen_at = now
                        row.last_source = source
                        row.registry_version = ORCA_FIELD_REGISTRY_VERSION
                await db.flush()
    except Exception:  # noqa: BLE001
        logger.warning(
            "Failed to record Orca schema observations; preset sync continues",
            exc_info=True,
        )
