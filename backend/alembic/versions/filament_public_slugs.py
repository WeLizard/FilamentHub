"""scope filament slugs to brands and preserve public aliases

Revision ID: filament_public_slugs
Revises: country_cell_catalog_statuses
Create Date: 2026-08-09
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "filament_public_slugs"
down_revision: str | None = "country_cell_catalog_statuses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CYRILLIC_TRANSLITERATION = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "i",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "shch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
        "і": "i",
        "ї": "yi",
        "є": "ye",
        "ґ": "g",
        "ў": "u",
    }
)


def _slugify(value: str, fallback: str = "filament") -> str:
    transliterated = value.casefold().translate(_CYRILLIC_TRANSLITERATION)
    normalized = unicodedata.normalize("NFKD", transliterated)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return (slug or fallback)[:200].strip("-") or fallback


def _candidate(name: str, color_name: str | None) -> str:
    name = name.strip()
    color = (color_name or "").strip()
    name_slug = _slugify(name)
    color_slug = _slugify(color, "") if color else ""
    if not color_slug or color_slug in name_slug.split("-") or name_slug.endswith(f"-{color_slug}"):
        return name_slug
    return _slugify(f"{name} {color}")


def upgrade() -> None:
    op.create_table(
        "filament_slug_redirects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("filament_id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("old_slug", sa.String(length=200), nullable=False),
        sa.Column(
            "reason",
            sa.String(length=20),
            server_default=sa.text("'rename'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["filament_id"], ["filaments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "brand_id",
            "old_slug",
            name="uq_filament_slug_redirect_brand_old",
        ),
    )
    op.create_index(
        "ix_filament_slug_redirect_brand",
        "filament_slug_redirects",
        ["brand_id"],
        unique=False,
    )
    op.create_index(
        "ix_filament_slug_redirect_filament",
        "filament_slug_redirects",
        ["filament_id"],
        unique=False,
    )

    op.drop_index("ix_filaments_slug", table_name="filaments")
    op.create_index("ix_filaments_slug", "filaments", ["slug"], unique=False)
    op.create_unique_constraint(
        "uq_filaments_brand_slug",
        "filaments",
        ["brand_id", "slug"],
    )

    bind = op.get_bind()
    rows = [
        dict(row._mapping)
        for row in bind.execute(
            sa.text(
                "SELECT id, brand_id, name, color_name, slug FROM filaments ORDER BY brand_id, id"
            )
        )
    ]
    desired_counts: dict[int, Counter[str]] = defaultdict(Counter)
    old_owners: dict[int, dict[str, int]] = defaultdict(dict)
    candidates: dict[int, str] = {}
    for row in rows:
        candidate = _candidate(row["name"], row["color_name"])
        candidates[row["id"]] = candidate
        desired_counts[row["brand_id"]][candidate] += 1
        old_owners[row["brand_id"]][row["slug"]] = row["id"]

    for row in rows:
        candidate = candidates[row["id"]]
        if candidate == row["slug"]:
            continue
        if desired_counts[row["brand_id"]][candidate] != 1:
            continue
        previous_owner = old_owners[row["brand_id"]].get(candidate)
        if previous_owner is not None and previous_owner != row["id"]:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO filament_slug_redirects "
                "(filament_id, brand_id, old_slug, reason) "
                "VALUES (:filament_id, :brand_id, :old_slug, 'backfill')"
            ),
            {
                "filament_id": row["id"],
                "brand_id": row["brand_id"],
                "old_slug": row["slug"],
            },
        )
        bind.execute(
            sa.text("UPDATE filaments SET slug = :slug WHERE id = :filament_id"),
            {"slug": candidate, "filament_id": row["id"]},
        )


def downgrade() -> None:
    bind = op.get_bind()
    aliases = [
        dict(row._mapping)
        for row in bind.execute(
            sa.text("SELECT filament_id, old_slug, reason FROM filament_slug_redirects ORDER BY id")
        )
    ]
    if any(alias["reason"] != "backfill" for alias in aliases):
        raise RuntimeError(
            "Cannot downgrade filament slugs after a published slug rename; "
            "historical redirects would be lost."
        )

    original_by_filament = {alias["filament_id"]: alias["old_slug"] for alias in aliases}
    current_rows = [
        dict(row._mapping)
        for row in bind.execute(sa.text("SELECT id, slug FROM filaments ORDER BY id"))
    ]
    proposed = [original_by_filament.get(row["id"], row["slug"]) for row in current_rows]
    duplicates = [slug for slug, count in Counter(proposed).items() if count > 1]
    if duplicates:
        raise RuntimeError(
            "Cannot restore globally unique filament slugs; duplicates now exist: "
            + ", ".join(sorted(duplicates)[:10])
        )

    for filament_id, old_slug in original_by_filament.items():
        bind.execute(
            sa.text("UPDATE filaments SET slug = :slug WHERE id = :filament_id"),
            {"slug": old_slug, "filament_id": filament_id},
        )

    op.drop_constraint("uq_filaments_brand_slug", "filaments", type_="unique")
    op.drop_index("ix_filaments_slug", table_name="filaments")
    op.create_index("ix_filaments_slug", "filaments", ["slug"], unique=True)
    op.drop_index(
        "ix_filament_slug_redirect_filament",
        table_name="filament_slug_redirects",
    )
    op.drop_index(
        "ix_filament_slug_redirect_brand",
        table_name="filament_slug_redirects",
    )
    op.drop_table("filament_slug_redirects")
