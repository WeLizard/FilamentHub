"""Material mapping service для определения системного пресета OrcaSlicer по типу материала."""

import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import escape_like
from app.models.material_mapping import MaterialMapping, MaterialMappingPriority

logger = logging.getLogger(__name__)

# Базовый маппинг материалов (fallback если нет в БД)
# Основано на docs/ORCASLICER_FILAMENT_TYPES.md
BASE_MATERIAL_MAP = {
    # Базовые материалы
    "PLA": "Generic PLA @System",
    "ABS": "Generic ABS @System",
    "PETG": "Generic PETG @System",
    "PET": "Generic PETG @System",  # PET наследуется от PETG
    "TPU": "Generic TPU @System",
    "ASA": "Generic ASA @System",
    "PC": "Generic PC @System",
    "PA": "Generic PA @System",
    "PVA": "Generic PVA @System",
    "HIPS": "Generic ABS @System",  # HIPS наследуется от ABS
    "PP": "Generic PLA @System",  # PP → PLA (как в документации)
    "POM": "Generic PLA @System",  # POM → PLA (как в документации)

    # Материалы с углеродным волокном (CF)
    "PET-CF": "Generic PETG @System",
    "PETG-CF": "Generic PETG @System",
    "PLA-CF": "Generic PLA @System",
    "ABS-CF": "Generic ABS @System",
    "ASA-CF": "Generic ASA @System",
    "PC-CF": "Generic PC @System",
    "PA-CF": "Generic PA @System",
    "PP-CF": "Generic PLA @System",

    # Материалы со стекловолокном (GF)
    "ABS-GF": "Generic ABS @System",
    "ASA-GF": "Generic ASA @System",
    "PA-GF": "Generic PA @System",
    "PET-GF": "Generic PETG @System",
    "PETG-GF": "Generic PETG @System",
    "PC-PBT": "Generic PC @System",

    # Полиамиды (PA вариации)
    "PA6": "Generic PA @System",
    "PA11": "Generic PA @System",
    "PA12": "Generic PA @System",
    "PAHT": "Generic PA @System",
    "PA6-CF": "Generic PA @System",
    "PA11-CF": "Generic PA @System",
    "PA12-CF": "Generic PA @System",
    "PAHT-CF": "Generic PA @System",
    "PA6-GF": "Generic PA @System",
    "PA11-GF": "Generic PA @System",
    "PA12-GF": "Generic PA @System",
    "PAHT-GF": "Generic PA @System",

    # Высокотемпературные материалы → PC
    "PEI": "Generic PC @System",
    "PEI-1010": "Generic PC @System",
    "PEI-9085": "Generic PC @System",
    "PEI-1010-CF": "Generic PC @System",
    "PEI-9085-CF": "Generic PC @System",
    "PEI-1010-GF": "Generic PC @System",
    "PEI-9085-GF": "Generic PC @System",
    "PEEK": "Generic PC @System",
    "PEEK-CF": "Generic PC @System",
    "PEEK-GF": "Generic PC @System",
    "PEKK": "Generic PC @System",
    "PEKK-CF": "Generic PC @System",
    "PES": "Generic PC @System",
    "PPS": "Generic PC @System",
    "PPSU": "Generic PC @System",
    "PSU": "Generic PC @System",
    "TPI": "Generic TPU @System",  # TPI → TPU (гибкий)
    "PI": "Generic PC @System",

    # Гибкие материалы → TPU
    "FLEX": "Generic TPU @System",
    "PCL": "Generic TPU @System",

    # Растворимые материалы → PVA
    "BVOH": "Generic PVA @System",
    "PVB": "Generic PVA @System",

    # Специальные материалы
    "ASA-AERO": "Generic ASA @System",
    "PLA-AERO": "Generic PLA @System",
    "PC-ABS": "Generic PC @System",
    "PCTG": "Generic PETG @System",  # PCTG → PETG (близкий по свойствам)
    "PHA": "Generic PLA @System",  # PHA → PLA (близкий по свойствам)
    "PE": "Generic PLA @System",  # PE → PLA
    "PE-CF": "Generic PLA @System",
    "PE-GF": "Generic PLA @System",
    "PVDF": "Generic PLA @System",  # PVDF → PLA (по умолчанию)
    "SBS": "Generic PLA @System",  # SBS → PLA (по умолчанию)
    "PPA": "Generic PA @System",  # PPA → PA
    "PPA-CF": "Generic PA @System",
    "PPA-GF": "Generic PA @System",
    "EVA": "Generic TPU @System",  # EVA → TPU (гибкий)

    # Альтернативные названия (с модификаторами)
    "PLA+": "Generic PLA @System",
    "PLA PRO": "Generic PLA @System",
    "PLA PRO+": "Generic PLA @System",
    "PLA MAX": "Generic PLA @System",
    "PP+": "Generic PLA @System",  # PP+ → PP → PLA
    "PP PLUS": "Generic PLA @System",
}

