"""Replace legacy Orca schema triage statuses with reviewed.

Revision ID: orca_schema_review_status
Revises: review_printer_reference
Create Date: 2026-08-02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "orca_schema_review_status"
down_revision: Union[str, None] = "review_printer_reference"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE orca_schema_observations "
        "SET status = 'reviewed' "
        "WHERE status IN ('acknowledged', 'ignored')"
    )
    op.execute(
        "DELETE FROM orca_schema_observations "
        "WHERE id IN ("
        "SELECT id FROM ("
        "SELECT id, ROW_NUMBER() OVER ("
        "PARTITION BY scope, field_name "
        "ORDER BY last_seen_at DESC, id DESC"
        ") AS row_number FROM orca_schema_observations"
        ") AS ranked WHERE row_number > 1"
        ")"
    )
    with op.batch_alter_table("orca_schema_observations") as batch_op:
        batch_op.drop_constraint("uq_orca_schema_obs_field", type_="unique")
        batch_op.create_unique_constraint(
            "uq_orca_schema_obs_field",
            ["scope", "field_name"],
        )


def downgrade() -> None:
    with op.batch_alter_table("orca_schema_observations") as batch_op:
        batch_op.drop_constraint("uq_orca_schema_obs_field", type_="unique")
        batch_op.create_unique_constraint(
            "uq_orca_schema_obs_field",
            ["scope", "field_name", "value_shape"],
        )
    op.execute(
        "UPDATE orca_schema_observations "
        "SET status = 'acknowledged' "
        "WHERE status = 'reviewed'"
    )
