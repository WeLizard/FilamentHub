"""Add private session labels, sampled activity and legacy revocation boundaries.

Revision ID: account_active_sessions
Revises: calculator_gcode_artifacts
"""

import sqlalchemy as sa

from alembic import op

revision = "account_active_sessions"
down_revision = "calculator_gcode_artifacts"
branch_labels = None
depends_on = None

_OLD_REASONS = (
    "'recovery_grant', 'authenticated_change', 'logout', 'refresh_reuse', 'admin_block', "
    "'admin_promote', 'admin_demote', 'admin_delete', 'admin_email_code'"
)
_NEW_REASONS = f"{_OLD_REASONS}, 'session_revoke', 'other_sessions_revoke'"
_PENDING_CONSTRAINT = "ck_audit_events_reason_sessions_pending"


def _prepare_reason_constraint(reasons: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    # PostgreSQL retains ADD CHECK's ACCESS EXCLUSIVE lock until commit even
    # with NOT VALID. Release it before VALIDATE's scan, which permits DML.
    # No column changes precede these explicit commits: a failed later phase
    # leaves the original schema plus a safely replaceable temporary check.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TABLE audit_events "
            f"DROP CONSTRAINT IF EXISTS {_PENDING_CONSTRAINT}, "
            f"ADD CONSTRAINT {_PENDING_CONSTRAINT} CHECK (reason IN ({reasons})) NOT VALID"
        )
    try:
        with op.get_context().autocommit_block():
            op.execute(f"ALTER TABLE audit_events VALIDATE CONSTRAINT {_PENDING_CONSTRAINT}")
    except Exception:
        # In particular, a racing new audit during downgrade must not leave
        # an unvalidated narrower constraint rejecting otherwise valid writes.
        with op.get_context().autocommit_block():
            op.execute(f"ALTER TABLE audit_events DROP CONSTRAINT IF EXISTS {_PENDING_CONSTRAINT}")
        raise


def _replace_reason_constraint(reasons: str) -> None:
    if op.get_bind().dialect.name == "postgresql":
        # All potentially waiting column DDL precedes this short final swap.
        # The validated replacement continuously enforces the reason contract.
        op.drop_constraint("ck_audit_events_reason", "audit_events", type_="check")
        op.execute(
            f"ALTER TABLE audit_events RENAME CONSTRAINT {_PENDING_CONSTRAINT} "
            "TO ck_audit_events_reason"
        )
    else:
        with op.batch_alter_table("audit_events") as batch:
            batch.drop_constraint("ck_audit_events_reason", type_="check")
            batch.create_check_constraint("ck_audit_events_reason", f"reason IN ({reasons})")


def upgrade() -> None:
    _prepare_reason_constraint(_NEW_REASONS)
    op.add_column("users", sa.Column("legacy_access_revoked_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("legacy_refresh_disabled_at", sa.DateTime(timezone=True)))
    op.add_column("refresh_sessions", sa.Column("last_seen_at", sa.DateTime(timezone=True)))
    for name in ("browser", "os", "device_type"):
        op.add_column(
            "refresh_sessions",
            sa.Column(name, sa.String(16), nullable=False, server_default="unknown"),
        )
    _replace_reason_constraint(_NEW_REASONS)


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT COUNT(*) FROM audit_events WHERE reason IN "
            "('session_revoke', 'other_sessions_revoke')"
        )
    ):
        raise RuntimeError("Cannot downgrade while session revocation audit events exist")
    if op.get_bind().scalar(
        sa.text(
            "SELECT COUNT(*) FROM users WHERE legacy_access_revoked_at IS NOT NULL "
            "OR legacy_refresh_disabled_at IS NOT NULL"
        )
    ):
        raise RuntimeError("Cannot downgrade a persisted legacy session revocation boundary")
    _prepare_reason_constraint(_OLD_REASONS)
    for name in ("device_type", "os", "browser", "last_seen_at"):
        op.drop_column("refresh_sessions", name)
    op.drop_column("users", "legacy_refresh_disabled_at")
    op.drop_column("users", "legacy_access_revoked_at")
    _replace_reason_constraint(_OLD_REASONS)
