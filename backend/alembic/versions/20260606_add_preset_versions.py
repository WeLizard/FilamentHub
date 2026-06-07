"""add preset_versions table + backfill initial v1

Also merges the three divergent migration heads that existed in the repo
(change_tags_to_json, add_printer_hostname, d6f1b8e2a905) into a single head.

Revision ID: add_preset_versions
Revises: change_tags_to_json, add_printer_hostname, d6f1b8e2a905
Create Date: 2026-06-06
"""

import hashlib
import json

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "add_preset_versions"
down_revision = ("change_tags_to_json", "add_printer_hostname", "d6f1b8e2a905")
branch_labels = None
depends_on = None


# Structured Preset fields captured in each snapshot. Must stay in sync with
# preset_version_service._SNAPSHOT_FIELDS.
_SNAPSHOT_FIELDS = (
    "name",
    "description",
    "extruder_temp",
    "bed_temp",
    "print_speed",
    "travel_speed",
    "layer_height",
    "first_layer_height",
    "flow_rate",
    "fan_speed",
    "retraction_length",
    "retraction_speed",
)


def _canonical_hash(orcaslicer_settings) -> str:
    payload = json.dumps(
        orcaslicer_settings or {},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.create_table(
        "preset_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, index=True),
        sa.Column(
            "preset_id",
            sa.Integer(),
            sa.ForeignKey("presets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("snapshot_orcaslicer_settings", sa.JSON(), nullable=True),
        sa.Column("snapshot_structured", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False, index=True),
        sa.Column("label", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("label_description", sa.Text(), nullable=True),
        sa.Column("change_source", sa.String(length=40), nullable=False),
        sa.Column(
            "restored_from_version_id",
            sa.BigInteger(),
            sa.ForeignKey("preset_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("squash_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("preset_id", "version_number", name="uq_preset_version"),
    )
    op.create_index(
        "ix_preset_versions_preset_created",
        "preset_versions",
        ["preset_id", "created_at"],
    )

    # --- Backfill: create an initial v1 for every existing preset ---
    bind = op.get_bind()
    cols = ", ".join(_SNAPSHOT_FIELDS)
    presets = bind.execute(
        sa.text(f"SELECT id, orcaslicer_settings, {cols} FROM presets")
    ).mappings().all()

    if presets:
        insert_sql = sa.text(
            """
            INSERT INTO preset_versions
                (preset_id, version_number, snapshot_orcaslicer_settings,
                 snapshot_structured, content_hash, label, change_source,
                 squash_count, created_at, updated_at)
            VALUES
                (:preset_id, 1, CAST(:snap_orca AS json),
                 CAST(:snap_struct AS json), :content_hash,
                 '', 'migration', 1, now(), now())
            """
        )
        for row in presets:
            orca = row["orcaslicer_settings"]
            structured = {f: row[f] for f in _SNAPSHOT_FIELDS}
            bind.execute(
                insert_sql,
                {
                    "preset_id": row["id"],
                    "snap_orca": json.dumps(orca) if orca is not None else None,
                    "snap_struct": json.dumps(structured, default=str),
                    "content_hash": _canonical_hash(orca),
                },
            )


def downgrade() -> None:
    op.drop_index("ix_preset_versions_preset_created", table_name="preset_versions")
    op.drop_table("preset_versions")
