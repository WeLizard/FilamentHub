"""Durable Spoolman wire identities, private extras and legacy pending spools.

Revision ID: spool_compat_resources
Revises: orca_schema_sample_value
"""

from __future__ import annotations

import json
from copy import deepcopy
from math import isfinite

import sqlalchemy as sa

from alembic import op

revision = "spool_compat_resources"
down_revision = "orca_schema_sample_value"
branch_labels = None
depends_on = None

def _sequence_highwater(bind: sa.Connection, table: str) -> int:
    """Include allocated PostgreSQL IDs even if a transaction later rolled back."""
    if bind.dialect.name != "postgresql":
        return 0
    sequence = bind.scalar(sa.text("SELECT pg_get_serial_sequence(:table, 'id')"), {"table": table})
    if not sequence:
        return 0
    quoted = ".".join(bind.dialect.identifier_preparer.quote(part.strip('"')) for part in sequence.split("."))
    return int(bind.scalar(sa.text(f"SELECT last_value FROM {quoted}")) or 0)


def _positive_number(value: object) -> float | None:
    try:
        number = float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
    return number if number is not None and isfinite(number) and number > 0 else None


def _legacy_material_payload(snapshot: dict) -> dict:
    """Migration-local snapshot of the runtime import material projection."""
    extra = snapshot.get("extra")
    fields = extra if isinstance(extra, dict) else {}
    raw = fields.get("import_original")
    original = raw if isinstance(raw, dict) else {}
    latest = {
        "legacy_spool": deepcopy(snapshot),
        "name": fields.get("display_name") or original.get("name") or f"Spool {snapshot['id']}",
        "material": fields.get("material") or original.get("material") or "Unknown",
        "weight": snapshot["initial_weight_g"],
    }
    vendor_name = fields.get("vendor") or original.get("vendor_name")
    if isinstance(vendor_name, str) and vendor_name.strip():
        latest["vendor"] = {"name": vendor_name.strip()}
    color = fields.get("color_hex") or original.get("color_hex")
    if isinstance(color, str) and color.strip():
        latest["color_hex"] = color.strip().lstrip("#")
    density = _positive_number(fields.get("density_g_cm3") or original.get("density"))
    diameter = _positive_number(fields.get("diameter_mm") or original.get("diameter"))
    if density is not None:
        latest["density"] = density
    if diameter is not None:
        latest["diameter"] = diameter
    tare = snapshot.get("empty_spool_weight_g")
    if tare is not None:
        latest["spool_weight"] = tare
    for source, target in (
        ("nozzle_temperature_c", "settings_extruder_temp"),
        ("bed_temperature_c", "settings_bed_temp"),
    ):
        temperature = _positive_number(fields.get(source))
        if temperature is not None:
            latest[target] = temperature
    return latest


def _nonnegative_tare(extra: object) -> float | None:
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except (TypeError, ValueError):
            return None
    fields = extra if isinstance(extra, dict) else {}
    value = fields.get("empty_spool_weight_g")
    try:
        tare = float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
    return tare if tare is not None and isfinite(tare) and tare >= 0 else None


def _backfill_spool_tare(bind: sa.Connection) -> int:
    """Copy valid per-instance legacy tare for matched and unmatched spools."""
    rows = bind.execute(sa.text(
        "SELECT id, extra FROM user_spools "
        "WHERE extra IS NOT NULL AND empty_spool_weight_g IS NULL ORDER BY id"
    )).mappings().all()
    updates = [
        {"spool_id": row["id"], "tare": tare}
        for row in rows
        if (tare := _nonnegative_tare(row["extra"])) is not None
    ]
    if updates:
        bind.execute(sa.text(
            "UPDATE user_spools SET empty_spool_weight_g = :tare "
            "WHERE id = :spool_id AND empty_spool_weight_g IS NULL"
        ), updates)
    return len(updates)


def _resource_insert_statement(resources: sa.TableClause, values: dict) -> sa.Insert:
    """The migration's lightweight table has no mapped PK for implicit RETURNING."""
    return resources.insert().values(**values).returning(resources.c.id)


