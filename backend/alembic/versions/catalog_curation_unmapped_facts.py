"""Keep manufacturer facts that the catalog card cannot represent."""

import sqlalchemy as sa

from alembic import op

revision = "catalog_curation_unmapped_facts"
down_revision = "catalog_curation_proposals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "catalog_curation_proposals",
        sa.Column(
            "unmapped_facts",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )
    op.add_column(
        "catalog_curation_proposals",
        sa.Column(
            "source_facts",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("catalog_curation_proposals", "source_facts")
    op.drop_column("catalog_curation_proposals", "unmapped_facts")
