"""Seed initial material types

Revision ID: 962108c85ee3
Revises: cd4a3c3232ff
Create Date: 2025-11-03 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import table, column, String, Boolean, DateTime, Enum
from sqlalchemy.dialects.postgresql import ENUM

# revision identifiers, used by Alembic.
revision: str = '962108c85ee3'
down_revision: Union[str, None] = 'cd4a3c3232ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Базовый маппинг материалов из material_mapping_service.py
# Все известные типы материалов с их маппингом на OrcaSlicer системные пресеты
INITIAL_MATERIAL_MAPPINGS = [
    # Базовые материалы
    ("PLA", "Generic PLA @System", "manual"),
    ("ABS", "Generic ABS @System", "manual"),
    ("PETG", "Generic PETG @System", "manual"),
    ("PET", "Generic PETG @System", "manual"),  # PET наследуется от PETG
    ("TPU", "Generic TPU @System", "manual"),
    ("ASA", "Generic ASA @System", "manual"),
    ("PC", "Generic PC @System", "manual"),
    ("PA", "Generic PA @System", "manual"),
    ("PVA", "Generic PVA @System", "manual"),
    ("HIPS", "Generic ABS @System", "manual"),  # HIPS наследуется от ABS
    ("PP", "Generic PLA @System", "manual"),  # PP → PLA (как в документации)
    ("POM", "Generic PLA @System", "manual"),  # POM → PLA (как в документации)
    
    # Материалы с углеродным волокном (CF)
    ("PET-CF", "Generic PETG @System", "manual"),
    ("PETG-CF", "Generic PETG @System", "manual"),
    ("PLA-CF", "Generic PLA @System", "manual"),
    ("ABS-CF", "Generic ABS @System", "manual"),
    ("ASA-CF", "Generic ASA @System", "manual"),
    ("PC-CF", "Generic PC @System", "manual"),
    ("PA-CF", "Generic PA @System", "manual"),
    ("PP-CF", "Generic PLA @System", "manual"),
    
    # Материалы со стекловолокном (GF)
    ("ABS-GF", "Generic ABS @System", "manual"),
    ("ASA-GF", "Generic ASA @System", "manual"),
    ("PA-GF", "Generic PA @System", "manual"),
    ("PET-GF", "Generic PETG @System", "manual"),
    ("PETG-GF", "Generic PETG @System", "manual"),
    ("PC-PBT", "Generic PC @System", "manual"),
    
    # Полиамиды (PA вариации)
    ("PA6", "Generic PA @System", "manual"),
    ("PA11", "Generic PA @System", "manual"),
    ("PA12", "Generic PA @System", "manual"),
    ("PAHT", "Generic PA @System", "manual"),
    ("PA6-CF", "Generic PA @System", "manual"),
    ("PA11-CF", "Generic PA @System", "manual"),
    ("PA12-CF", "Generic PA @System", "manual"),
    ("PAHT-CF", "Generic PA @System", "manual"),
    ("PA6-GF", "Generic PA @System", "manual"),
    ("PA11-GF", "Generic PA @System", "manual"),
    ("PA12-GF", "Generic PA @System", "manual"),
    ("PAHT-GF", "Generic PA @System", "manual"),
    
    # Высокотемпературные материалы → PC
    ("PEI", "Generic PC @System", "manual"),
    ("PEI-1010", "Generic PC @System", "manual"),
    ("PEI-9085", "Generic PC @System", "manual"),
    ("PEI-1010-CF", "Generic PC @System", "manual"),
    ("PEI-9085-CF", "Generic PC @System", "manual"),
    ("PEI-1010-GF", "Generic PC @System", "manual"),
    ("PEI-9085-GF", "Generic PC @System", "manual"),
    ("PEEK", "Generic PC @System", "manual"),
    ("PEEK-CF", "Generic PC @System", "manual"),
    ("PEEK-GF", "Generic PC @System", "manual"),
    ("PEKK", "Generic PC @System", "manual"),
    ("PEKK-CF", "Generic PC @System", "manual"),
    ("PES", "Generic PC @System", "manual"),
    ("PPS", "Generic PC @System", "manual"),
    ("PPSU", "Generic PC @System", "manual"),
    ("PSU", "Generic PC @System", "manual"),
    ("TPI", "Generic TPU @System", "manual"),  # TPI → TPU (гибкий)
    ("PI", "Generic PC @System", "manual"),
    
    # Гибкие материалы → TPU
    ("FLEX", "Generic TPU @System", "manual"),
    ("PCL", "Generic TPU @System", "manual"),
    
    # Растворимые материалы → PVA
    ("BVOH", "Generic PVA @System", "manual"),
    ("PVB", "Generic PVA @System", "manual"),
    
    # Специальные материалы
    ("ASA-AERO", "Generic ASA @System", "manual"),
    ("PLA-AERO", "Generic PLA @System", "manual"),
    ("PC-ABS", "Generic PC @System", "manual"),
    ("PCTG", "Generic PETG @System", "manual"),  # PCTG → PETG (близкий по свойствам)
    ("PHA", "Generic PLA @System", "manual"),  # PHA → PLA (близкий по свойствам)
    ("PE", "Generic PLA @System", "manual"),  # PE → PLA
    ("PE-CF", "Generic PLA @System", "manual"),
    ("PE-GF", "Generic PLA @System", "manual"),
    ("PVDF", "Generic PLA @System", "manual"),  # PVDF → PLA (по умолчанию)
    ("SBS", "Generic PLA @System", "manual"),  # SBS → PLA (по умолчанию)
    ("PPA", "Generic PA @System", "manual"),  # PPA → PA
    ("PPA-CF", "Generic PA @System", "manual"),
    ("PPA-GF", "Generic PA @System", "manual"),
    ("EVA", "Generic TPU @System", "manual"),  # EVA → TPU (гибкий)
    
    # Альтернативные названия (с модификаторами)
    ("PLA+", "Generic PLA @System", "manual"),
    ("PLA PRO", "Generic PLA @System", "manual"),
    ("PLA PRO+", "Generic PLA @System", "manual"),
    ("PLA MAX", "Generic PLA @System", "manual"),
    ("PP+", "Generic PLA @System", "manual"),  # PP+ → PP → PLA
    ("PP PLUS", "Generic PLA @System", "manual"),
]


def upgrade() -> None:
    """Upgrade database schema."""
    # Создаем ссылку на таблицу material_mappings
    material_mappings = table(
        'material_mappings',
        column('material_type', String(100)),
        column('orcaslicer_preset', String(200)),
        column('priority', String(20)),  # Enum будет автоматически преобразован
        column('active', Boolean),
        column('description', sa.Text),
    )
    
    # Вставляем начальные маппинги материалов
    # Проверяем существование перед вставкой, чтобы избежать дубликатов
    connection = op.get_bind()
    
    for material_type, orcaslicer_preset, priority in INITIAL_MATERIAL_MAPPINGS:
        # Проверяем, существует ли уже такой маппинг
        existing = connection.execute(
            sa.text(
                "SELECT id FROM material_mappings WHERE material_type = :material_type"
            ),
            {"material_type": material_type}
        ).fetchone()
        
        if not existing:
            # Используем прямой SQL с подстановкой значения приоритета (без параметризации для Enum)
            # PostgreSQL Enum требует явного приведения типа
            sql = sa.text(
                f"""
                INSERT INTO material_mappings (material_type, orcaslicer_preset, priority, active, description, created_at, updated_at)
                VALUES (:material_type, :orcaslicer_preset, '{priority}'::materialmappingpriority, :active, :description, NOW(), NOW())
                """
            )
            connection.execute(
                sql,
                {
                    "material_type": material_type,
                    "orcaslicer_preset": orcaslicer_preset,
                    "active": True,
                    "description": f"Начальный маппинг для материала '{material_type}' → '{orcaslicer_preset}'",
                }
            )
    
    # Коммитим изменения
    connection.commit()


def downgrade() -> None:
    """Downgrade database schema."""
    # Удаляем начальные маппинги с приоритетом 'manual' (не автоматические)
    connection = op.get_bind()
    
    material_types_to_remove = [mt[0] for mt in INITIAL_MATERIAL_MAPPINGS]
    
    if material_types_to_remove:
        # Используем цикл для универсальности (работает на любых БД)
        for material_type in material_types_to_remove:
            connection.execute(
                sa.text(
                    "DELETE FROM material_mappings WHERE material_type = :material_type AND priority = 'manual'"
                ),
                {"material_type": material_type}
            )
    
    # Коммитим изменения
    connection.commit()