# Паттерны для умного поиска материалов
# Основано на docs/ORCASLICER_FILAMENT_TYPES.md
MATERIAL_PATTERNS = [
    # PLA варианты (включая PLA+, PLA-CF, PLA-AERO)
    (r"(?i)\bPLA[^A-Z]*(?:CF|AERO|PRO|\+)?\b", "Generic PLA @System"),
    # ABS варианты (включая ABS-CF, ABS-GF)
    (r"(?i)\bABS[^A-Z]*(?:CF|GF)?\b", "Generic ABS @System"),
    # PETG/PET варианты (включая PET-CF, PETG-CF, PETG-GF, PET-GF, PCTG)
    (r"(?i)\b(?:PETG?|PCTG)[^A-Z]*(?:CF|GF)?\b", "Generic PETG @System"),
    # TPU варианты
    (r"(?i)\bTPU[^A-Z]*\b", "Generic TPU @System"),
    # Гибкие материалы (FLEX, EVA, PCL, TPI)
    (r"(?i)\b(FLEX|EVA|PCL|TPI)\b", "Generic TPU @System"),
    # ASA варианты (включая ASA-CF, ASA-GF, ASA-AERO)
    (r"(?i)\bASA[^A-Z]*(?:CF|GF|AERO)?\b", "Generic ASA @System"),
    # PC варианты (включая PC-CF, PC-ABS, PC-PBT)
    (r"(?i)\bPC[^A-Z]*(?:CF|ABS|PBT)?\b", "Generic PC @System"),
    # Высокотемпературные материалы (PEI, PEEK, PEKK, PES, PPS, PPSU, PSU, PI)
    (r"(?i)\b(PEI|PEEK|PEKK|PES|PPS|PPSU|PSU|PI)[^A-Z]*(?:CF|GF)?\b", "Generic PC @System"),
    # PA/Nylon варианты (включая PA6, PA11, PA12, PAHT, PA-CF, PA-GF, PPA)
    (r"(?i)\b(?:PA|NYLON|PPA)[^A-Z0-9]*(?:6|11|12|HT)?[^A-Z]*(?:CF|GF)?\b", "Generic PA @System"),
    # PVA варианты (включая BVOH, PVB)
    (r"(?i)\b(?:PVA|BVOH|PVB)\b", "Generic PVA @System"),
    # PP варианты (Polypropylene, включая PP+, PP-CF, PP-GF)
    (r"(?i)\bPP[^A-Z]*(?:CF|GF|\+|PLUS)?\b", "Generic PLA @System"),  # PP → PLA (как в документации)
    # POM (Delrin) → PLA
    (r"(?i)\bPOM\b", "Generic PLA @System"),
    # PE (Polyethylene) → PLA
    (r"(?i)\bPE[^A-Z]*(?:CF|GF)?\b", "Generic PLA @System"),
    # HIPS → ABS
    (r"(?i)\bHIPS\b", "Generic ABS @System"),
    # SBS, PHA, PVDF → PLA (по умолчанию)
    (r"(?i)\b(SBS|PHA|PVDF)\b", "Generic PLA @System"),
]


