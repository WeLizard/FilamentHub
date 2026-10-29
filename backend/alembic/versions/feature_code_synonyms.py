"""Stored feature spellings become their codes; Silk products get the silk finish.

Revision ID: feature_code_synonyms
Revises: material_plus_subtypes

Effects, finish, colour type, additives and claims written before the synonym
dictionary existed may hold another spelling of a known code ("glass fibre",
"sparkle"). They are rewritten to the code from ``app.services.filament_features``,
which the schema now applies on every write. Unknown custom codes stay as they
are. A glossy filament whose name has the word Silk gets the new silk finish.
"""

import re

import sqlalchemy as sa

from alembic import op
from app.services.filament_features import canonical_code, known_codes

revision = "feature_code_synonyms"
down_revision = "material_plus_subtypes"
branch_labels = None
depends_on = None

_SILK_WORD = re.compile(r"(?<![^\W_])(silk|шелк|шёлк|丝绸)(?![^\W_])", re.IGNORECASE)

filaments = sa.table(
    "filaments",
    sa.column("id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("visual_settings", sa.JSON),
    sa.column("additives", sa.JSON),
    sa.column("property_claims", sa.JSON),
)


def _known(kind, value):
    code = canonical_code(kind, value)
    return code if code in known_codes(kind) else value


def _visual(settings: dict, name: str) -> dict:
    result = dict(settings)
    for field, kind in (("finish", "finish"), ("color_type", "color_type"), ("filler", "effect")):
        if isinstance(result.get(field), str):
            result[field] = _known(kind, result[field])
    if isinstance(result.get("effects"), list):
        result["effects"] = list(
            dict.fromkeys(_known("effect", item) for item in result["effects"])
        )
    if result.get("finish") == "glossy" and _SILK_WORD.search(name or ""):
        result["finish"] = "silk"
    return result


def _coded(items: list, kind: str) -> list:
    result, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            result.append(item)
            continue
        code = _known(kind, item.get("code"))
        if code in seen:
            continue
        seen.add(code)
        result.append({**item, "code": code})
    return result


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.select(
            filaments.c.id,
            filaments.c.name,
            filaments.c.visual_settings,
            filaments.c.additives,
            filaments.c.property_claims,
        )
    ).all()
    for filament_id, name, visual, additives, claims in rows:
        values = {}
        if isinstance(visual, dict) and (new := _visual(visual, name)) != visual:
            values["visual_settings"] = new
        if isinstance(additives, list) and (new := _coded(additives, "additive")) != additives:
            values["additives"] = new
        if isinstance(claims, list) and (new := _coded(claims, "claim")) != claims:
            values["property_claims"] = new
        if values:
            bind.execute(filaments.update().where(filaments.c.id == filament_id).values(**values))


def downgrade() -> None:
    # Codes stay: they are the same values in canonical spelling. Values the
    # previous schema rejects go back to the nearest value it accepts.
    fallback = {
        "finish": {"silk": "glossy", "satin": "matte"},
        "color_type": {"four": "transition"},
    }
    bind = op.get_bind()
    rows = bind.execute(sa.select(filaments.c.id, filaments.c.visual_settings)).all()
    for filament_id, visual in rows:
        if not isinstance(visual, dict):
            continue
        new = dict(visual)
        for field, mapping in fallback.items():
            if new.get(field) in mapping:
                new[field] = mapping[new[field]]
        if new != visual:
            bind.execute(
                filaments.update().where(filaments.c.id == filament_id).values(visual_settings=new)
            )
