"""Create User Materials brand (id=1)

Revision ID: c3d4e5f6a7b0
Revises: b2c3d4e5f6a9
Create Date: 2025-11-12 23:52:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b0'
down_revision: Union[str, None] = 'b2c3d4e5f6a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Создаем служебный бренд "User Materials" (id=1)
    # Этот бренд используется для импортированных пользовательских материалов из OrcaSlicer
    # Материалы импортируются как черновики (active=False) и привязаны к этому бренду
    # Пользователь может позже активировать и привязать к своему бренду через UI
    
    # Используем INSERT с ON CONFLICT DO NOTHING, чтобы не было ошибки, если бренд уже существует
    # Также используем явное указание created_at и updated_at, так как они могут не иметь server_default
    op.execute("""
        INSERT INTO brands (id, name, slug, description, verified, active, created_at, updated_at)
        VALUES (
            1,
            'User Materials',
            'user-materials',
            'User-imported materials from OrcaSlicer (drafts). These materials are imported as inactive drafts and can be activated and assigned to your brand via the UI.',
            false,
            true,
            COALESCE((SELECT created_at FROM brands WHERE id = 1), NOW()),
            NOW()
        )
        ON CONFLICT (id) DO UPDATE
        SET 
            name = EXCLUDED.name,
            slug = EXCLUDED.slug,
            description = EXCLUDED.description,
            updated_at = NOW()
    """)


def downgrade() -> None:
    """Downgrade database schema."""
    # Удаляем служебный бренд "User Materials" (id=1)
    # ВАЖНО: Перед удалением нужно проверить, что нет материалов, привязанных к этому бренду
    # Или переместить их в другой бренд
    # Для безопасности оставляем бренд (просто комментируем удаление)
    # Если нужно удалить, можно сделать это вручную через SQL
    # op.execute("DELETE FROM brands WHERE id = 1")
    pass
