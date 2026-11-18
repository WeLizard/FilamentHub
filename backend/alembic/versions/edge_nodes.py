"""Edge nodes: account-owned installations with their own credential and pairing codes.

Revision ID: edge_nodes
Revises: subscription_withdrawn
"""

import sqlalchemy as sa

from alembic import op

revision = "edge_nodes"
down_revision = "subscription_withdrawn"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "edge_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("kit_id", sa.String(64), nullable=True),
        sa.Column("node_instance_id", sa.String(100), nullable=True),
        sa.Column("runtime_version", sa.String(50), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_edge_nodes_user_id", "edge_nodes", ["user_id"])

    op.create_table(
        "edge_node_credentials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "node_id",
            sa.Integer(),
            sa.ForeignKey("edge_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("credential_generation", sa.Integer(), server_default="1", nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("node_id", name="uq_edge_node_credentials_node"),
        sa.UniqueConstraint("token_hash", name="uq_edge_node_credentials_token"),
    )

    op.create_table(
        "edge_node_pairings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "node_id",
            sa.Integer(),
            sa.ForeignKey("edge_nodes.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("kit_id", sa.String(64), nullable=True),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proof_hash", sa.String(64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("code_hash", name="uq_edge_node_pairings_code"),
    )
    op.create_index("ix_edge_node_pairings_user_id", "edge_node_pairings", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_edge_node_pairings_user_id", table_name="edge_node_pairings")
    op.drop_table("edge_node_pairings")
    op.drop_table("edge_node_credentials")
    op.drop_index("ix_edge_nodes_user_id", table_name="edge_nodes")
    op.drop_table("edge_nodes")
