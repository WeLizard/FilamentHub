"""Импорт материалов бренда из CSV."""

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.core.errors import (
    ERR_BRAND_NOT_FOUND,
    ERR_NO_PERMISSION_EDIT_FILAMENT,
    raise_error,
)
from app.db.session import get_db
from app.models.brand import Brand
from app.models.filament import Filament, FilamentAvailability
from app.models.filament_line import FilamentLine
from app.models.user import User, UserRole
from app.schemas.filament import (
    FilamentImportResult,
    FilamentImportRowResult,
)
from app.services.preset_moderation import validate_text_field
from app.services.slug_service import generate_unique_slug

router = APIRouter(prefix="/filament-import", tags=["filament-import"])

CSV_COLUMNS = [
    "name", "material_type", "color_name", "color_hex",
    "price_per_kg", "spool_weight", "line", "availability",
]

_AVAILABILITY_VALUES = {a.value for a in FilamentAvailability}


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip().replace(",", ".")
    if not text:
        return None
    try:
        num = float(text)
    except ValueError:
        return None
    return num if num > 0 else None


@router.get("/template")
async def download_template() -> Response:
    """CSV-шаблон для импорта (открывается в Excel)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    writer.writerow(["PLA Basic Red", "PLA", "Red", "#FF0000", "1500", "1000", "PLA Basic", "available"])
    # BOM — чтобы Excel распознал UTF-8; "sep=," — чтобы Excel (в т.ч. RU-локаль,
    # где разделитель по умолчанию ";") разбил файл на колонки по запятой.
    content = "﻿" + "sep=,\r\n" + buffer.getvalue()
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=filament_import_template.csv"},
    )


@router.post("", response_model=FilamentImportResult)
async def import_filaments(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    brand_id: int = Query(..., gt=0),
    file: UploadFile = File(...),
) -> FilamentImportResult:
    """Импортировать материалы бренда из CSV."""
    brand = await db.scalar(select(Brand).where(Brand.id == brand_id))
    if brand is None:
        raise_error(404, ERR_BRAND_NOT_FOUND)
    if current_user.role != UserRole.ADMIN and current_user.brand_id != brand_id:
        raise_error(403, ERR_NO_PERMISSION_EDIT_FILAMENT)

    raw = await file.read()
    text = raw.decode("utf-8-sig", errors="replace")
    # Excel (особенно RU-локаль) сохраняет CSV с разделителем ";". Поддерживаем оба
    # разделителя и строку-подсказку "sep=," (её Excel пишет/читает, в данные не берём).
    lines = text.splitlines()
    delimiter = ","
    if lines and lines[0].strip().lower().startswith("sep="):
        sep_char = lines[0].strip()[4:5]
        if sep_char in (",", ";", "\t"):
            delimiter = sep_char
        text = "\n".join(lines[1:])
    elif lines and ";" in lines[0] and "," not in lines[0]:
        delimiter = ";"
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    result = FilamentImportResult()
    # Кэш линеек бренда по нижнему регистру имени, чтобы не плодить дубликаты.
    line_cache: dict[str, FilamentLine] = {}
    existing_lines = await db.execute(
        select(FilamentLine).where(FilamentLine.brand_id == brand_id)
    )
    for line in existing_lines.scalars():
        line_cache[line.name.strip().lower()] = line

    for index, row in enumerate(reader, start=1):
        name = (row.get("name") or "").strip()
        material_type = (row.get("material_type") or "").strip()

        if not name or not material_type:
            result.errors += 1
            result.rows.append(FilamentImportRowResult(
                row=index, status="error", name=name or None, message="ERR_VALIDATION_REQUIRED",
            ))
            continue

        is_valid, _ = await validate_text_field(name, db, "filament_name")
        if not is_valid:
            result.errors += 1
            result.rows.append(FilamentImportRowResult(
                row=index, status="error", name=name, message="ERR_VALIDATION_TEXT",
            ))
            continue

        color_name = (row.get("color_name") or "").strip() or None
        color_hex = (row.get("color_hex") or "").strip().upper() or None
        price_per_kg = _parse_float(row.get("price_per_kg"))
        spool_weight = _parse_float(row.get("spool_weight"))

        availability_raw = (row.get("availability") or "").strip().lower()
        availability = (
            FilamentAvailability(availability_raw)
            if availability_raw in _AVAILABILITY_VALUES
            else FilamentAvailability.available
        )

        # Дубликат: тот же бренд + название + тип + цвет (по имени цвета, без регистра).
        duplicate = await db.scalar(
            select(Filament.id).where(
                Filament.brand_id == brand_id,
                Filament.active.is_(True),
                func.lower(func.trim(Filament.name)) == name.lower(),
                func.lower(func.trim(Filament.material_type)) == material_type.lower(),
                func.coalesce(func.lower(func.trim(Filament.color_name)), "")
                == (color_name.lower() if color_name else ""),
            )
        )
        if duplicate is not None:
            result.skipped += 1
            result.rows.append(FilamentImportRowResult(
                row=index, status="skipped", name=name, filament_id=duplicate,
                message="ERR_FILAMENT_ALREADY_EXISTS",
            ))
            continue

        # Линейка (создаём при необходимости).
        line_id: int | None = None
        line_name = (row.get("line") or "").strip()
        if line_name:
            cached = line_cache.get(line_name.lower())
            if cached is None:
                cached = FilamentLine(brand_id=brand_id, name=line_name)
                db.add(cached)
                await db.flush()
                line_cache[line_name.lower()] = cached
            line_id = cached.id

        slug = await generate_unique_slug(db=db, model=Filament, source=name, fallback="filament")
        filament = Filament(
            brand_id=brand_id,
            line_id=line_id,
            name=name,
            material_type=material_type,
            color_name=color_name,
            color_hex=color_hex if color_hex and color_hex.startswith("#") else None,
            price_per_kg=price_per_kg,
            spool_weight=spool_weight,
            availability=availability,
            slug=slug,
            active=True,
        )
        db.add(filament)
        await db.flush()

        if brand.verified:
            from app.services.qr_service import generate_short_code, save_qr_code_image
            short_code = generate_short_code(filament.id)
            if await db.scalar(select(Filament.id).where(Filament.qr_code == short_code)):
                short_code = f"{short_code}-{filament.id % 1000}"
            filament.qr_code = short_code
            save_qr_code_image(short_code, sizes=[300, 600, 1200])

        result.created += 1
        result.rows.append(FilamentImportRowResult(
            row=index, status="created", name=name, filament_id=filament.id,
        ))

    await db.commit()
    return result
