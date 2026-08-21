"""unify legacy badges with audited user achievements

Revision ID: unify_user_achievements
Revises: preset_contribution_motivation
"""

import json

import sqlalchemy as sa

from alembic import op

revision = "unify_user_achievements"
down_revision = "preset_contribution_motivation"
branch_labels = None
depends_on = None


LEGACY_BADGE_CODES = {
    "founder": "project_founder",
    "beta_tester": "beta_tester",
    "contributor": "project_contributor",
    "supporter": "project_supporter",
    "early_adopter": "early_adopter",
}


def _badge_list(raw_badges: object) -> list[str]:
    if isinstance(raw_badges, list):
        return [str(item) for item in raw_badges]
    if isinstance(raw_badges, str):
        try:
            decoded = json.loads(raw_badges)
        except json.JSONDecodeError:
            return []
        if isinstance(decoded, list):
            return [str(item) for item in decoded]
    return []


def upgrade() -> None:
    with op.batch_alter_table("user_achievements") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source",
                sa.String(length=24),
                server_default="automatic",
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("awarded_by_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("award_reason", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("revoked_by_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("revoke_reason", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_user_achievements_awarded_by_user_id_users",
            "users",
            ["awarded_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_user_achievements_revoked_by_user_id_users",
            "users",
            ["revoked_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    bind = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("badges", sa.JSON()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    achievements = sa.table(
        "user_achievements",
        sa.column("user_id", sa.Integer()),
        sa.column("code", sa.String()),
        sa.column("source", sa.String()),
        sa.column("evidence_type", sa.String()),
        sa.column("earned_at", sa.DateTime(timezone=True)),
        sa.column("award_reason", sa.Text()),
    )
    for user_id, raw_badges, created_at in bind.execute(
        sa.select(users.c.id, users.c.badges, users.c.created_at).where(users.c.badges.is_not(None))
    ):
        for legacy_code in _badge_list(raw_badges):
            achievement_code = LEGACY_BADGE_CODES.get(legacy_code)
            if achievement_code is None:
                # Legacy `verified` described a brand relationship and is kept
                # only in users.badges as rollback evidence. It must not become
                # a personal public distinction.
                continue
            exists = bind.scalar(
                sa.select(sa.func.count())
                .select_from(achievements)
                .where(
                    achievements.c.user_id == user_id,
                    achievements.c.code == achievement_code,
                )
            )
            if exists:
                continue
            bind.execute(
                achievements.insert().values(
                    user_id=user_id,
                    code=achievement_code,
                    source="migration",
                    evidence_type="legacy_badge",
                    earned_at=created_at,
                    award_reason=f"legacy_badge:{legacy_code}",
                )
            )


def downgrade() -> None:
    with op.batch_alter_table("user_achievements") as batch_op:
        batch_op.drop_constraint(
            "fk_user_achievements_revoked_by_user_id_users",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_user_achievements_awarded_by_user_id_users",
            type_="foreignkey",
        )
        batch_op.drop_column("revoke_reason")
        batch_op.drop_column("revoked_by_user_id")
        batch_op.drop_column("revoked_at")
        batch_op.drop_column("award_reason")
        batch_op.drop_column("awarded_by_user_id")
        batch_op.drop_column("source")
