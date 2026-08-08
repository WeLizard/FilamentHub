"""A brand's own workspace holds its authority as a grant, like everyone else.

Revision ID: workspace_global_grants
Revises: brand_invite_territory
Create Date: 2026-08-08

Authority over a brand used to have two sources: a territorial grant, and the
older link from the brand to one organization. Screens asked one of them, the
country cells asked the other, and they disagreed.

This turns the second into the first. The workspace organization of every
verified brand receives the global grant its approval always meant — before
today there was no way to claim one country, so becoming that workspace's owner
was a claim on the mark itself. Unverified brands are left alone: nobody proved
ownership there.

Nobody gains access they did not already have; what was implicit becomes
visible.
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "workspace_global_grants"
down_revision: Union[str, None] = "brand_invite_territory"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO brand_territorial_grants (
                brand_id, organization_id, country, status, source,
                manage_brand_country, manage_filament_country, create_filaments,
                edit_own_created_filaments, edit_brand_common,
                edit_all_filaments_common, approved_at, created_at, updated_at
            )
            SELECT b.id, b.organization_id, NULL, 'active', 'application',
                   true, true, true, true, true, true, NOW(), NOW(), NOW()
            FROM brands b
            WHERE b.organization_id IS NOT NULL
              AND b.verified IS TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM brand_territorial_grants g
                  WHERE g.brand_id = b.id
                    AND g.organization_id = b.organization_id
                    AND g.country IS NULL
              )
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM brand_territorial_grants g
            USING brands b
            WHERE g.brand_id = b.id
              AND g.organization_id = b.organization_id
              AND g.country IS NULL
              AND g.source = 'application'
            """
        )
    )
