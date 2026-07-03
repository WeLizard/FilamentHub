"""API endpoints for OrcaSlicer FilamentHub Edition downloads."""

import hashlib
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import ERR_DOWNLOAD_UNAVAILABLE, raise_error

router = APIRouter(prefix="/downloads", tags=["downloads"])


def _get_distributions_dir() -> Path:
    """Получить путь к папке с дистрибутивами."""
    base_path = Path("/app") if Path("/app").exists() else Path(__file__).parent.parent.parent
    return base_path / settings.DISTRIBUTIONS_DIR / "orcaslicer"


def _parse_version(filename: str) -> tuple[str, str, str] | None:
    """
    Распарсить имя файла и вернуть (версия, платформа, тип).

    Примеры:
    - OrcaSlicer-FilamentHub-2.1.0-fh-win64.exe -> ('2.1.0-fh', 'windows', 'installer')
    - OrcaSlicer-FilamentHub-2.1.0-fh-win64-portable.zip -> ('2.1.0-fh', 'windows', 'portable')
    - OrcaSlicer-FilamentHub-2.1.0-fh-linux-x64.AppImage -> ('2.1.0-fh', 'linux', 'installer')
    """
    # Платформы перечислены явно, всё между префиксом и платформой — версия.
    pattern = r"^OrcaSlicer-FilamentHub-(.+?)-(win64|linux-x64|macos-x64|macos-arm64)(?:-(portable|setup))?\.(exe|zip|dmg|AppImage)$"
    match = re.match(pattern, filename)

    if not match:
        return None

    version = match.group(1)
    platform_raw = match.group(2)
    flavor = match.group(3)
    ext = match.group(4)

    # Определяем платформу
    if "win" in platform_raw:
        platform = "windows"
    elif "macos" in platform_raw or ext == "dmg":
        platform = "macos"
    elif "linux" in platform_raw or ext == "AppImage":
        platform = "linux"
    else:
        platform = platform_raw

    download_type = "portable" if flavor == "portable" else "installer"

    return (version, platform, download_type)


def _scan_available_versions() -> dict[str, list[dict]]:
    """
    Сканировать папку distributions и найти все доступные версии.

    Возвращает dict: {version: [{platform, arch, type, filename}, ...]}
    """
    dist_dir = _get_distributions_dir()
    versions: dict[str, list[dict]] = {}

    if not dist_dir.exists():
        return versions

    for filepath in dist_dir.iterdir():
        if not filepath.is_file():
            continue

        parsed = _parse_version(filepath.name)
        if not parsed:
            continue

        version, platform, download_type = parsed

        # Определяем архитектуру из имени файла
        if "arm64" in filepath.name.lower():
            arch = "arm64"
        else:
            arch = "x64"

        if version not in versions:
            versions[version] = []

        versions[version].append({
            "platform": platform,
            "architecture": arch,
            "download_type": download_type,
            "filename": filepath.name,
            "filepath": filepath,
        })

    return versions


def _get_latest_version() -> str:
    """Получить последнюю версию из доступных файлов."""
    versions = _scan_available_versions()

    if not versions:
        return "2.0.0-fh"  # Fallback

    # Сортируем версии (семантическое сравнение)
    def version_key(v: str) -> tuple:
        # "2.1.0-fh" -> (2, 1, 0)
        nums = re.findall(r"\d+", v)
        return tuple(int(n) for n in nums)

    sorted_versions = sorted(versions.keys(), key=version_key, reverse=True)
    return sorted_versions[0]


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

    # Хэширование больших файлов на каждом запросе очень дорого.
    # Кэш автоматически инвалидируется при изменении размера или mtime файла.
    try:
        stat = filepath.stat()
    except OSError:
        return None

    return _calculate_sha256_cached(
        str(filepath.resolve()),
        stat.st_size,
        stat.st_mtime_ns,
    )


