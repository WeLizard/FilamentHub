"""Clear active brand pointers without a matching membership.

Revision ID: active_brand_membership_only
Revises: email_communication_threads
Create Date: 2026-07-15
"""

from typing import Sequence, Union

from alembic import op

revision: str = "active_brand_membership_only"
down_revision: Union[str, None] = "email_communication_threads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Remove stale workspace selections without changing memberships."""
    op.execute(
        """
        UPDATE users AS u
        SET brand_id = NULL
        WHERE u.brand_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM brands AS b
              JOIN organizations AS o
                ON o.id = b.organization_id
               AND o.active IS TRUE
              JOIN organization_memberships AS om
                ON om.organization_id = o.id
               AND om.user_id = u.id
               AND om.active IS TRUE
              LEFT JOIN organization_brand_access AS oba
                ON oba.membership_id = om.id
               AND oba.brand_id = b.id
              WHERE b.id = u.brand_id
                AND b.active IS TRUE
                AND (om.all_brands IS TRUE OR oba.brand_id = b.id)
          )
        """
    )


def downgrade() -> None:
    """The invalid selections cannot be restored safely."""
