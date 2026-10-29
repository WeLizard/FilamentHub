"""Filaments typed ABS HF / high flow before the subtype existed get it."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa

from alembic.migration import MigrationContext
from alembic.operations import Operations


def _migration_module():
    path = Path(__file__).parents[1] / "alembic" / "versions" / "material_abs_hf.py"
    spec = importlib.util.spec_from_file_location("material_abs_hf_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_gives_high_flow_abs_its_subtype() -> None:
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
                "INSERT INTO filaments VALUES (1, 'ABS High Flow', 'ABS', NULL), "
                "(2, 'ABS', 'ABS', 'ABS')"
            )
        )

        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            rows = connection.execute(
                sa.text("SELECT id, material_subtype FROM filaments ORDER BY id")
            ).all()
            assert rows == [(1, "ABS HF"), (2, "ABS")]
            seeded = connection.execute(
                sa.text("SELECT material_type, base_type FROM material_properties")
            ).all()
            assert seeded == [("ABS HF", "ABS")]

            migration.downgrade()
            assert (
                connection.execute(
                    sa.text("SELECT material_subtype FROM filaments WHERE id = 1")
                ).scalar()
                is None
            )
