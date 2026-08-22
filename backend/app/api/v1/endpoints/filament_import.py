"""Импорт материалов бренда из CSV."""

import csv
import hashlib
import hmac
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from jwt.exceptions import InvalidTokenError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_active_user
from app.core.errors import (
    ERR_BRAND_NOT_FOUND,
    ERR_FILAMENT_IMPORT_CONFIRMATION_INVALID,
    ERR_FILAMENT_IMPORT_FILE_TOO_LARGE,
    ERR_FILAMENT_IMPORT_INVALID_CSV,
    ERR_NO_PERMISSION_EDIT_FILAMENT,
    raise_error,
)
from app.db.session import get_db
from app.models.brand import Brand
from app.models.filament import Filament, FilamentAvailability
from app.models.filament_country_cell import CountryAvailability, FilamentCountryCell
from app.models.filament_line import FilamentLine
from app.models.user import User
from app.schemas.filament import (
    FilamentImportPreviewResult,
    FilamentImportResult,
    FilamentImportRowResult,
    normalize_ral_code,
)
from app.services.catalog_color_groups import classify_color_group
from app.services.catalog_url_service import choose_filament_slug
from app.services.country_market import filament_cell_has_public_data
from app.services.preset_moderation import validate_text_field
from app.services.territorial_access import (
    can_create_for_brand,
    can_edit_filament_common,
    can_manage_filament_country,
)

router = APIRouter(prefix="/filament-import", tags=["filament-import"])

CSV_COLUMNS = [
    "name",
    "material_type",
    "color_name",
    "market_color_name",
    "color_hex",
    "ral_code",
    "price_per_kg",
    "currency",
    "spool_weight",
    "line",
    "availability",
    "product_url",
    "market_note",
]

_AVAILABILITY_VALUES = {a.value for a in FilamentAvailability}
_COUNTRY_AVAILABILITY_VALUES = {a.value for a in CountryAvailability}
_MAX_CSV_BYTES = 2 * 1024 * 1024
_CONFIRMATION_MINUTES = 15
_CONFIRMATION_TYPE = "filament_csv_import"


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


async def _read_csv_upload(file: UploadFile) -> tuple[bytes, list[dict[str, str | None]]]:
    raw = await file.read(_MAX_CSV_BYTES + 1)
    if len(raw) > _MAX_CSV_BYTES:
        raise_error(413, ERR_FILAMENT_IMPORT_FILE_TOO_LARGE)

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise_error(400, ERR_FILAMENT_IMPORT_INVALID_CSV)

    lines = text.splitlines()
    delimiter = ","
    if lines and lines[0].strip().lower().startswith("sep="):
        sep_char = lines[0].strip()[4:5]
        if sep_char in (",", ";", "\t"):
            delimiter = sep_char
        text = "\n".join(lines[1:])
    elif lines and ";" in lines[0] and "," not in lines[0]:
        delimiter = ";"

    try:
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        fieldnames = {str(value).strip() for value in (reader.fieldnames or []) if value}
        if not {"name", "material_type"}.issubset(fieldnames):
            raise_error(400, ERR_FILAMENT_IMPORT_INVALID_CSV)
        return raw, list(reader)
    except csv.Error:
        raise_error(400, ERR_FILAMENT_IMPORT_INVALID_CSV)


