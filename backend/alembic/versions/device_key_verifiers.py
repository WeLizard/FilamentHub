"""Replace legacy device API keys with non-bearer verifiers.

Revision ID: device_key_verifiers
Revises: repair_seeded_sequences
"""

from __future__ import annotations

import base64
import hashlib
import re

import sqlalchemy as sa

from alembic import op

revision = "device_key_verifiers"
down_revision = "repair_seeded_sequences"
branch_labels = None
depends_on = None

_PREFIX = "fhk1:"
_VALID_VERIFIER = re.compile(r"^fhk1:[A-Za-z0-9_-]{43}$")
_CONSTRAINT = "ck_user_printer_device_key_verifier"
_CHECK = "api_key IS NULL OR (length(api_key) = 48 AND api_key LIKE 'fhk1:%')"


def _device_api_key_verifier(api_key: str) -> str:
    digest = hashlib.sha256(api_key.encode("utf-8")).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"{_PREFIX}{encoded}"


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, api_key FROM user_printer_devices "
            "WHERE api_key IS NOT NULL ORDER BY id"
        )
    ).mappings()

    for row in rows:
        stored_value = row["api_key"]
        if _VALID_VERIFIER.fullmatch(stored_value):
            continue
        if stored_value.startswith(_PREFIX):
            raise RuntimeError(
                "user_printer_devices contains an invalid tagged API-key verifier"
            )

        # Match the old value as well as the row id: a concurrent writer may
        # already have replaced this legacy key with a valid verifier.
        bind.execute(
            sa.text(
                "UPDATE user_printer_devices SET api_key = :verifier "
                "WHERE id = :device_id AND api_key = :legacy_key"
            ),
            {
                "device_id": row["id"],
                "legacy_key": stored_value,
                "verifier": _device_api_key_verifier(stored_value),
            },
        )

    invalid_count = bind.scalar(
        sa.text(
            "SELECT count(*) FROM user_printer_devices "
            f"WHERE api_key IS NOT NULL AND NOT ({_CHECK})"
        )
    )
    if invalid_count:
        raise RuntimeError(
            "device API-key backfill left values outside the verifier contract"
        )

    op.create_check_constraint(
        _CONSTRAINT,
        "user_printer_devices",
        _CHECK,
    )


def downgrade() -> None:
    op.drop_constraint(
        _CONSTRAINT,
        "user_printer_devices",
        type_="check",
    )
    # SHA-256 verifiers intentionally cannot be converted back to bearer keys.
