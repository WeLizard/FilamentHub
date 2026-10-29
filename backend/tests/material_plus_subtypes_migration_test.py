"""Filaments typed before ABS+/PETG+/ASA+ joined the reference get their subtype."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "material_plus_subtypes.py"
    spec = importlib.util.spec_from_file_location("material_plus_subtypes_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_rederives_stored_subtypes_and_seeds_reference() -> None:
    migration = _migration_module()
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "CREATE TABLE filaments (id INTEGER PRIMARY KEY, material_type TEXT, "
                "base_material_type TEXT, material_subtype TEXT)"
            )
        )
        connection.execute(
            sa.text(
                "CREATE TABLE material_properties (material_type TEXT PRIMARY KEY, "
                "display_name TEXT, base_type TEXT, aliases JSON, wiki_article_slug TEXT)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO filaments VALUES (1, 'PETG+', 'PETG', NULL), "
                "(2, 'ABS Plus', 'ABS', NULL), (3, 'PLA', 'PLA', 'PLA'), "
                "(4, 'ASA+ CF', 'ASA', NULL)"
            )
        )

        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            rows = connection.execute(
                sa.text(
                    "SELECT id, base_material_type, material_subtype FROM filaments ORDER BY id"
                )
            ).all()
            assert rows == [
                (1, "PETG", "PETG+"),
                (2, "ABS", "ABS+"),
                (3, "PLA", "PLA"),
                (4, "ASA", "ASA+"),
            ]
            seeded = connection.execute(
                sa.text("SELECT material_type, base_type FROM material_properties ORDER BY 1")
            ).all()
            assert seeded == [("ABS+", "ABS"), ("ASA+", "ASA"), ("PETG+", "PETG")]

            migration.downgrade()
            assert (
                connection.execute(
                    sa.text("SELECT count(*) FROM filaments WHERE material_subtype LIKE '%+'")
                ).scalar()
                == 0
            )
            assert (
                connection.execute(sa.text("SELECT count(*) FROM material_properties")).scalar()
                == 0
            )
