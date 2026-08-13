"""replace guessable endpoint hashes with keyed blind indexes

Revision ID: orca_endpoint_blind_indexes
Revises: orca_process_inherited_links
Create Date: 2026-08-13
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from urllib.parse import urlsplit

import sqlalchemy as sa

from alembic import op
from app.core.field_encryption import blind_index, decrypt_field

revision: str = "orca_endpoint_blind_indexes"
down_revision: str | None = "orca_process_inherited_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFAULT_PORTS = {
    "moonraker": 7125,
    "klipper": 7125,
    "mainsail": 7125,
    "fluidd": 7125,
    "octoprint": 5000,
    "prusalink": 80,
    "repetier": 80,
    "bambu": 8883,
}


def _canonical_endpoint(raw: str, provider: str | None) -> str:
    return f"{str(provider or 'generic').lower()}|{raw}"


def _blind_fingerprint(raw: str, provider: str | None) -> str:
    return blind_index(
        _canonical_endpoint(raw, provider),
        context="printer-endpoint-v1",
    )


def _legacy_fingerprint(raw: str, provider: str | None) -> str:
    return hashlib.sha256(
        _canonical_endpoint(raw, provider).encode("utf-8")
    ).hexdigest()


def _ref_storage_key(source_instance_id: str | None, connection_ref: str) -> str:
    stable = f"{source_instance_id or ''}|{connection_ref}"
    return "ref:" + hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _legacy_endpoint_storage_key(raw: str, provider: str | None) -> str:
    value = raw if "://" in raw else f"http://{raw}"
    parts = urlsplit(value)
    normalized_provider = str(provider or "generic").lower()
    port = parts.port or _DEFAULT_PORTS.get(normalized_provider)
    normalized = "|".join(
        [
            normalized_provider,
            (parts.scheme or "http").lower(),
            (parts.hostname or "").lower(),
            str(port or ""),
            (parts.path or "").rstrip("/"),
        ]
    )
    return "endpoint:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _tables() -> tuple[sa.TableClause, sa.TableClause]:
    observations = sa.table(
        "orca_printer_connection_observations",
        sa.column("id", sa.Integer()),
        sa.column("host_type", sa.String()),
        sa.column("endpoint_ciphertext", sa.Text()),
        sa.column("endpoint_fingerprint", sa.String()),
    )
    bindings = sa.table(
        "printer_connection_bindings",
        sa.column("id", sa.Integer()),
        sa.column("source_instance_id", sa.String()),
        sa.column("connection_ref", sa.String()),
        sa.column("provider", sa.String()),
        sa.column("normalized_endpoint", sa.String()),
        sa.column("endpoint_ciphertext", sa.Text()),
        sa.column("endpoint_fingerprint", sa.String()),
    )
    return observations, bindings


def upgrade() -> None:
    bind = op.get_bind()
    observations, bindings = _tables()

    for row in bind.execute(
        sa.select(observations).where(
            observations.c.endpoint_ciphertext.is_not(None)
        )
    ):
        raw = decrypt_field(row.endpoint_ciphertext)
        bind.execute(
            observations.update()
            .where(observations.c.id == row.id)
            .values(endpoint_fingerprint=_blind_fingerprint(raw, row.host_type))
        )

    for row in bind.execute(
        sa.select(bindings).where(bindings.c.endpoint_ciphertext.is_not(None))
    ):
        raw = decrypt_field(row.endpoint_ciphertext)
        endpoint_fingerprint = _blind_fingerprint(raw, row.provider)
        storage_key = (
            _ref_storage_key(row.source_instance_id, row.connection_ref)
            if row.connection_ref
            else f"endpoint:{endpoint_fingerprint}"
        )
        bind.execute(
            bindings.update()
            .where(bindings.c.id == row.id)
            .values(
                endpoint_fingerprint=endpoint_fingerprint,
                normalized_endpoint=storage_key,
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    observations, bindings = _tables()

    for row in bind.execute(
        sa.select(observations).where(
            observations.c.endpoint_ciphertext.is_not(None)
        )
    ):
        raw = decrypt_field(row.endpoint_ciphertext)
        bind.execute(
            observations.update()
            .where(observations.c.id == row.id)
            .values(endpoint_fingerprint=_legacy_fingerprint(raw, row.host_type))
        )

    for row in bind.execute(
        sa.select(bindings).where(bindings.c.endpoint_ciphertext.is_not(None))
    ):
        raw = decrypt_field(row.endpoint_ciphertext)
        storage_key = (
            _ref_storage_key(row.source_instance_id, row.connection_ref)
            if row.connection_ref
            else _legacy_endpoint_storage_key(raw, row.provider)
        )
        bind.execute(
            bindings.update()
            .where(bindings.c.id == row.id)
            .values(
                endpoint_fingerprint=_legacy_fingerprint(raw, row.provider),
                normalized_endpoint=storage_key,
            )
        )
