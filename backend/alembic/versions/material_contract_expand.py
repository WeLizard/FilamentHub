"""expand physical printer and provider-neutral material contract

Revision ID: material_contract_expand
Revises: usp_targets_table
Create Date: 2026-07-18
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "material_contract_expand"
down_revision: str | None = "usp_targets_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CAPABILITIES_HH = ["read", "write", "presence", "spool_identity", "consumption"]


def upgrade() -> None:
    op.add_column(
        "user_printer_devices",
        sa.Column("logical_id", sa.String(length=36), nullable=True),
    )

    bind = op.get_bind()
    device_rows = bind.execute(
        sa.text(
            """
            SELECT id, user_id, supports_hh, gate_count, device_fingerprint,
                   api_key, printer_hostname, last_seen_at
            FROM user_printer_devices
            ORDER BY id
            """
        )
    ).mappings()
    devices = [dict(row) for row in device_rows]
    for device in devices:
        bind.execute(
            sa.text(
                "UPDATE user_printer_devices SET logical_id = :logical_id WHERE id = :id"
            ),
            {"logical_id": str(uuid4()), "id": device["id"]},
        )

    op.create_index(
        "ix_user_printer_devices_logical_id",
        "user_printer_devices",
        ["logical_id"],
        unique=True,
    )
    op.alter_column(
        "user_printer_devices",
        "logical_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
    op.alter_column(
        "user_printer_devices",
        "device_fingerprint",
        existing_type=sa.String(length=200),
        nullable=True,
    )

    op.create_table(
        "user_printer_profile_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "physical_printer_id",
            sa.Integer(),
            sa.ForeignKey("user_printer_devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "printer_profile_id",
            sa.Integer(),
            sa.ForeignKey("printer_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "physical_printer_id",
            "printer_profile_id",
            name="uq_user_printer_profile_link",
        ),
    )
    op.create_index(
        "ix_user_printer_profile_links_user_id",
        "user_printer_profile_links",
        ["user_id"],
    )
    op.create_index(
        "ix_user_printer_profile_links_physical_printer_id",
        "user_printer_profile_links",
        ["physical_printer_id"],
    )
    op.create_index(
        "ix_user_printer_profile_links_printer_profile_id",
        "user_printer_profile_links",
        ["printer_profile_id"],
    )

    op.create_table(
        "material_systems",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "physical_printer_id",
            sa.Integer(),
            sa.ForeignKey("user_printer_devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column(
            "capabilities", sa.JSON(), server_default=sa.text("'[]'"), nullable=False
        ),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
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
    )
    op.create_index("ix_material_systems_user_id", "material_systems", ["user_id"])
    op.create_index(
        "ix_material_systems_physical_printer_id",
        "material_systems",
        ["physical_printer_id"],
    )

    op.create_table(
        "material_slots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "material_system_id",
            sa.Integer(),
            sa.ForeignKey("material_systems.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider_index", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=True),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
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
        sa.UniqueConstraint(
            "material_system_id",
            "provider_index",
            name="uq_material_system_slot_index",
        ),
    )
    op.create_index("ix_material_slots_user_id", "material_slots", ["user_id"])
    op.create_index(
        "ix_material_slots_material_system_id",
        "material_slots",
        ["material_system_id"],
    )

    op.create_table(
        "physical_printer_connectors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "physical_printer_id",
            sa.Integer(),
            sa.ForeignKey("user_printer_devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "material_system_id",
            sa.Integer(),
            sa.ForeignKey("material_systems.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("transport", sa.String(length=50), nullable=False),
        sa.Column(
            "capabilities", sa.JSON(), server_default=sa.text("'[]'"), nullable=False
        ),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint(
            "physical_printer_id",
            "provider",
            "transport",
            name="uq_physical_printer_connector",
        ),
    )
    op.create_index(
        "ix_physical_printer_connectors_user_id",
        "physical_printer_connectors",
        ["user_id"],
    )
    op.create_index(
        "ix_physical_printer_connectors_physical_printer_id",
        "physical_printer_connectors",
        ["physical_printer_id"],
    )
    op.create_index(
        "ix_physical_printer_connectors_material_system_id",
        "physical_printer_connectors",
        ["material_system_id"],
    )

    op.add_column(
        "preset_gate_states",
        sa.Column(
            "material_slot_id",
            sa.Integer(),
            sa.ForeignKey("material_slots.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_preset_gate_states_material_slot_id",
        "preset_gate_states",
        ["material_slot_id"],
    )

    material_systems = sa.table(
        "material_systems",
        sa.column("id", sa.Integer()),
        sa.column("user_id", sa.Integer()),
        sa.column("physical_printer_id", sa.Integer()),
        sa.column("name", sa.String()),
        sa.column("kind", sa.String()),
        sa.column("provider", sa.String()),
        sa.column("capabilities", sa.JSON()),
        sa.column("active", sa.Boolean()),
    )
    material_slots = sa.table(
        "material_slots",
        sa.column("id", sa.Integer()),
        sa.column("user_id", sa.Integer()),
        sa.column("material_system_id", sa.Integer()),
        sa.column("provider_index", sa.Integer()),
        sa.column("label", sa.String()),
        sa.column("kind", sa.String()),
        sa.column("active", sa.Boolean()),
    )
    connectors = sa.table(
        "physical_printer_connectors",
        sa.column("id", sa.Integer()),
        sa.column("user_id", sa.Integer()),
        sa.column("physical_printer_id", sa.Integer()),
        sa.column("material_system_id", sa.Integer()),
        sa.column("provider", sa.String()),
        sa.column("transport", sa.String()),
        sa.column("capabilities", sa.JSON()),
        sa.column("active", sa.Boolean()),
        sa.column("last_seen_at", sa.DateTime(timezone=True)),
    )

    gate_rows = bind.execute(
        sa.text(
            "SELECT id, device_id, gate_index FROM preset_gate_states ORDER BY device_id, gate_index"
        )
    ).mappings()
    gates_by_device: dict[int, list[dict[str, int]]] = {}
    for row in gate_rows:
        gates_by_device.setdefault(row["device_id"], []).append(dict(row))

    for device in devices:
        device_gates = gates_by_device.get(device["id"], [])
        needs_system = bool(
            device["supports_hh"] or device["gate_count"] is not None or device_gates
        )
        system_id: int | None = None
        if needs_system:
            system_id = bind.execute(
                sa.insert(material_systems)
                .values(
                    user_id=device["user_id"],
                    physical_printer_id=device["id"],
                    name="Legacy material system",
                    kind="mmu",
                    provider="happy_hare" if device["supports_hh"] else "legacy",
                    capabilities=CAPABILITIES_HH if device["supports_hh"] else [],
                    active=True,
                )
                .returning(material_systems.c.id)
            ).scalar_one()

            max_observed = max((row["gate_index"] for row in device_gates), default=-1) + 1
            slot_count = max(device["gate_count"] or 0, max_observed)
            slots_by_index: dict[int, int] = {}
            for provider_index in range(slot_count):
                slots_by_index[provider_index] = bind.execute(
                    sa.insert(material_slots)
                    .values(
                        user_id=device["user_id"],
                        material_system_id=system_id,
                        provider_index=provider_index,
                        label=None,
                        kind="slot",
                        active=True,
                    )
                    .returning(material_slots.c.id)
                ).scalar_one()
            for gate in device_gates:
                bind.execute(
                    sa.text(
                        "UPDATE preset_gate_states SET material_slot_id = :slot_id WHERE id = :id"
                    ),
                    {"slot_id": slots_by_index[gate["gate_index"]], "id": gate["id"]},
                )

        has_legacy_connector = bool(
            device["device_fingerprint"]
            or device["api_key"]
            or device["printer_hostname"]
            or device["supports_hh"]
        )
        if has_legacy_connector:
            bind.execute(
                sa.insert(connectors).values(
                    user_id=device["user_id"],
                    physical_printer_id=device["id"],
                    material_system_id=system_id,
                    provider="happy_hare" if device["supports_hh"] else "legacy",
                    transport="spoolman_compat" if device["api_key"] else "legacy_adapter",
                    capabilities=CAPABILITIES_HH if device["supports_hh"] else [],
                    active=True,
                    last_seen_at=device["last_seen_at"],
                )
            )


def downgrade() -> None:
    op.drop_index(
        "ix_preset_gate_states_material_slot_id", table_name="preset_gate_states"
    )
    op.drop_column("preset_gate_states", "material_slot_id")

    op.drop_index(
        "ix_physical_printer_connectors_material_system_id",
        table_name="physical_printer_connectors",
    )
    op.drop_index(
        "ix_physical_printer_connectors_physical_printer_id",
        table_name="physical_printer_connectors",
    )
    op.drop_index(
        "ix_physical_printer_connectors_user_id",
        table_name="physical_printer_connectors",
    )
    op.drop_table("physical_printer_connectors")

    op.drop_index("ix_material_slots_material_system_id", table_name="material_slots")
    op.drop_index("ix_material_slots_user_id", table_name="material_slots")
    op.drop_table("material_slots")

    op.drop_index(
        "ix_material_systems_physical_printer_id", table_name="material_systems"
    )
    op.drop_index("ix_material_systems_user_id", table_name="material_systems")
    op.drop_table("material_systems")

    op.drop_index(
        "ix_user_printer_profile_links_printer_profile_id",
        table_name="user_printer_profile_links",
    )
    op.drop_index(
        "ix_user_printer_profile_links_physical_printer_id",
        table_name="user_printer_profile_links",
    )
    op.drop_index(
        "ix_user_printer_profile_links_user_id",
        table_name="user_printer_profile_links",
    )
    op.drop_table("user_printer_profile_links")

    op.execute(
        sa.text(
            """
            UPDATE user_printer_devices
            SET device_fingerprint = 'manual-' || logical_id
            WHERE device_fingerprint IS NULL
            """
        )
    )
    op.alter_column(
        "user_printer_devices",
        "device_fingerprint",
        existing_type=sa.String(length=200),
        nullable=False,
    )
    op.drop_index(
        "ix_user_printer_devices_logical_id", table_name="user_printer_devices"
    )
    op.drop_column("user_printer_devices", "logical_id")