def upgrade() -> None:
    op.create_table(
        "spool_compat_wire_counters",
        sa.Column("kind", sa.String(16), primary_key=True),
        sa.Column("next_wire_id", sa.BigInteger(), nullable=False),
    )
    op.create_table(
        "spool_compat_resources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("wire_id", sa.BigInteger(), nullable=False),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brands.id", ondelete="SET NULL"), nullable=True),
        sa.Column("filament_id", sa.Integer(), sa.ForeignKey("filaments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("original_payload", sa.JSON(), nullable=True),
        sa.Column("latest_payload", sa.JSON(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_namespace", sa.String(80), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("kind", "wire_id", name="uq_spool_compat_kind_wire"),
        sa.CheckConstraint("kind IN ('vendor','filament')", name="ck_spool_compat_kind"),
        sa.CheckConstraint("source_kind IN ('catalog','import','alias')", name="ck_spool_compat_source"),
        sa.CheckConstraint(
            "(kind = 'vendor' AND filament_id IS NULL) OR "
            "(kind = 'filament' AND brand_id IS NULL)", name="ck_spool_compat_target_kind",
        ),
        sa.CheckConstraint(
            "(source_kind = 'import' AND user_id IS NOT NULL AND "
            "original_payload IS NOT NULL AND latest_payload IS NOT NULL) OR "
            "(source_kind IN ('catalog','alias') AND user_id IS NULL AND "
            "original_payload IS NULL AND latest_payload IS NULL)",
            name="ck_spool_compat_owner_payload",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_spool_compat_revision"),
    )
    op.create_index("ix_spool_compat_owner_kind", "spool_compat_resources", ["user_id", "kind"])
    op.create_index(
        "uq_spool_compat_catalog_brand", "spool_compat_resources", ["brand_id"], unique=True,
        postgresql_where=sa.text("source_kind = 'catalog'"),
        sqlite_where=sa.text("source_kind = 'catalog'"),
    )
    op.create_index(
        "uq_spool_compat_catalog_filament", "spool_compat_resources", ["filament_id"], unique=True,
        postgresql_where=sa.text("source_kind = 'catalog'"),
        sqlite_where=sa.text("source_kind = 'catalog'"),
    )
    op.create_table(
        "spool_compat_resource_extras",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_id", sa.Integer(), sa.ForeignKey("spool_compat_resources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extra", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "resource_id", name="uq_spool_compat_extra_owner_ref"),
    )
    op.create_index("ix_spool_compat_resource_extras_user_id", "spool_compat_resource_extras", ["user_id"])
    op.create_index("ix_spool_compat_resource_extras_resource_id", "spool_compat_resource_extras", ["resource_id"])
    op.create_table(
        "spool_compat_field_defs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "kind", "key", name="uq_spool_compat_field_owner_key"),
        sa.CheckConstraint("kind IN ('spool','vendor','filament')", name="ck_spool_compat_field_kind"),
    )
    op.create_index("ix_spool_compat_field_defs_user_id", "spool_compat_field_defs", ["user_id"])
    op.add_column("user_spools", sa.Column("compat_filament_ref_id", sa.Integer(), nullable=True))
    op.add_column("user_spools", sa.Column("empty_spool_weight_g", sa.Float(), nullable=True))
    op.create_foreign_key("fk_user_spool_compat_ref", "user_spools", "spool_compat_resources",
                          ["compat_filament_ref_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_user_spools_compat_filament_ref_id", "user_spools", ["compat_filament_ref_id"])

    bind = op.get_bind()
    tare_count = _backfill_spool_tare(bind)
    if bind.dialect.name == "postgresql":
        # Freeze catalog inserts while determining sequence high-water marks and
        # reserving all existing PKs in the new wire namespace.
        bind.execute(sa.text("LOCK TABLE brands, filaments IN SHARE ROW EXCLUSIVE MODE"))
    resources = sa.table(
        "spool_compat_resources",
        sa.column("id", sa.Integer()), sa.column("kind", sa.String()),
        sa.column("wire_id", sa.BigInteger()), sa.column("source_kind", sa.String()),
        sa.column("user_id", sa.Integer()), sa.column("brand_id", sa.Integer()),
        sa.column("filament_id", sa.Integer()), sa.column("original_payload", sa.JSON()),
        sa.column("latest_payload", sa.JSON()), sa.column("revision", sa.Integer()),
        sa.column("source_namespace", sa.String()), sa.column("external_id", sa.String()),
    )
    counters = sa.table("spool_compat_wire_counters", sa.column("kind", sa.String()),
                        sa.column("next_wire_id", sa.BigInteger()))
    next_ids: dict[str, int] = {}
    for kind, table in (("vendor", "brands"), ("filament", "filaments")):
        maximum = int(bind.scalar(sa.text(f"SELECT COALESCE(MAX(id), 0) FROM {table}")) or 0)
        highwater = max(maximum, _sequence_highwater(bind, table))
        next_ids[kind] = highwater + 1
        bind.execute(counters.insert().values(kind=kind, next_wire_id=next_ids[kind]))
        # Existing published catalog PKs remain unchanged as transport IDs.
        target_column = "brand_id" if kind == "vendor" else "filament_id"
        bind.execute(sa.text(
            f"INSERT INTO spool_compat_resources "
            f"(kind, wire_id, source_kind, {target_column}, revision) "
            f"SELECT :kind, id, 'catalog', id, 1 FROM {table}"
        ), {"kind": kind})

    bind.execute(sa.text(
        "UPDATE user_spools SET compat_filament_ref_id = "
        "(SELECT id FROM spool_compat_resources AS r "
        "WHERE r.kind = 'filament' AND r.source_kind = 'catalog' "
        "AND r.filament_id = user_spools.filament_id) "
        "WHERE filament_id IS NOT NULL AND compat_filament_ref_id IS NULL"
    ))

    # Existing unmatched physical spools remain unmatched; only a private
    # transport reference and exact pre-migration evidence are added.
    legacy = bind.execute(sa.text(
        "SELECT id, user_id, source, initial_weight_g, used_weight_g, price, "
        "lot_nr, comment, extra, empty_spool_weight_g FROM user_spools "
        "WHERE filament_id IS NULL ORDER BY id"
    )).mappings().all()
    for spool in legacy:
        extra = deepcopy(spool["extra"] or {})
        if isinstance(extra, str):
            try:
                extra = json.loads(extra)
            except (TypeError, ValueError):
                pass
        extra_fields = extra if isinstance(extra, dict) else {}
        snapshot = {
            "id": spool["id"], "source": spool["source"],
            "initial_weight_g": spool["initial_weight_g"],
            "used_weight_g": spool["used_weight_g"], "price": spool["price"],
            "lot_nr": spool["lot_nr"], "comment": spool["comment"],
            "empty_spool_weight_g": spool["empty_spool_weight_g"], "extra": extra,
        }
        payload = {"legacy_spool": snapshot}
        wire_id = next_ids["filament"]
        next_ids["filament"] += 1
        values = {
            "kind": "filament", "wire_id": wire_id, "source_kind": "import",
            "user_id": spool["user_id"], "original_payload": payload,
            "latest_payload": _legacy_material_payload(snapshot), "revision": 1,
            "source_namespace": str(extra_fields.get("import_provider") or spool["source"])[:80],
            "external_id": str(extra_fields.get("import_external_ref") or spool["id"])[:255],
        }
        resource_id = bind.execute(_resource_insert_statement(resources, values)).scalar_one()
        bind.execute(sa.text(
            "UPDATE user_spools SET compat_filament_ref_id = :resource_id "
            "WHERE id = :spool_id"
        ), {"resource_id": resource_id, "spool_id": spool["id"]})
    bind.execute(
        counters.update().where(counters.c.kind == "filament")
        .values(next_wire_id=next_ids["filament"])
    )
    affected = bind.scalar(sa.text(
        "SELECT COUNT(*) FROM user_spools WHERE filament_id IS NULL "
        "AND compat_filament_ref_id IS NOT NULL"
    ))
    print(f"spool_compat_resources: preserved {affected} unmatched spools as private import refs")
    print(f"spool_compat_resources: backfilled {tare_count} individual spool tare values")


def downgrade() -> None:
    raise RuntimeError("spool_compat_resources preserves imported identity and has no safe automatic downgrade")
