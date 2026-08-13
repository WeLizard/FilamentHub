"""add inherited process links and private Orca connection identity

Revision ID: orca_printer_identity_v2
Revises: wiki_guide_progress
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence
from urllib.parse import urlsplit

import sqlalchemy as sa

from alembic import op
from app.core.field_encryption import blind_index, decrypt_field, encrypt_field

revision: str = "orca_printer_identity_v2"
down_revision: str | None = "wiki_guide_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _fingerprint(value: str, provider: str | None = None) -> str:
    canonical = f"{str(provider or 'generic').lower()}|{value}"
    return blind_index(canonical, context="printer-endpoint-v1")


def _binding_raw_endpoint(row: sa.Row) -> str:
    if row.print_host:
        return str(row.print_host)
    if not row.host:
        return ""
    scheme = str(row.scheme or "http")
    authority = str(row.host)
    if row.port:
        authority += f":{row.port}"
    return f"{scheme}://{authority}{row.path or ''}"


def _normalized_endpoint(raw: str, provider: str | None) -> tuple[str, dict]:
    value = raw if "://" in raw else f"http://{raw}"
    parts = urlsplit(value)
    scheme = (parts.scheme or "http").lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    defaults = {
        "moonraker": 7125,
        "klipper": 7125,
        "mainsail": 7125,
        "fluidd": 7125,
        "octoprint": 5000,
        "prusalink": 80,
        "repetier": 80,
        "bambu": 8883,
    }
    if port is None:
        port = defaults.get(str(provider or "").lower())
    path = (parts.path or "").rstrip("/")
    normalized = "|".join(
        [str(provider or "generic").lower(), scheme, host, str(port or ""), path]
    )
    return normalized, {
        "scheme": scheme,
        "host": host,
        "port": port,
        "path": path,
    }


def upgrade() -> None:
    op.add_column(
        "print_profile_configuration_links",
        sa.Column(
            "relation_type",
            sa.String(length=32),
            server_default="explicit",
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column("sync_printer_endpoints", sa.Boolean(), nullable=True),
    )

    op.add_column(
        "orca_printer_connection_observations",
        sa.Column("connection_ref", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "orca_printer_connection_observations",
        sa.Column("endpoint_ciphertext", sa.Text(), nullable=True),
    )
    op.add_column(
        "orca_printer_connection_observations",
        sa.Column("endpoint_fingerprint", sa.String(length=64), nullable=True),
    )

    op.add_column(
        "printer_connection_bindings",
        sa.Column("source_instance_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "printer_connection_bindings",
        sa.Column("connection_ref", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "printer_connection_bindings",
        sa.Column("endpoint_ciphertext", sa.Text(), nullable=True),
    )
    op.add_column(
        "printer_connection_bindings",
        sa.Column("endpoint_fingerprint", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uq_pcb_user_source_connection_ref",
        "printer_connection_bindings",
        ["user_id", "source_instance_id", "connection_ref"],
        unique=True,
    )

    bind = op.get_bind()
    observations = sa.table(
        "orca_printer_connection_observations",
        sa.column("id", sa.Integer()),
        sa.column("print_host", sa.String()),
        sa.column("host_type", sa.String()),
        sa.column("endpoint_ciphertext", sa.Text()),
        sa.column("endpoint_fingerprint", sa.String()),
    )
    for row in bind.execute(
        sa.select(
            observations.c.id,
            observations.c.print_host,
            observations.c.host_type,
        ).where(
            observations.c.print_host.is_not(None)
        )
    ):
        raw = str(row.print_host or "")
        bind.execute(
            observations.update()
            .where(observations.c.id == row.id)
            .values(
                print_host=None,
                endpoint_ciphertext=encrypt_field(raw) if raw else None,
                endpoint_fingerprint=(
                    _fingerprint(raw, row.host_type) if raw else None
                ),
            )
        )

    bindings = sa.table(
        "printer_connection_bindings",
        sa.column("id", sa.Integer()),
        sa.column("normalized_endpoint", sa.String()),
        sa.column("provider", sa.String()),
        sa.column("scheme", sa.String()),
        sa.column("host", sa.String()),
        sa.column("port", sa.Integer()),
        sa.column("path", sa.String()),
        sa.column("print_host", sa.String()),
        sa.column("endpoint_ciphertext", sa.Text()),
        sa.column("endpoint_fingerprint", sa.String()),
    )
    for row in bind.execute(sa.select(bindings)):
        raw = _binding_raw_endpoint(row)
        endpoint_fingerprint = _fingerprint(raw, row.provider) if raw else None
        bind.execute(
            bindings.update()
            .where(bindings.c.id == row.id)
            .values(
                normalized_endpoint=f"endpoint:{endpoint_fingerprint or 'unknown'}",
                scheme=None,
                host=None,
                port=None,
                path=None,
                print_host=None,
                endpoint_ciphertext=encrypt_field(raw) if raw else None,
                endpoint_fingerprint=endpoint_fingerprint,
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    observations = sa.table(
        "orca_printer_connection_observations",
        sa.column("id", sa.Integer()),
        sa.column("print_host", sa.String()),
        sa.column("endpoint_ciphertext", sa.Text()),
    )
    for row in bind.execute(
        sa.select(observations.c.id, observations.c.endpoint_ciphertext).where(
            observations.c.endpoint_ciphertext.is_not(None)
        )
    ):
        bind.execute(
            observations.update()
            .where(observations.c.id == row.id)
            .values(print_host=decrypt_field(row.endpoint_ciphertext))
        )

    bindings = sa.table(
        "printer_connection_bindings",
        sa.column("id", sa.Integer()),
        sa.column("normalized_endpoint", sa.String()),
        sa.column("provider", sa.String()),
        sa.column("scheme", sa.String()),
        sa.column("host", sa.String()),
        sa.column("port", sa.Integer()),
        sa.column("path", sa.String()),
        sa.column("print_host", sa.String()),
        sa.column("endpoint_ciphertext", sa.Text()),
    )
    for row in bind.execute(
        sa.select(bindings).where(bindings.c.endpoint_ciphertext.is_not(None))
    ):
        raw = decrypt_field(row.endpoint_ciphertext)
        normalized, parsed = _normalized_endpoint(raw, row.provider)
        bind.execute(
            bindings.update()
            .where(bindings.c.id == row.id)
            .values(
                normalized_endpoint=normalized,
                scheme=parsed["scheme"],
                host=parsed["host"],
                port=parsed["port"],
                path=parsed["path"],
                print_host=raw,
            )
        )

    op.drop_index(
        "uq_pcb_user_source_connection_ref",
        table_name="printer_connection_bindings",
    )
    op.drop_column("printer_connection_bindings", "endpoint_fingerprint")
    op.drop_column("printer_connection_bindings", "endpoint_ciphertext")
    op.drop_column("printer_connection_bindings", "connection_ref")
    op.drop_column("printer_connection_bindings", "source_instance_id")
    op.drop_column("orca_printer_connection_observations", "endpoint_fingerprint")
    op.drop_column("orca_printer_connection_observations", "endpoint_ciphertext")
    op.drop_column("orca_printer_connection_observations", "connection_ref")
    op.drop_column("users", "sync_printer_endpoints")
    op.drop_column("print_profile_configuration_links", "relation_type")
