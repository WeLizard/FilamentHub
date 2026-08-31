"""Public label inputs contain catalog facts only, never private spool data."""

import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.errors import (
    ERR_FILAMENT_NOT_FOUND,
    ERR_QR_NOT_FOUND,
    ERR_QR_VERIFIED_ONLY,
    raise_error,
)
from app.models.filament import Filament
from app.services.file_service import get_upload_root_dir
from app.services.label_layout import LabelData

logger = logging.getLogger(__name__)

FIELD_LABELS = {
    "ru": {
        "nozzle": "Сопло",
        "bed": "Стол",
        "drying": "Сушка",
        "abrasiveness": "Твёрдость сопла",
        "diameter": "Диаметр",
        "density": "Плотность",
        "weight": "Масса",
        "chamber": "Камера",
        "comment": "Комментарий",
        "hours": "ч",
        "mm": "мм",
        "grams": "г",
        "density_unit": "г/см³",
    },
    "en": {
        "nozzle": "Nozzle",
        "bed": "Bed",
        "drying": "Drying",
        "abrasiveness": "Nozzle hardness",
        "diameter": "Diameter",
        "density": "Density",
        "weight": "Weight",
        "chamber": "Chamber",
        "comment": "Comment",
        "hours": "h",
        "mm": "mm",
        "grams": "g",
        "density_unit": "g/cm³",
    },
    "zh": {
        "nozzle": "喷嘴",
        "bed": "热床",
        "drying": "干燥",
        "abrasiveness": "喷嘴硬度",
        "diameter": "直径",
        "density": "密度",
        "weight": "重量",
        "chamber": "腔室",
        "comment": "备注",
        "hours": "小时",
        "mm": "毫米",
        "grams": "克",
        "density_unit": "克/厘米³",
    },
}


async def public_label_filament(db: AsyncSession, filament_id: int) -> Filament:
    filament = await db.scalar(
        select(Filament)
        .options(joinedload(Filament.brand))
        .where(Filament.id == filament_id, Filament.active.is_(True))
    )
    if filament is None or not filament.brand.active:
        raise_error(404, ERR_FILAMENT_NOT_FOUND)
    if not filament.qr_code:
        if not filament.brand.verified:
            raise_error(403, ERR_QR_VERIFIED_ONLY)
        raise_error(409, ERR_QR_NOT_FOUND)
    return filament


def catalog_label_data(filament: Filament, locale: str) -> LabelData:
    labels = FIELD_LABELS[locale]
    fields = []

    def number(value) -> str:
        formatted = f"{value:g}"
        return formatted.replace(".", ",") if locale == "ru" else formatted

    def add(key: str, value: str) -> None:
        fields.append((key, labels[key], value))

    for key, lower, upper in (
        ("nozzle", filament.recommended_nozzle_temp_min, filament.recommended_nozzle_temp_max),
        ("bed", filament.recommended_bed_temp_min, filament.recommended_bed_temp_max),
    ):
        if lower is not None and upper is not None:
            value = number(lower) if lower == upper else f"{number(lower)}–{number(upper)}"
            add(key, f"{value}\u00a0°C")
    if filament.drying_temperature_c is not None:
        value = f"{number(filament.drying_temperature_c)}\u00a0°C"
        if filament.drying_duration_hours is not None:
            value += f" · {number(filament.drying_duration_hours)}\u00a0{labels['hours']}"
        add("drying", value)
    if filament.required_nozzle_hrc is not None:
        add("abrasiveness", f"≥{number(filament.required_nozzle_hrc)}\u00a0HRC")
    for key, value, unit in (
        ("diameter", filament.diameter, labels["mm"]),
        ("density", filament.density, labels["density_unit"]),
        ("weight", filament.spool_weight, labels["grams"]),
        ("chamber", filament.chamber_temperature_c, "°C"),
    ):
        if value is not None:
            add(key, f"{number(value)}\u00a0{unit}")
    color = filament.color_hex or ""
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        color = ""
    return LabelData(
        sku=filament.qr_code,
        brand=filament.brand.name,
        material=filament.material_type,
        name=filament.name,
        fields=tuple(fields),
        ral=f"RAL {filament.ral_code}" if filament.ral_code else "",
        color_hex=color,
        comment_heading=labels["comment"],
    )


def public_brand_logo(logo_url: str | None) -> bytes | None:
    if not logo_url or not logo_url.startswith("/uploads/brand_logos/"):
        return None
    root = (get_upload_root_dir() / "brand_logos").resolve()
    path = (root / logo_url.removeprefix("/uploads/brand_logos/")).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in {
        ".webp",
        ".png",
        ".jpg",
        ".jpeg",
    }:
        return None
    try:
        if not path.is_file() or path.stat().st_size > 512 * 1024:
            return None
        return path.read_bytes()
    except OSError:
        logger.warning("Cannot read catalog brand logo", exc_info=True)
        return None
