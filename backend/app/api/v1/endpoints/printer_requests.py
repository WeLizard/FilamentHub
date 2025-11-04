"""Printer request endpoints for users."""

import json
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.printer_request import PrinterRequest, PrinterRequestStatus
from app.models.user import User
from app.schemas.printer_request import (
    PrinterRequestCreate,
    PrinterRequestListResponse,
    PrinterRequestResponse,
)
from app.services.file_service import (
    delete_proof_file,
    delete_proof_files,
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
        raise HTTPException(
            status_code=400,
            detail="Принтер с таким slug уже существует в базе"
        )
    
    # Проверяем, нет ли уже запроса на этот принтер
    request_result = await db.execute(
        select(PrinterRequest)
        .where(PrinterRequest.slug == data.slug)
        .where(PrinterRequest.status == PrinterRequestStatus.PENDING)
    )
    existing_request = request_result.scalar_one_or_none()
    
    if existing_request:
        raise HTTPException(
            status_code=400,
            detail="Запрос на добавление этого принтера уже существует и ожидает рассмотрения"
        )
    
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
        raise HTTPException(status_code=404, detail="Printer request not found")
    
    # Проверяем, что заявка еще не обработана
    if printer_request.status != PrinterRequestStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Can only upload files to pending requests"
        )
    
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
        raise HTTPException(status_code=404, detail="Printer request not found")
    
    # Проверяем, что заявка еще не обработана
    if printer_request.status != PrinterRequestStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Can only delete files from pending requests"
        )
    
    # Удаляем файл из списка
    existing_files = parse_proof_files(printer_request.proof_files)
    if file_path not in existing_files:
        raise HTTPException(
            status_code=404,
            detail="File not found in request"
        )
    
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
        raise HTTPException(status_code=404, detail="Printer request not found")
    
    response = PrinterRequestResponse.model_validate(printer_request)
    # Парсим файлы для ответа
    if printer_request.proof_files:
        response.proof_files = parse_proof_files(printer_request.proof_files)
    return response


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
        raise HTTPException(status_code=404, detail="Printer request not found")
    
    # Проверяем, что заявка еще не обработана
    if printer_request.status != PrinterRequestStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Can only upload files to pending requests"
        )
    
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
        raise HTTPException(status_code=404, detail="Printer request not found")
    
    # Проверяем, что заявка еще не обработана
    if printer_request.status != PrinterRequestStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail="Can only delete files from pending requests"
        )
    
    # Удаляем файл из списка
    existing_files = parse_proof_files(printer_request.proof_files)
    if file_path not in existing_files:
        raise HTTPException(
            status_code=404,
            detail="File not found in request"
        )
    
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

