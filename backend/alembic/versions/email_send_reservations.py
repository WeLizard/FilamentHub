"""Keep outbound email idempotency keys after a thread is deleted.

Revision ID: email_send_reservations
Revises: wiki_spaces_revisions
Create Date: 2026-08-02
"""

import sqlalchemy as sa

from alembic import op

revision = "email_send_reservations"
down_revision = "wiki_spaces_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_send_reservations",
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("idempotency_key"),
    )

    reservations = sa.table(
        "email_send_reservations",
        sa.column("idempotency_key", sa.String(length=128)),
    )
    messages = sa.table(
        "email_messages",
        sa.column("client_idempotency_key", sa.String(length=128)),
    )
    op.execute(
        reservations.insert().from_select(
            ["idempotency_key"],
            sa.select(messages.c.client_idempotency_key)
            .where(messages.c.client_idempotency_key.is_not(None))
            .distinct(),
        )
    )


def downgrade() -> None:
    op.drop_table("email_send_reservations")
