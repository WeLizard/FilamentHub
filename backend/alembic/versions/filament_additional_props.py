"""Store reviewed manufacturer facts on exact filament variants."""

import sqlalchemy as sa

from alembic import op

revision = "filament_additional_props"
down_revision = "catalog_cur_svc_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "filaments",
        sa.Column(
            "additional_properties",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("filaments", "additional_properties")
