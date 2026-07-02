"""Printer request endpoints for users."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.errors import (
    ERR_DELETE_PENDING_ONLY,
    ERR_FILE_NOT_FOUND_IN_REQUEST,
    ERR_PRINTER_REQUEST_NOT_FOUND,
    ERR_PRINTER_REQUEST_PENDING,
    ERR_PRINTER_SLUG_EXISTS,
    ERR_UPLOAD_PENDING_ONLY,
    ERR_VIEW_OWN_REQUESTS_ONLY,
    raise_error,
)
from app.db.session import get_db
from app.models.printer_request import PrinterRequest, PrinterRequestStatus
from app.models.user import User, UserRole
from app.schemas.printer_request import (
    PrinterRequestCreate,
    PrinterRequestListResponse,
    PrinterRequestResponse,
)
from app.services.file_service import (
    delete_proof_file,
    get_upload_root_dir,
    parse_proof_files,
    save_proof_file,
    serialize_proof_files,
)

router = APIRouter(prefix="/printer-requests", tags=["printer-requests"])


@router.post("/", response_model=PrinterRequestResponse, status_code=201)
async def create_printer_request(
    data: PrinterRequestCreate,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterRequestResponse:
    """Создать запрос на добавление принтера (для пользователей)."""
    # Проверяем уникальность slug
    from app.models.printer import Printer

    printer_result = await db.execute(select(Printer).where(Printer.slug == data.slug))
    existing_printer = printer_result.scalar_one_or_none()

    if existing_printer:
        raise_error(400, ERR_PRINTER_SLUG_EXISTS)

    # Проверяем, нет ли уже запроса на этот принтер
    request_result = await db.execute(
        select(PrinterRequest)
        .where(PrinterRequest.slug == data.slug)
        .where(PrinterRequest.status == PrinterRequestStatus.PENDING)
    )
    existing_request = request_result.scalar_one_or_none()

    if existing_request:
        raise_error(400, ERR_PRINTER_REQUEST_PENDING)

    # Проверка текстовых полей на плохие слова
    from app.services.preset_moderation import validate_text_field
    is_valid, error_msg = await validate_text_field(data.name, db, "printer_name")
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    if data.description:
        is_valid, error_msg = await validate_text_field(data.description, db, "printer_description")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    if data.message:
        is_valid, error_msg = await validate_text_field(data.message, db, "message")
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)

    # Сериализуем файлы если они есть
    proof_files_str = serialize_proof_files(data.proof_files) if data.proof_files else None

    # Создаём запрос
    printer_request = PrinterRequest(
        user_id=user.id,
        proof_files=proof_files_str,
        **{k: v for k, v in data.model_dump().items() if k != 'proof_files'}
    )
    db.add(printer_request)
    await db.commit()
    await db.refresh(printer_request)

    response = PrinterRequestResponse.model_validate(printer_request)
    # Парсим файлы для ответа
    if printer_request.proof_files:
        response.proof_files = parse_proof_files(printer_request.proof_files)
    return response


@router.get("/{request_id}/proof/{file_name}")
async def download_proof_file(
    request_id: int,
    file_name: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FileResponse:
    """Отдать proof-файл заявки (только владелец заявки или админ)."""
    result = await db.execute(
        select(PrinterRequest).where(PrinterRequest.id == request_id)
    )
    request = result.scalar_one_or_none()

    if not request:
        raise_error(404, ERR_PRINTER_REQUEST_NOT_FOUND)

    if request.user_id != user.id and user.role != UserRole.ADMIN:
        raise_error(403, ERR_VIEW_OWN_REQUESTS_ONLY)

    base_dir = (get_upload_root_dir() / "printer_requests" / str(request_id)).resolve()
    file_path = (base_dir / file_name).resolve()
    if file_path.parent != base_dir or not file_path.is_file():
        raise_error(404, ERR_FILE_NOT_FOUND_IN_REQUEST)

    return FileResponse(file_path, filename=file_name)


@router.post("/{request_id}/upload", response_model=PrinterRequestResponse)
async def upload_proof_file(
    request_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: UploadFile = File(...),
) -> PrinterRequestResponse:
    """Загрузить файл (скриншот, изображение) для заявки на принтер."""

    # Проверяем, что заявка существует и принадлежит пользователю
    result = await db.execute(
        select(PrinterRequest)
        .where(PrinterRequest.id == request_id)
        .where(PrinterRequest.user_id == user.id)
    )
    printer_request = result.scalar_one_or_none()

    if not printer_request:
        raise_error(404, ERR_PRINTER_REQUEST_NOT_FOUND)

    # Проверяем, что заявка еще не обработана
    if printer_request.status != PrinterRequestStatus.PENDING:
        raise_error(400, ERR_UPLOAD_PENDING_ONLY)

    # Получаем существующие файлы для проверки лимита
    existing_files = parse_proof_files(printer_request.proof_files)

    # Сохраняем файл (с проверкой лимита)
    file_path = await save_proof_file(
        file=file,
        request_id=request_id,
        user_id=user.id,
        request_type="printer",
        existing_files=existing_files,
    )

    # Добавляем файл в список
    existing_files.append(file_path)
    printer_request.proof_files = serialize_proof_files(existing_files)

    await db.commit()
    await db.refresh(printer_request)

    response = PrinterRequestResponse.model_validate(printer_request)
    response.proof_files = parse_proof_files(printer_request.proof_files)
    return response


@router.delete("/{request_id}/files/{file_path:path}", response_model=PrinterRequestResponse)
async def delete_proof_file_endpoint(
    request_id: int,
    file_path: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterRequestResponse:
    """Удалить файл из заявки на принтер."""

    # Проверяем, что заявка существует и принадлежит пользователю
    result = await db.execute(
        select(PrinterRequest)
        .where(PrinterRequest.id == request_id)
        .where(PrinterRequest.user_id == user.id)
    )
    printer_request = result.scalar_one_or_none()

    if not printer_request:
        raise_error(404, ERR_PRINTER_REQUEST_NOT_FOUND)

    # Проверяем, что заявка еще не обработана
    if printer_request.status != PrinterRequestStatus.PENDING:
        raise_error(400, ERR_DELETE_PENDING_ONLY)

    # Удаляем файл из списка
    existing_files = parse_proof_files(printer_request.proof_files)
    if file_path not in existing_files:
        raise_error(404, ERR_FILE_NOT_FOUND_IN_REQUEST)

    existing_files.remove(file_path)

    # Удаляем файл с диска
    await delete_proof_file(file_path)

    # Обновляем заявку
    if existing_files:
        printer_request.proof_files = serialize_proof_files(existing_files)
    else:
        printer_request.proof_files = None

    await db.commit()
    await db.refresh(printer_request)

    response = PrinterRequestResponse.model_validate(printer_request)
    response.proof_files = parse_proof_files(printer_request.proof_files) if printer_request.proof_files else []
    return response


@router.get("/", response_model=PrinterRequestListResponse)
async def list_printer_requests(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    status: PrinterRequestStatus | None = Query(None, description="Фильтр по статусу"),
) -> PrinterRequestListResponse:
    """Получить список запросов на принтеры текущего пользователя."""
    # Build query
    query = select(PrinterRequest).where(PrinterRequest.user_id == user.id)

    if status:
        query = query.where(PrinterRequest.status == status)

    # Count total
    count_query = select(func.count()).select_from(PrinterRequest).where(PrinterRequest.user_id == user.id)
    if status:
        count_query = count_query.where(PrinterRequest.status == status)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * size
    query = query.offset(offset).limit(size).order_by(PrinterRequest.created_at.desc())

    # Execute
    result = await db.execute(query)
    requests = result.scalars().all()

    items = []
    for req in requests:
        response = PrinterRequestResponse.model_validate(req)
        if req.proof_files:
            response.proof_files = parse_proof_files(req.proof_files)
        items.append(response)

    return PrinterRequestListResponse(
        items=items,
        total=total,
    )


@router.get("/{request_id}", response_model=PrinterRequestResponse)
async def get_printer_request(
    request_id: int,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrinterRequestResponse:
    """Получить запрос на принтер по ID (только свой запрос)."""
    result = await db.execute(
        select(PrinterRequest)
        .where(PrinterRequest.id == request_id)
        .where(PrinterRequest.user_id == user.id)
    )
    printer_request = result.scalar_one_or_none()

    if not printer_request:
        raise_error(404, ERR_PRINTER_REQUEST_NOT_FOUND)

    response = PrinterRequestResponse.model_validate(printer_request)
    # Парсим файлы для ответа
    if printer_request.proof_files:
        response.proof_files = parse_proof_files(printer_request.proof_files)
    return response

