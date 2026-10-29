"""Stored feature spellings are rewritten to codes without touching custom values."""

import importlib.util
import json
from pathlib import Path

import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "feature_code_synonyms.py"
    spec = importlib.util.spec_from_file_location("feature_code_synonyms_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(connection, filament_id):
    visual, additives, claims = connection.execute(
        sa.text("SELECT visual_settings, additives, property_claims FROM filaments WHERE id = :id"),
        {"id": filament_id},
    ).one()
    return json.loads(visual), json.loads(additives), json.loads(claims)


def test_upgrade_rewrites_spellings_and_downgrade_keeps_old_schema_valid() -> None:
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE filaments (id INTEGER PRIMARY KEY, name TEXT, "
                "visual_settings JSON, additives JSON, property_claims JSON)"
            )
        )
        rows = [
            (
                1,
                "PLA Silk Gold",
                {
                    "finish": "glossy",
                    "filler": "sparkle",
                    "effects": ["sparkle", "glitter", "my_custom"],
                },
                [{"code": "glass fibre", "content_percent": 20}, {"code": "GF"}],
                [{"code": "esd safe"}],
            ),
            (2, "PLA Basic", {"finish": "glossy", "effects": []}, [], []),
        ]
        for filament_id, name, visual, additives, claims in rows:
            connection.execute(
                sa.text("INSERT INTO filaments VALUES (:id, :name, :v, :a, :c)"),
                {
                    "id": filament_id,
                    "name": name,
                    "v": json.dumps(visual),
                    "a": json.dumps(additives),
                    "c": json.dumps(claims),
                },
            )

        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            visual, additives, claims = _row(connection, 1)
            assert visual["finish"] == "silk"
            assert visual["filler"] == "glitter"
            assert visual["effects"] == ["glitter", "my_custom"]
            assert additives == [{"code": "glass_fiber", "content_percent": 20}]
            assert claims == [{"code": "esd"}]
            assert _row(connection, 2)[0]["finish"] == "glossy"

            migration.downgrade()
            assert _row(connection, 1)[0]["finish"] == "glossy"