@lru_cache(maxsize=256)
def _calculate_sha256_cached(filepath_str: str, file_size: int, file_mtime_ns: int) -> str:
    """Кэшируем SHA256 по пути/размеру/mtime, чтобы не читать файл повторно."""
    # file_size и file_mtime_ns используются как часть ключа кэша (инвалидация).
    _ = (file_size, file_mtime_ns)

    sha256_hash = hashlib.sha256()
    with open(filepath_str, "rb") as f:
        # Читаем файл по частям для больших файлов
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)

    return sha256_hash.hexdigest()


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

    Автоматически сканирует папку distributions и возвращает все найденные версии.
    Версия, размер и SHA256 определяются из реальных файлов.
    """
    # Сканируем доступные файлы
    available_versions = _scan_available_versions()
    latest_version = _get_latest_version()

    all_downloads: list[DownloadVersion] = []

    # Все возможные комбинации платформ
    possible_platforms = [
        ("windows", "x64"),
        ("macos", "x64"),
        ("macos", "arm64"),
        ("linux", "x64"),
    ]

    # Собираем информацию о найденных файлах
    found_files: dict[tuple, dict] = {}  # (platform, arch, type) -> file_info

    for version, files in available_versions.items():
        for file_info in files:
            key = (file_info["platform"], file_info["architecture"], file_info["download_type"])
            # Берём файл с последней версией
            if key not in found_files:
                found_files[key] = {**file_info, "version": version}
            else:
                # Сравниваем версии, берём новее
                existing_version = found_files[key]["version"]
                if _compare_versions(version, existing_version) > 0:
                    found_files[key] = {**file_info, "version": version}

    # Генерируем ответ для каждой платформы
    for plat, arch in possible_platforms:
        # Проверяем installer
        installer_key = (plat, arch, "installer")
        installer_info = found_files.get(installer_key)

        # Проверяем portable
        portable_key = (plat, arch, "portable")
        portable_info = found_files.get(portable_key)

        # Добавляем installer если есть
        if installer_info:
            filepath = installer_info["filepath"]
            version = installer_info["version"]
            all_downloads.append(
                DownloadVersion(
                    platform=plat,
                    architecture=arch,
                    version=version,
                    download_url=_get_download_url_from_file(request, filepath),
                    file_size=_get_file_size(filepath),
                    checksum=_calculate_sha256(filepath),
                    available=True,
                    download_type="installer",
                    github_url=None,
                )
            )

        # Добавляем portable если есть
        if portable_info:
            filepath = portable_info["filepath"]
            version = portable_info["version"]
            all_downloads.append(
                DownloadVersion(
                    platform=plat,
                    architecture=arch,
                    version=version,
                    download_url=_get_download_url_from_file(request, filepath),
                    file_size=_get_file_size(filepath),
                    checksum=_calculate_sha256(filepath),
                    available=True,
                    download_type="portable",
                    github_url=None,
                )
            )

        # Если нет ни installer ни portable — добавляем placeholder
        if not installer_info and not portable_info:
            file_size_map = {
                "windows": "~250 MB",
                "macos": "~280 MB",
                "linux": "~250 MB",
            }
            all_downloads.append(
                DownloadVersion(
                    platform=plat,
                    architecture=arch,
                    version=latest_version,
                    download_url=None,
                    file_size=file_size_map.get(plat, "~250 MB"),
                    checksum=None,
                    available=False,
                    download_type="installer",
                    github_url="https://github.com/WeLizard/OrcaSlicer/releases",
                )
            )

    # Фильтруем по платформе если указано
    if platform:
        all_downloads = [v for v in all_downloads if v.platform == platform]

    return DownloadVersionsResponse(
        versions=all_downloads,
        latest_version=latest_version,
    )


def _compare_versions(v1: str, v2: str) -> int:
    """Сравнить две версии. Возвращает >0 если v1 > v2."""
    def parse(v: str) -> tuple:
        nums = re.findall(r"\d+", v)
        return tuple(int(n) for n in nums)

    p1, p2 = parse(v1), parse(v2)
    if p1 > p2:
        return 1
    elif p1 < p2:
        return -1
    return 0


@lru_cache(maxsize=1)
def _allowed_download_hosts() -> frozenset[str]:
    """Доверенные хосты для download-URL — из CORS_ORIGINS и BASE_URL (hostname без порта)."""
    hosts: set[str] = set()
    for origin in settings.CORS_ORIGINS:
        parsed = urlparse(origin)
        if parsed.hostname:
            hosts.add(parsed.hostname.lower())
    base_host = urlparse(settings.BASE_URL).hostname
    if base_host:
        hosts.add(base_host.lower())
    return frozenset(hosts)


def _get_download_url_from_file(request: Request, filepath: Path) -> str:
    """Получить URL для скачивания. Хост берём из клиентских заголовков только если он в allowlist
    (CORS_ORIGINS + BASE_URL) — иначе фолбэк на BASE_URL. Защита от Host-header injection."""
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "https")
    candidate = request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or ""
    hostname = candidate.split(":", 1)[0].strip().lower()

    if hostname and hostname in _allowed_download_hosts():
        proto = "https" if "filamenthub.ru" in hostname else forwarded_proto
        base_url = f"{proto}://{candidate}".rstrip("/")
    else:
        base_url = settings.BASE_URL.rstrip("/")
        if base_url.startswith("http://") and "filamenthub.ru" in base_url:
            base_url = base_url.replace("http://", "https://")

    return f"{base_url}/distributions/orcaslicer/{filepath.name}"


@router.get("/orcaslicer/{platform}/{architecture}", response_model=DownloadVersion)
async def get_orcaslicer_download(
    request: Request,
    platform: Literal["windows", "macos", "linux"],
    architecture: Literal["x64", "arm64"],
    download_type: Literal["installer", "portable"] = Query("installer"),
) -> DownloadVersion:
    """
    Get download link for specific platform and architecture.

    Автоматически находит файл нужной версии в папке distributions.
    """
    available_versions = _scan_available_versions()
    _get_latest_version()

    # Ищем файл для запрошенной платформы
    best_match = None
    best_version = None

    for version, files in available_versions.items():
        for file_info in files:
            if (file_info["platform"] == platform and
                file_info["architecture"] == architecture and
                file_info["download_type"] == download_type):
                if best_version is None or _compare_versions(version, best_version) > 0:
                    best_match = file_info
                    best_version = version

    if best_match:
        filepath = best_match["filepath"]
        return DownloadVersion(
            platform=platform,
            architecture=architecture,
            version=best_version,
            download_url=_get_download_url_from_file(request, filepath),
            file_size=_get_file_size(filepath),
            checksum=_calculate_sha256(filepath),
            available=True,
            download_type=download_type,
            github_url=None,
        )

    # Файл не найден
    raise_error(
        status.HTTP_404_NOT_FOUND,
        ERR_DOWNLOAD_UNAVAILABLE,
        {"platform": platform, "arch": architecture, "type": download_type},
    )
