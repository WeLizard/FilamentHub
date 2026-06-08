"""Сервис для валидации пресетов OrcaSlicer."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.material_mapping import MaterialMapping

# Известные системные пресеты OrcaSlicer
KNOWN_PARENT_PRESETS = {
    # PLA
    "Generic PLA @System",
    "Generic PLA @base",
    "Bambu PLA Basic @BBL X1C",
    "Bambu PLA Matte @BBL X1C",
    "Bambu PLA Silk @BBL X1C",
    # PETG
    "Generic PETG @System",
    "Generic PETG @base",
    "Bambu PETG Basic @BBL X1C",
    "Bambu PETG-HF @BBL X1C",
    # ABS
    "Generic ABS @System",
    "Generic ABS @base",
    "Bambu ABS @BBL X1C",
    # TPU
    "Generic TPU @System",
    "Generic TPU @base",
    "Bambu TPU 95A @BBL X1C",
    # ASA
    "Generic ASA @System",
    "Generic ASA @base",
    # Nylon / PA
    "Generic PA @System",
    "Generic PA-CF @System",
    "Generic PA @base",
    "Bambu PA-CF @BBL X1C",
    # PC
    "Generic PC @System",
    "Generic PC @base",
    # PVA
    "Generic PVA @System",
    "Generic PVA @base",
    # Support materials
    "Generic Support @System",
    "Bambu Support W @BBL X1C",
    "Bambu Support G @BBL X1C",
}


class ParentValidationResult:
    """Результат валидации родительского пресета."""

    def __init__(
        self,
        exists: bool,
        needs_fallback: bool = False,
        fallback_preset: str | None = None,
        confidence: float = 1.0,
        material_type: str | None = None,
    ):
        self.exists = exists
        self.needs_fallback = needs_fallback
        self.fallback_preset = fallback_preset
        self.confidence = confidence
        self.material_type = material_type

    def to_dict(self) -> dict:
        return {
            "exists": self.exists,
            "needs_fallback": self.needs_fallback,
            "fallback_preset": self.fallback_preset,
            "confidence": self.confidence,
            "material_type": self.material_type,
        }


class PresetValidationResult:
    """Результат валидации пресета."""

    def __init__(
        self,
        preset_id: int | None,
        is_valid: bool,
        errors: list[str] | None = None,
        warnings: list[str] | None = None,
        parent_preset_missing: bool = False,
        material_mapping_confidence: float = 1.0,
    ):
        self.preset_id = preset_id
        self.is_valid = is_valid
        self.errors = errors or []
        self.warnings = warnings or []
        self.parent_preset_missing = parent_preset_missing
        self.material_mapping_confidence = material_mapping_confidence

    def to_dict(self) -> dict:
        return {
            "preset_id": self.preset_id,
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "parent_preset_missing": self.parent_preset_missing,
            "material_mapping_confidence": self.material_mapping_confidence,
        }


def _extract_material_from_inherits(inherits: str) -> str | None:
    """Извлечь тип материала из строки inherits."""
    inherits_lower = inherits.lower()
    # Порядок важен — более специфичные первыми
    for mat in ["PA-CF", "PETG", "ABS", "ASA", "TPU", "PA", "PC", "PVA", "PLA"]:
        if mat.lower() in inherits_lower:
            return mat
    return None


async def validate_parent_preset(
    inherits: str, orcaslicer_version: str | None, db: AsyncSession
) -> ParentValidationResult:
    """
    Проверяет существование родительского пресета в OrcaSlicer.

    Args:
        inherits: Название родительского пресета (например, "Generic PLA @System")
        orcaslicer_version: Версия OrcaSlicer (для будущего использования)
        db: Database session

    Returns:
        ParentValidationResult с информацией о существовании и fallback
    """
    if not inherits:
        return ParentValidationResult(exists=True, needs_fallback=False, confidence=1.0)

    # Проверяем известные системные пресеты
    if inherits in KNOWN_PARENT_PRESETS:
        material_type = _extract_material_from_inherits(inherits)
        return ParentValidationResult(exists=True, confidence=1.0, material_type=material_type)

    # Извлекаем материал из inherits
    material_type = _extract_material_from_inherits(inherits)

    if not material_type:
        return ParentValidationResult(
            exists=False,
            needs_fallback=True,
            fallback_preset="Generic PLA @System",
            confidence=0.3,
            material_type="PLA",
        )

    # Проверяем material_mapping для определения fallback
    result = await db.execute(
        select(MaterialMapping).where(
            MaterialMapping.material_type.ilike(f"%{material_type}%")
        )
    )
    mapping = result.scalars().first()

    if mapping:
        # Нашли mapping — используем orcaslicer_preset как fallback
        fallback = mapping.orcaslicer_preset
        return ParentValidationResult(
            exists=False,
            needs_fallback=True,
            fallback_preset=fallback,
            confidence=0.8,
            material_type=material_type,
        )

    # Fallback на системный generic пресет
    fallback = f"Generic {material_type} @System"
    return ParentValidationResult(
        exists=False,
        needs_fallback=True,
        fallback_preset=fallback,
        confidence=0.7,
        material_type=material_type,
    )


async def validate_preset_batch(
    presets: list[dict], db: AsyncSession
) -> list[PresetValidationResult]:
    """
    Валидирует несколько пресетов за один запрос.

    Загружает все нужные material_mappings одним запросом, чтобы избежать N+1.
    """
    # 1. Собираем все material_type из пресетов
    material_types = set()
    for p in presets:
        mt = p.get("material_type")
        if mt:
            material_types.add(mt)

    # 2. Загружаем все маппинги одним запросом
    mappings_dict: dict[str, MaterialMapping] = {}
    if material_types:
        result = await db.execute(
            select(MaterialMapping).where(
                MaterialMapping.material_type.in_(material_types)
            )
        )
        for mapping in result.scalars().all():
            mappings_dict[mapping.material_type] = mapping

    # 3. Валидируем каждый пресет
    results = []

    for preset_data in presets:
        errors = []
        warnings = []
        parent_preset_missing = False
        material_confidence = 1.0

        preset_id = preset_data.get("preset_id")
        name = preset_data.get("name", "")
        inherits = preset_data.get("inherits")
        material_type = preset_data.get("material_type")
        extruder_temp = preset_data.get("extruder_temp")
        bed_temp = preset_data.get("bed_temp")

        # 1. Проверка обязательных полей
        if not name or len(name.strip()) == 0:
            errors.append("Name is required")

        # 2. Валидация parent preset
        if inherits:
            parent_result = await validate_parent_preset(inherits, None, db)
            if not parent_result.exists:
                parent_preset_missing = True
                warnings.append(
                    f"Parent preset '{inherits}' not found. "
                    f"Fallback: '{parent_result.fallback_preset}'"
                )
                material_confidence = parent_result.confidence

        # 3. Проверка температур
        if extruder_temp is not None:
            if extruder_temp < 150 or extruder_temp > 350:
                warnings.append(
                    f"Extruder temperature {extruder_temp}C is outside typical range (150-350C)"
                )

        if bed_temp is not None:
            if bed_temp < 0 or bed_temp > 150:
                warnings.append(
                    f"Bed temperature {bed_temp}C is outside typical range (0-150C)"
                )

        # 4. Проверка material_type (используем кэш)
        if material_type and material_type not in mappings_dict:
            warnings.append(
                f"Material type '{material_type}' not found in material mapping"
            )
            material_confidence = min(material_confidence, 0.5)

        is_valid = len(errors) == 0

        results.append(
            PresetValidationResult(
                preset_id=preset_id,
                is_valid=is_valid,
                errors=errors,
                warnings=warnings,
                parent_preset_missing=parent_preset_missing,
                material_mapping_confidence=material_confidence,
            )
        )

    return results


async def validate_temperature_range(
    material_type: str, extruder_temp: float, bed_temp: float, db: AsyncSession
) -> tuple[bool, list[str]]:
    """Проверяет, соответствуют ли температуры типу материала."""
    warnings = []

    temp_ranges = {
        "PLA": {"extruder": (190, 230), "bed": (50, 70)},
        "PETG": {"extruder": (220, 250), "bed": (70, 90)},
        "ABS": {"extruder": (230, 260), "bed": (90, 110)},
        "TPU": {"extruder": (210, 240), "bed": (50, 70)},
        "ASA": {"extruder": (240, 270), "bed": (90, 110)},
        "PA": {"extruder": (250, 280), "bed": (80, 100)},
        "PC": {"extruder": (270, 310), "bed": (100, 120)},
        "PVA": {"extruder": (190, 220), "bed": (50, 70)},
    }

    if material_type not in temp_ranges:
        warnings.append(f"Unknown material type '{material_type}' - cannot validate temperatures")
        return True, warnings

    ranges = temp_ranges[material_type]
    extruder_range = ranges["extruder"]
    bed_range = ranges["bed"]

    if extruder_temp < extruder_range[0] or extruder_temp > extruder_range[1]:
        warnings.append(
            f"Extruder temp {extruder_temp}C is outside typical range for {material_type} "
            f"({extruder_range[0]}-{extruder_range[1]}C)"
        )

    if bed_temp < bed_range[0] or bed_temp > bed_range[1]:
        warnings.append(
            f"Bed temp {bed_temp}C is outside typical range for {material_type} "
            f"({bed_range[0]}-{bed_range[1]}C)"
        )

    return True, warnings