def _plan_digest(result: FilamentImportResult) -> str:
    payload = {
        "created": result.created,
        "updated": result.updated,
        "skipped": result.skipped,
        "errors": result.errors,
        "rows": [
            {
                "row": row.row,
                "status": row.status,
                "name": row.name,
                "material_type": row.material_type,
                "color_name": row.color_name,
                "message": row.message,
            }
            for row in result.rows
        ],
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _editable_source_rows(rows: list[dict[str, str | None]]) -> list[dict[str, str]]:
    """Return only supported CSV cells so the preview can be safely corrected."""
    return [{column: str(row.get(column) or "") for column in CSV_COLUMNS} for row in rows]


def _create_confirmation_token(
    *,
    user_id: int,
    brand_id: int,
    country: str | None,
    file_digest: str,
    plan_digest: str,
) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=_CONFIRMATION_MINUTES)
    token = jwt.encode(
        {
            "type": _CONFIRMATION_TYPE,
            "user_id": user_id,
            "brand_id": brand_id,
            "country": country,
            "file_digest": file_digest,
            "plan_digest": plan_digest,
            "exp": expires_at,
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return token, expires_at


def _decode_confirmation_token(
    *,
    token: str,
    user_id: int,
    brand_id: int,
    country: str | None,
    file_digest: str,
) -> str:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            leeway=30,
        )
        if payload.get("type") != _CONFIRMATION_TYPE:
            raise ValueError("Wrong confirmation type")
        if payload.get("user_id") != user_id or payload.get("brand_id") != brand_id:
            raise ValueError("Confirmation belongs to another import")
        if payload.get("country") != country:
            raise ValueError("Import country changed")
        stored_file_digest = payload.get("file_digest")
        if not isinstance(stored_file_digest, str) or not hmac.compare_digest(
            stored_file_digest, file_digest
        ):
            raise ValueError("Import file changed")
        plan_digest = payload.get("plan_digest")
        if not isinstance(plan_digest, str):
            raise ValueError("Missing import plan")
        return plan_digest
    except (InvalidTokenError, TypeError, ValueError):
        raise_error(409, ERR_FILAMENT_IMPORT_CONFIRMATION_INVALID)


async def _get_import_brand(
    *,
    db: AsyncSession,
    current_user: User,
    brand_id: int,
    country: str | None,
    lock: bool = False,
) -> Brand:
    query = select(Brand).where(Brand.id == brand_id)
    if lock:
        query = query.with_for_update()
    brand = await db.scalar(query)
    if brand is None:
        raise_error(404, ERR_BRAND_NOT_FOUND)
    if not await can_create_for_brand(db, current_user, brand_id):
        raise_error(403, ERR_NO_PERMISSION_EDIT_FILAMENT)
    if country and not await can_manage_filament_country(db, current_user, brand_id, country):
        raise_error(403, ERR_NO_PERMISSION_EDIT_FILAMENT)
    if country is None and not await can_edit_filament_common(db, current_user, brand_id):
        raise_error(403, ERR_NO_PERMISSION_EDIT_FILAMENT)
    return brand


@router.get("/template")
async def download_template() -> Response:
    """CSV-шаблон для импорта (открывается в Excel)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    writer.writerow(
        [
            "PLA Basic Red",
            "PLA",
            "Red",
            "Red",
            "#FF0000",
            "3020",
            "1500",
            "RUB",
            "1000",
            "PLA Basic",
            "available",
            "",
            "",
        ]
    )
    # BOM — чтобы Excel распознал UTF-8; "sep=," — чтобы Excel (в т.ч. RU-локаль,
    # где разделитель по умолчанию ";") разбил файл на колонки по запятой.
    content = "﻿" + "sep=,\r\n" + buffer.getvalue()
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=filament_import_template.csv"},
    )


async def _execute_import_plan(
    *,
    db: AsyncSession,
    current_user: User,
    brand: Brand,
    country: str | None,
    rows: list[dict[str, str | None]],
) -> tuple[FilamentImportResult, list[Filament]]:
    """Apply one deterministic import plan to the current transaction.

    The caller either rolls the transaction back (preview) or verifies the
    signed plan and commits it (confirmed import).
    """
    brand_id = brand.id
    result = FilamentImportResult()
    created_filaments: list[Filament] = []
    # Кэш линеек бренда по нижнему регистру имени, чтобы не плодить дубликаты.
    line_cache: dict[str, FilamentLine] = {}
    existing_lines = await db.execute(select(FilamentLine).where(FilamentLine.brand_id == brand_id))
    for line in existing_lines.scalars():
        line_cache[line.name.strip().lower()] = line

    for index, row in enumerate(rows, start=1):
        name = (row.get("name") or "").strip()
        material_type = (row.get("material_type") or "").strip()

        if not name or not material_type:
            result.errors += 1
            result.rows.append(
                FilamentImportRowResult(
                    row=index,
                    status="error",
                    name=name or None,
                    material_type=material_type or None,
                    color_name=(row.get("color_name") or "").strip() or None,
                    message="ERR_VALIDATION_REQUIRED",
                )
            )
            continue

        is_valid, _ = await validate_text_field(name, db, "filament_name")
        if not is_valid:
            result.errors += 1
            result.rows.append(
                FilamentImportRowResult(
                    row=index,
                    status="error",
                    name=name,
                    material_type=material_type,
                    color_name=(row.get("color_name") or "").strip() or None,
                    message="ERR_VALIDATION_TEXT",
                )
            )
            continue

        color_name = (row.get("color_name") or "").strip() or None
        market_color_name = (row.get("market_color_name") or "").strip() or color_name
        color_hex = (row.get("color_hex") or "").strip().upper() or None
        ral_code_value = normalize_ral_code(row.get("ral_code"))
        ral_code = (
            ral_code_value
            if isinstance(ral_code_value, str)
            and ral_code_value.isdigit()
            and len(ral_code_value) == 4
            else None
        )
        price_per_kg = _parse_float(row.get("price_per_kg"))
        currency = (row.get("currency") or "").strip().upper() or None
        spool_weight = _parse_float(row.get("spool_weight"))

        if country and price_per_kg is not None and currency is None:
            result.errors += 1
            result.rows.append(
                FilamentImportRowResult(
                    row=index,
                    status="error",
                    name=name,
                    material_type=material_type,
                    color_name=color_name,
                    message="ERR_PRICE_CURRENCY_PAIR",
                )
            )
            continue

        availability_raw = (row.get("availability") or "").strip().lower()
        availability = (
            FilamentAvailability(availability_raw)
            if availability_raw in _AVAILABILITY_VALUES
            else FilamentAvailability.available
        )
        country_availability = (
            CountryAvailability(availability_raw)
            if availability_raw in _COUNTRY_AVAILABILITY_VALUES
            else CountryAvailability.unknown
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
            if country:
                cell = await db.scalar(
                    select(FilamentCountryCell).where(
                        FilamentCountryCell.filament_id == duplicate,
                        FilamentCountryCell.country == country,
                    )
                )
                if cell is None:
                    cell = FilamentCountryCell(filament_id=duplicate, country=country)
                    db.add(cell)
                cell.availability = country_availability
                cell.price = price_per_kg
                cell.currency = currency if price_per_kg is not None else None
                cell.price_display_unit = "per_kg" if price_per_kg is not None else None
                cell.product_url = (row.get("product_url") or "").strip() or None
                cell.market_note = (row.get("market_note") or "").strip() or None
                cell.market_color_name = market_color_name
                cell.published = filament_cell_has_public_data(cell)
                if price_per_kg is not None:
                    cell.price_updated_at = datetime.now(timezone.utc)
                    cell.price_updated_by_id = current_user.id
                result.updated += 1
                result.rows.append(
                    FilamentImportRowResult(
                        row=index,
                        status="updated",
                        name=name,
                        material_type=material_type,
                        color_name=color_name,
                        filament_id=duplicate,
                    )
                )
                continue
            result.skipped += 1
            result.rows.append(
                FilamentImportRowResult(
                    row=index,
                    status="skipped",
                    name=name,
                    material_type=material_type,
                    color_name=color_name,
                    filament_id=duplicate,
                    message="ERR_FILAMENT_ALREADY_EXISTS",
                )
            )
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

        slug = await choose_filament_slug(
            db=db,
            brand_id=brand_id,
            name=name,
            color_name=color_name,
            ral_code=ral_code,
        )
        if slug is None:
            result.errors += 1
            result.rows.append(
                FilamentImportRowResult(
                    row=index,
                    status="error",
                    name=name,
                    material_type=material_type,
                    color_name=color_name,
                    message="ERR_FILAMENT_ALREADY_EXISTS",
                )
            )
            continue
        filament = Filament(
            brand_id=brand_id,
            contributed_by_organization_id=current_user.active_organization_id,
            line_id=line_id,
            name=name,
            material_type=material_type,
            color_name=color_name,
            color_hex=color_hex if color_hex and color_hex.startswith("#") else None,
            color_group=classify_color_group(
                color_hex if color_hex and color_hex.startswith("#") else None
            ),
            color_group_source="auto",
            ral_code=ral_code,
            price_per_kg=None if country else price_per_kg,
            spool_weight=spool_weight,
            availability=availability,
            slug=slug,
            active=True,
        )
        db.add(filament)
        await db.flush()

        if country:
            cell = FilamentCountryCell(
                filament_id=filament.id,
                country=country,
                availability=country_availability,
                price=price_per_kg,
                currency=currency if price_per_kg is not None else None,
                price_display_unit="per_kg" if price_per_kg is not None else None,
                product_url=(row.get("product_url") or "").strip() or None,
                market_note=(row.get("market_note") or "").strip() or None,
                market_color_name=market_color_name,
            )
            cell.published = filament_cell_has_public_data(cell)
            if price_per_kg is not None:
                cell.price_updated_at = datetime.now(timezone.utc)
                cell.price_updated_by_id = current_user.id
            db.add(cell)

        created_filaments.append(filament)
        result.created += 1
        result.rows.append(
            FilamentImportRowResult(
                row=index,
                status="created",
                name=name,
                material_type=material_type,
                color_name=color_name,
                filament_id=filament.id,
            )
        )

    return result, created_filaments


@router.post("/preview", response_model=FilamentImportPreviewResult)
async def preview_filaments(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    brand_id: int = Query(..., gt=0),
    country: str | None = Query(None, pattern=r"^[A-Za-z]{2}$"),
    file: UploadFile = File(...),
) -> FilamentImportPreviewResult:
    """Build a correctable CSV plan; no catalogue data or QR asset is retained."""
    country = country.upper() if country else None
    brand = await _get_import_brand(
        db=db,
        current_user=current_user,
        brand_id=brand_id,
        country=country,
    )
    raw, rows = await _read_csv_upload(file)
    user_id = current_user.id

    try:
        result, _ = await _execute_import_plan(
            db=db,
            current_user=current_user,
            brand=brand,
            country=country,
            rows=rows,
        )
    finally:
        # Preview deliberately exercises the same writes as apply, then drops
        # the whole transaction. This keeps duplicate/slug/update behaviour
        # identical without leaving catalogue rows, line groups or timestamps.
        await db.rollback()

    for row in result.rows:
        if row.status == "created":
            row.filament_id = None
    token, expires_at = _create_confirmation_token(
        user_id=user_id,
        brand_id=brand_id,
        country=country,
        file_digest=hashlib.sha256(raw).hexdigest(),
        plan_digest=_plan_digest(result),
    )
    return FilamentImportPreviewResult(
        **result.model_dump(),
        file_name=(file.filename or "import.csv")[:255],
        source_rows=_editable_source_rows(rows),
        confirmation_token=token,
        confirmation_expires_at=expires_at,
    )


@router.post("", response_model=FilamentImportResult)
async def import_filaments(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_active_user)],
    brand_id: int = Query(..., gt=0),
    country: str | None = Query(None, pattern=r"^[A-Za-z]{2}$"),
    file: UploadFile = File(...),
    confirmation_token: str = Form(...),
) -> FilamentImportResult:
    """Apply a previously previewed CSV plan after explicit confirmation."""
    country = country.upper() if country else None
    raw, rows = await _read_csv_upload(file)
    expected_plan_digest = _decode_confirmation_token(
        token=confirmation_token,
        user_id=current_user.id,
        brand_id=brand_id,
        country=country,
        file_digest=hashlib.sha256(raw).hexdigest(),
    )
    brand = await _get_import_brand(
        db=db,
        current_user=current_user,
        brand_id=brand_id,
        country=country,
        lock=True,
    )
    result, created_filaments = await _execute_import_plan(
        db=db,
        current_user=current_user,
        brand=brand,
        country=country,
        rows=rows,
    )
    if not hmac.compare_digest(_plan_digest(result), expected_plan_digest):
        await db.rollback()
        raise_error(409, ERR_FILAMENT_IMPORT_CONFIRMATION_INVALID)

    if brand.verified:
        from app.services.qr_service import ensure_filament_qr_code

        for filament in created_filaments:
            await ensure_filament_qr_code(filament, db)
    await db.commit()
    return result
