"""preserve Orca import evidence and organization provenance

Revision ID: preset_import_provenance
Revises: crm_order_no_quote
"""

import sqlalchemy as sa

from alembic import op

revision = "preset_import_provenance"
down_revision = "crm_order_no_quote"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("presets", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.add_column("presets", sa.Column("import_evidence", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "fk_presets_organization_id_organizations",
        "presets",
        "organizations",
        ["organization_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_presets_organization_id",
        "presets",
        ["organization_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_presets_organization_id", table_name="presets")
    op.drop_constraint(
        "fk_presets_organization_id_organizations",
        "presets",
        type_="foreignkey",
    )
    op.drop_column("presets", "import_evidence")
    op.drop_column("presets", "organization_id")
