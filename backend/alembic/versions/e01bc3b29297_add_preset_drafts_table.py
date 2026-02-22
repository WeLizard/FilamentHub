"""make_preset_filament_id_nullable_for_drafts

Revision ID: e01bc3b29297
Revises: f3e4d5c6b7a8
Create Date: 2025-11-23 14:17:14.708541

Черновики пресетов из OrcaSlicer хранятся в таблице presets с filament_id=None.
Они отображаются вместе с обычными пресетами, но помечены как черновики.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e01bc3b29297'
down_revision: Union[str, None] = 'f3e4d5c6b7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Делаем filament_id nullable в таблице presets для черновиков из OrcaSlicer
    # Черновики = presets с filament_id=None и active=False
    # Они отображаются вместе с обычными пресетами, но помечены как черновики
    op.alter_column('presets', 'filament_id',
                    existing_type=sa.Integer(),
                    nullable=True,
                    existing_nullable=False)


def downgrade() -> None:
    """Downgrade database schema."""
    # ALEMBIC-5 fix: вместо тихого удаления черновиков — проверяем их наличие и падаем с ошибкой.
    # Это защищает от случайной потери данных при downgrade.
    # Если черновики есть — нужно их вручную перенести или удалить перед downgrade.
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT COUNT(*) FROM presets WHERE filament_id IS NULL"))
    draft_count = result.scalar()
    if draft_count > 0:
        raise RuntimeError(
            f"Cannot downgrade: {draft_count} draft preset(s) with filament_id=NULL exist. "
            "Manually migrate or delete them before running downgrade."
        )
    op.alter_column('presets', 'filament_id',
                    existing_type=sa.Integer(),
                    nullable=False,
                    existing_nullable=True)

