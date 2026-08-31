"""Add canonical spool tags and tag evidence on slot observations.

Revision ID: spool_tag_identity
Revises: edge_connector_node
"""

from __future__ import annotations

import json
import re

import sqlalchemy as sa

from alembic import op

revision = "spool_tag_identity"
down_revision = "edge_connector_node"
branch_labels = None
depends_on = None

_SEPARATORS = re.compile(r"[\s:_.-]+")


def _normalize_uid(value: str) -> str:
    normalized = _SEPARATORS.sub("", value).strip().upper().removeprefix("0X")
    if not normalized or re.fullmatch(r"[0-9A-F]+", normalized) is None:
        raise RuntimeError("Existing rfid_tag contains a non-hexadecimal UID")
    if len(normalized) % 2:
        raise RuntimeError("Existing rfid_tag UID does not contain complete bytes")
    if len(normalized) > 64:
        raise RuntimeError("Existing rfid_tag UID exceeds 64 hexadecimal characters")
    return normalized


def _parse_legacy(value: object) -> list[str]:
    decoded = value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            decoded = value
    if decoded in (None, ""):
        return []
    if isinstance(decoded, str):
        values = decoded.split(",")
    elif isinstance(decoded, list) and all(isinstance(item, str) for item in decoded):
        values = decoded
    else:
        raise RuntimeError("Existing rfid_tag must be a string or a list of strings")
    return list(dict.fromkeys(_normalize_uid(item) for item in values if item.strip()))


def upgrade() -> None:
    op.create_table(
        "spool_tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("spool_id", sa.Integer(), nullable=False),
        sa.Column("uid", sa.String(length=64), nullable=False),
        sa.Column("technology", sa.String(length=16), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["spool_id"], ["user_spools.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "uid", name="uq_spool_tag_user_uid"),
    )
    op.create_index("ix_spool_tag_user_spool", "spool_tags", ["user_id", "spool_id"])
    for column in (
        sa.Column("tag_uid", sa.String(length=64), nullable=True),
        sa.Column("tag_technology", sa.String(length=16), nullable=True),
        sa.Column("tag_format", sa.String(length=32), nullable=True),
        sa.Column("tag_match_status", sa.String(length=16), nullable=True),
    ):
        op.add_column("material_slot_observations", column)

    bind = op.get_bind()
    spools = sa.table(
        "user_spools",
        sa.column("id", sa.Integer()),
        sa.column("user_id", sa.Integer()),
        sa.column("extra", sa.JSON()),
    )
    tags = sa.table(
        "spool_tags",
        sa.column("user_id", sa.Integer()),
        sa.column("spool_id", sa.Integer()),
        sa.column("uid", sa.String(length=64)),
        sa.column("technology", sa.String(length=16)),
        sa.column("format", sa.String(length=32)),
        sa.column("source", sa.String(length=40)),
    )
    seen: dict[tuple[int, str], int] = {}
    for row in bind.execute(sa.select(spools.c.id, spools.c.user_id, spools.c.extra)):
        extra = dict(row.extra or {})
        if "rfid_tag" not in extra:
            continue
        for uid in _parse_legacy(extra.pop("rfid_tag")):
            key = (row.user_id, uid)
            if key in seen and seen[key] != row.id:
                raise RuntimeError(
                    f"Existing RFID UID {uid} is linked to multiple spools for user {row.user_id}"
                )
            seen[key] = row.id
            bind.execute(
                tags.insert().values(
                    user_id=row.user_id,
                    spool_id=row.id,
                    uid=uid,
                    technology="unknown",
                    format=None,
                    source="legacy_hh_extra",
                )
            )
        bind.execute(spools.update().where(spools.c.id == row.id).values(extra=extra))


def downgrade() -> None:
    bind = op.get_bind()
    spools = sa.table(
        "user_spools",
        sa.column("id", sa.Integer()),
        sa.column("extra", sa.JSON()),
    )
    tags = sa.table(
        "spool_tags",
        sa.column("spool_id", sa.Integer()),
        sa.column("uid", sa.String(length=64)),
    )
    by_spool: dict[int, list[str]] = {}
    for row in bind.execute(sa.select(tags.c.spool_id, tags.c.uid).order_by(tags.c.spool_id, tags.c.uid)):
        by_spool.setdefault(row.spool_id, []).append(row.uid)
    for spool_id, uids in by_spool.items():
        extra = dict(bind.execute(sa.select(spools.c.extra).where(spools.c.id == spool_id)).scalar() or {})
        extra["rfid_tag"] = json.dumps(",".join(uids))
        bind.execute(spools.update().where(spools.c.id == spool_id).values(extra=extra))

    for column in ("tag_match_status", "tag_format", "tag_technology", "tag_uid"):
        op.drop_column("material_slot_observations", column)
    op.drop_index("ix_spool_tag_user_spool", table_name="spool_tags")
    op.drop_table("spool_tags")