async def get_material_preset(
    material_type: str,
    db: AsyncSession,
    log_unknown: bool = True,
) -> str:
    """
    Получить системный пресет OrcaSlicer для типа материала.

    Приоритет поиска:
    1. MaterialMapping из БД (brand > manual > automatic)
    2. Базовый маппинг (BASE_MATERIAL_MAP)
    3. Умный поиск по паттернам (MATERIAL_PATTERNS)
    4. Умный поиск базового типа (убирает модификаторы +, PRO, MAX, CF, GF)
    5. Fallback на fdm_filament_common (для любых неизвестных типов)

    Args:
        material_type: Тип материала (например "PLA-MAX", "SUPER PLA")
        db: AsyncSession для запросов к БД
        log_unknown: Логировать неизвестные типы материалов

    Returns:
        str: Имя системного пресета OrcaSlicer (например "Generic PLA @System")
    """
    material_type_upper = material_type.upper().strip()

    # 1. Проверяем MaterialMapping из БД (сортировка по приоритету)
    query = select(MaterialMapping).where(
        MaterialMapping.material_type.ilike(escape_like(material_type_upper)),
        MaterialMapping.active == True,
    ).order_by(
        # Приоритет: brand > manual > automatic
        MaterialMapping.priority.desc()
    )

    result = await db.execute(query)
    mapping = result.scalar_one_or_none()

    if mapping:
        logger.debug(f"MaterialMapping found: {material_type} -> {mapping.orcaslicer_preset} (priority: {mapping.priority.value})")
        return mapping.orcaslicer_preset

    # 2. Проверяем базовый маппинг
    if material_type_upper in BASE_MATERIAL_MAP:
        logger.debug(f"Base mapping found: {material_type} -> {BASE_MATERIAL_MAP[material_type_upper]}")
        return BASE_MATERIAL_MAP[material_type_upper]

    # 3. Умный поиск по паттернам
    for pattern, preset in MATERIAL_PATTERNS:
        if re.search(pattern, material_type):
            logger.info(f"Pattern match: {material_type} -> {preset} (pattern: {pattern})")
            return preset

    # 3.5. Умный поиск базового типа (например, PP+ → PP → Generic PLA)
    # Убираем модификаторы типа +, PRO, MAX, CF, GF и ищем базовый тип
    # Основано на docs/ORCASLICER_FILAMENT_TYPES.md
    base_types_map = {
        "PLA": "Generic PLA @System",
        "ABS": "Generic ABS @System",
        "PETG": "Generic PETG @System",
        "PET": "Generic PETG @System",
        "TPU": "Generic TPU @System",
        "ASA": "Generic ASA @System",
        "PC": "Generic PC @System",
        "PA": "Generic PA @System",
        "PVA": "Generic PVA @System",
        "HIPS": "Generic ABS @System",  # HIPS → ABS
        "PP": "Generic PLA @System",  # PP → PLA (как в документации)
        "POM": "Generic PLA @System",  # POM → PLA (как в документации)
        "PE": "Generic PLA @System",  # PE → PLA
        "PEI": "Generic PC @System",  # PEI → PC (высокотемпературный)
        "PEEK": "Generic PC @System",  # PEEK → PC (высокотемпературный)
        "PEKK": "Generic PC @System",  # PEKK → PC (высокотемпературный)
        "PES": "Generic PC @System",  # PES → PC (высокотемпературный)
        "PPS": "Generic PC @System",  # PPS → PC (высокотемпературный)
        "PPSU": "Generic PC @System",  # PPSU → PC (высокотемпературный)
        "PSU": "Generic PC @System",  # PSU → PC (высокотемпературный)
        "PI": "Generic PC @System",  # PI → PC (высокотемпературный)
        "FLEX": "Generic TPU @System",  # FLEX → TPU (гибкий)
        "EVA": "Generic TPU @System",  # EVA → TPU (гибкий)
        "PCL": "Generic TPU @System",  # PCL → TPU (гибкий)
        "TPI": "Generic TPU @System",  # TPI → TPU (гибкий)
        "BVOH": "Generic PVA @System",  # BVOH → PVA (растворимый)
        "PVB": "Generic PVA @System",  # PVB → PVA (растворимый)
        "PPA": "Generic PA @System",  # PPA → PA
        "PCTG": "Generic PETG @System",  # PCTG → PETG (близкий по свойствам)
        "PHA": "Generic PLA @System",  # PHA → PLA (близкий по свойствам)
        "PVDF": "Generic PLA @System",  # PVDF → PLA (по умолчанию)
        "SBS": "Generic PLA @System",  # SBS → PLA (по умолчанию)
    }

    for base_type, preset in base_types_map.items():
        # Ищем базовый тип в начале или после дефиса/пробела
        # Учитываем модификаторы: +, PRO, MAX, PLUS, ZERO, CF, GF, -AERO, -PBT, и числа (PA6, PA11, PA12)
        pattern = rf"(?i)\b{re.escape(base_type)}(?:\+|PRO|MAX|PLUS|ZERO|-\w+|\d+)?\b"
        if re.search(pattern, material_type_upper):
            logger.info(f"Base type match: {material_type} -> {base_type} -> {preset}")
            return preset

    # 4. Fallback на fdm_filament_common (универсальный пресет для неизвестных типов)
    if log_unknown:
        logger.warning(f"Unknown material type: '{material_type}', using fallback 'fdm_filament_common'")

    return "fdm_filament_common"


async def create_material_mapping(
    material_type: str,
    orcaslicer_preset: str,
    db: AsyncSession,
    priority: MaterialMappingPriority = MaterialMappingPriority.MANUAL,
    brand_id: int | None = None,
    description: str | None = None,
) -> MaterialMapping:
    """
    Создать новый маппинг материала.

    Args:
        material_type: Тип материала
        orcaslicer_preset: Системный пресет OrcaSlicer
        db: AsyncSession
        priority: Приоритет маппинга
        brand_id: ID бренда (если от производителя)
        description: Описание маппинга

    Returns:
        MaterialMapping: Созданный маппинг
    """
    mapping = MaterialMapping(
        material_type=material_type.upper().strip(),
        orcaslicer_preset=orcaslicer_preset,
        priority=priority,
        brand_id=brand_id,
        description=description,
        active=True,
    )

    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)

    logger.info(f"Created MaterialMapping: {material_type} -> {orcaslicer_preset} (priority: {priority.value})")
    return mapping

