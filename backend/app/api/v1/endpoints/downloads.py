"""Download endpoints for published FilamentHub plugin packages."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.errors import ERR_DOWNLOAD_UNAVAILABLE, raise_error
from app.services import plugin_release_service

router = APIRouter(prefix="/downloads", tags=["downloads"])


def _format_size(size_bytes: int) -> str:
    """Return a human-readable binary file size."""
    size_mb = size_bytes / (1024 * 1024)
    if size_mb < 1:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_mb:.1f} MB"


@lru_cache(maxsize=1)
def _allowed_download_hosts() -> frozenset[str]:
    """Trusted download hosts derived from CORS_ORIGINS and BASE_URL."""
    hosts: set[str] = set()
    for origin in settings.CORS_ORIGINS:
        parsed = urlparse(origin)
        if parsed.hostname:
            hosts.add(parsed.hostname.lower())
    base_host = urlparse(settings.BASE_URL).hostname
    if base_host:
        hosts.add(base_host.lower())
    return frozenset(hosts)


def _safe_base_url(request: Request) -> str:
    """Build a public URL without trusting an arbitrary Host header."""
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "https")
    candidate = request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or ""
    hostname = candidate.split(":", 1)[0].strip().lower()

    if hostname and hostname in _allowed_download_hosts():
        proto = "https" if "filamenthub.ru" in hostname else forwarded_proto
        return f"{proto}://{candidate}".rstrip("/")

    base_url = settings.BASE_URL.rstrip("/")
    if base_url.startswith("http://") and "filamenthub.ru" in base_url:
        base_url = base_url.replace("http://", "https://")
    return base_url


class PluginDownload(BaseModel):
    """One plugin package the site can hand out."""

    plugin: Literal["orcaslicer", "octoprint", "print_farm"]
    filename: str
    version: str
    file_size: str
    checksum: str | None
    download_url: str
    github_url: str | None


class PluginDownloadsResponse(BaseModel):
    """Plugin packages of the newest published release."""

    packages: list[PluginDownload]
    release_url: str | None


@router.get("/plugins", response_model=PluginDownloadsResponse)
async def get_plugin_downloads(request: Request) -> PluginDownloadsResponse:
    """List the published plugin packages.

    The release is read server-side so a visitor's browser never has to reach
    GitHub, which is blocked for part of our audience and rate-limited for the
    rest.
    """
    packages = await plugin_release_service.get_packages()
    base_url = _safe_base_url(request)
    return PluginDownloadsResponse(
        packages=[
            PluginDownload(
                plugin=package.plugin,
                filename=package.filename,
                version=package.version,
                file_size=_format_size(package.size_bytes),
                checksum=package.sha256,
                download_url=f"{base_url}/api/v1/downloads/plugins/{package.filename}",
                github_url=package.release_url or None,
            )
            for package in packages
        ],
        release_url=packages[0].release_url if packages else None,
    )


@router.get("/plugins/{filename}")
async def download_plugin_package(filename: str) -> FileResponse:
    """Serve our own copy of a plugin package, fetching it once if needed."""
    packages = await plugin_release_service.get_packages()
    package = next((item for item in packages if item.filename == filename), None)
    if package is None:
        raise_error(status.HTTP_404_NOT_FOUND, ERR_DOWNLOAD_UNAVAILABLE, {"file": filename})

    path: Path | None = await plugin_release_service.ensure_local_copy(package)
    if path is None:
        raise_error(status.HTTP_503_SERVICE_UNAVAILABLE, ERR_DOWNLOAD_UNAVAILABLE, {"file": filename})

    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=package.filename,
    )
