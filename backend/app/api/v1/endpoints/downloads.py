"""API endpoints for OrcaSlicer FilamentHub Edition downloads."""

import hashlib
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/downloads", tags=["downloads"])


def _get_distribution_path(platform: str, architecture: str, version: str, download_type: str = "installer") -> Path:
    """Получить путь к файлу дистрибутива."""
    # Используем абсолютный путь /app для работы в Docker
    base_path = Path("/app") if Path("/app").exists() else Path(__file__).parent.parent.parent
    distributions_dir = base_path / settings.DISTRIBUTIONS_DIR / "orcaslicer"
    
    # Формируем имя файла по платформе и типу
    if platform == "windows":
        if download_type == "portable":
            filename = f"OrcaSlicer-FilamentHub-{version}-win64-portable.zip"
        else:
            filename = f"OrcaSlicer-FilamentHub-{version}-win64.exe"
    elif platform == "macos":
        arch_suffix = "arm64" if architecture == "arm64" else "x64"
        filename = f"OrcaSlicer-FilamentHub-{version}-macos-{arch_suffix}.dmg"
    elif platform == "linux":
        filename = f"OrcaSlicer-FilamentHub-{version}-linux-x64.AppImage"
    else:
        filename = f"OrcaSlicer-FilamentHub-{version}-{platform}-{architecture}"
    
    return distributions_dir / filename


def _file_exists(filepath: Path) -> bool:
    """Проверить существование файла."""
    return filepath.exists() and filepath.is_file()


def _get_file_size(filepath: Path) -> str:
    """Получить размер файла в читаемом формате."""
    if not _file_exists(filepath):
        return "N/A"
    
    size_bytes = filepath.stat().st_size
    size_mb = size_bytes / (1024 * 1024)
    
    if size_mb < 1:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_mb:.1f} MB"


def _calculate_sha256(filepath: Path) -> str | None:
    """Вычислить SHA256 checksum файла."""
    if not _file_exists(filepath):
        return None
    
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        # Читаем файл по частям для больших файлов
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    
    return sha256_hash.hexdigest()


def _get_download_url(request: Request, platform: str, architecture: str, version: str, download_type: str = "installer") -> str | None:
    """Получить URL для скачивания файла."""
    filepath = _get_distribution_path(platform, architecture, version, download_type)
    if not _file_exists(filepath):
        return None
    
    # Формируем URL относительно базового URL
    base_url = str(request.base_url).rstrip("/")
    filename = filepath.name
    return f"{base_url}/distributions/orcaslicer/{filename}"


class DownloadVersion(BaseModel):
    """Information about a downloadable version."""

    platform: Literal["windows", "macos", "linux"]
    architecture: Literal["x64", "arm64"]
    version: str
    download_url: str | None
    file_size: str | None
    checksum: str | None
    available: bool
    download_type: Literal["installer", "portable", "github"] = "installer"  # Тип дистрибутива
    github_url: str | None = None  # Ссылка на GitHub release если есть


class DownloadVersionsResponse(BaseModel):
    """Response with available download versions."""

    versions: list[DownloadVersion]
    latest_version: str


@router.get("/orcaslicer", response_model=DownloadVersionsResponse)
async def get_orcaslicer_downloads(
    request: Request,
    platform: Literal["windows", "macos", "linux"] | None = Query(
        None, description="Filter by platform"
    ),
) -> DownloadVersionsResponse:
    """
    Get available OrcaSlicer FilamentHub Edition download links.
    
    Returns information about available builds for different platforms.
    Проверяет наличие файлов в папке distributions и генерирует URL.
    """
    # Базовая версия
    base_version = "2.0.0-fh"
    
    # Все возможные версии
    possible_versions = [
        ("windows", "x64"),
        ("macos", "x64"),
        ("macos", "arm64"),
        ("linux", "x64"),
    ]
    
    all_versions: list[DownloadVersion] = []
    
    for plat, arch in possible_versions:
        # Проверяем installer
        installer_path = _get_distribution_path(plat, arch, base_version, "installer")
        installer_available = _file_exists(installer_path)
        
        # Проверяем portable (только для Windows)
        portable_available = False
        portable_path = None
        if plat == "windows":
            portable_path = _get_distribution_path(plat, arch, base_version, "portable")
            portable_available = _file_exists(portable_path)
        
        # Приоритет: installer, если нет - portable
        download_type = "installer"
        filepath = installer_path
        available = installer_available
        
        if not available and portable_available:
            download_type = "portable"
            filepath = portable_path
            available = True
        
        download_url = None
        file_size = "N/A"
        checksum = None
        github_url = None
        
        if available:
            download_url = _get_download_url(request, plat, arch, base_version, download_type)
            file_size = _get_file_size(filepath)
            checksum = _calculate_sha256(filepath)
        else:
            # Оценочный размер если файл не найден
            if plat == "windows":
                file_size = "~250 MB"
            elif plat == "macos":
                file_size = "~280 MB"
            elif plat == "linux":
                file_size = "~250 MB"
            # Если нет локального файла, предлагаем GitHub
            github_url = "https://github.com/lizardjazz1/OrcaSlicer/releases"
        
        all_versions.append(
            DownloadVersion(
                platform=plat,
                architecture=arch,
                version=base_version,
                download_url=download_url,
                file_size=file_size,
                checksum=checksum,
                available=available,
                download_type=download_type,
                github_url=github_url,
            )
        )
        
        # Добавляем portable версию отдельно если она есть (только для Windows)
        if plat == "windows" and portable_available and installer_available:
            portable_filepath = _get_distribution_path(plat, arch, base_version, "portable")
            all_versions.append(
                DownloadVersion(
                    platform=plat,
                    architecture=arch,
                    version=base_version,
                    download_url=_get_download_url(request, plat, arch, base_version, "portable"),
                    file_size=_get_file_size(portable_filepath),
                    checksum=_calculate_sha256(portable_filepath),
                    available=True,
                    download_type="portable",
                    github_url=None,
                )
            )
    
    # Фильтруем по платформе если указано
    if platform:
        all_versions = [v for v in all_versions if v.platform == platform]
    
    return DownloadVersionsResponse(
        versions=all_versions,
        latest_version=base_version,
    )


@router.get("/orcaslicer/{platform}/{architecture}", response_model=DownloadVersion)
async def get_orcaslicer_download(
    request: Request,
    platform: Literal["windows", "macos", "linux"],
    architecture: Literal["x64", "arm64"],
) -> DownloadVersion:
    """
    Get download link for specific platform and architecture.
    
    Returns download information for the requested build.
    Проверяет наличие файла и возвращает актуальную информацию.
    """
    base_version = "2.0.0-fh"
    
    filepath = _get_distribution_path(platform, architecture, base_version)
    available = _file_exists(filepath)
    
    download_url = None
    file_size = "N/A"
    checksum = None
    
    if available:
        download_url = _get_download_url(request, platform, architecture, base_version)
        file_size = _get_file_size(filepath)
        checksum = _calculate_sha256(filepath)
    else:
        # Оценочный размер если файл не найден
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
        download_url=download_url,
        file_size=file_size,
        checksum=checksum,
        available=available,
    )
    
    if not version.available:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Build for {platform} ({architecture}) is not available yet",
        )
    
    return version

