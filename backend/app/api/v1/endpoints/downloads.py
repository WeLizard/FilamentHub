"""API endpoints for OrcaSlicer FilamentHub Edition downloads."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

router = APIRouter(prefix="/downloads", tags=["downloads"])


class DownloadVersion(BaseModel):
    """Information about a downloadable version."""

    platform: Literal["windows", "macos", "linux"]
    architecture: Literal["x64", "arm64"]
    version: str
    download_url: str | None
    file_size: str | None
    checksum: str | None
    available: bool


class DownloadVersionsResponse(BaseModel):
    """Response with available download versions."""

    versions: list[DownloadVersion]
    latest_version: str


@router.get("/orcaslicer", response_model=DownloadVersionsResponse)
async def get_orcaslicer_downloads(
    platform: Literal["windows", "macos", "linux"] | None = Query(
        None, description="Filter by platform"
    ),
) -> DownloadVersionsResponse:
    """
    Get available OrcaSlicer FilamentHub Edition download links.
    
    Returns information about available builds for different platforms.
    """
    # TODO: Загружать из базы данных или конфигурации
    # Пока используем статические данные, позже можно добавить модель Build в БД
    
    # Базовая версия
    base_version = "2.0.0-fh"
    
    # Все доступные версии
    all_versions: list[DownloadVersion] = [
        DownloadVersion(
            platform="windows",
            architecture="x64",
            version=base_version,
            download_url=None,  # TODO: Заменить на реальную ссылку после сборки
            file_size="~250 MB",
            checksum=None,
            available=False,  # Пока не собрано
        ),
        DownloadVersion(
            platform="macos",
            architecture="x64",
            version=base_version,
            download_url=None,
            file_size="~280 MB",
            checksum=None,
            available=False,
        ),
        DownloadVersion(
            platform="macos",
            architecture="arm64",
            version=base_version,
            download_url=None,
            file_size="~280 MB",
            checksum=None,
            available=False,
        ),
        DownloadVersion(
            platform="linux",
            architecture="x64",
            version=base_version,
            download_url=None,
            file_size="~250 MB",
            checksum=None,
            available=False,
        ),
    ]
    
    # Фильтруем по платформе если указано
    if platform:
        all_versions = [v for v in all_versions if v.platform == platform]
    
    return DownloadVersionsResponse(
        versions=all_versions,
        latest_version=base_version,
    )


@router.get("/orcaslicer/{platform}/{architecture}", response_model=DownloadVersion)
async def get_orcaslicer_download(
    platform: Literal["windows", "macos", "linux"],
    architecture: Literal["x64", "arm64"],
) -> DownloadVersion:
    """
    Get download link for specific platform and architecture.
    
    Returns download information for the requested build.
    """
    # TODO: Загружать из базы данных или конфигурации
    
    base_version = "2.0.0-fh"
    
    # Определяем размер файла по платформе
    file_size_map = {
        ("windows", "x64"): "~250 MB",
        ("macos", "x64"): "~280 MB",
        ("macos", "arm64"): "~280 MB",
        ("linux", "x64"): "~250 MB",
    }
    
    file_size = file_size_map.get((platform, architecture), "~250 MB")
    
    version = DownloadVersion(
        platform=platform,
        architecture=architecture,
        version=base_version,
        download_url=None,  # TODO: Заменить на реальную ссылку
        file_size=file_size,
        checksum=None,
        available=False,
    )
    
    if not version.available:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Build for {platform} ({architecture}) is not available yet",
        )
    
    return version

