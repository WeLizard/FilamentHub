"""Local mirror of the published plugin packages.

The download page must never send a visitor's browser to GitHub: it is blocked
for part of our audience and rate-limited for the rest. This module reads the
release server-side, keeps the answer briefly, and copies each package to disk on
first use so later downloads no longer need GitHub at all.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

GITHUB_RELEASES_URL = "https://api.github.com/repos/WeLizard/FilamentHub/releases"
PRINT_FARM_RELEASES_URL = "https://api.github.com/repos/WeLizard/orca-plugins/releases"
RELEASE_TAG_PREFIX = "plugins-v"
CHECKSUM_ASSET = "SHA256SUMS"
METADATA_TTL = timedelta(minutes=15)
HTTP_TIMEOUT = 10.0
# The wheels are tens of kilobytes; anything near this ceiling is not our package.
MAX_ASSET_BYTES = 8 * 1024 * 1024
_RELEASE_PAGE_SIZE = 20

ORCASLICER_PLUGIN = "orcaslicer"
OCTOPRINT_BRIDGE = "octoprint"
PRINT_FARM_PLUGIN = "print_farm"

_ORCA_WHEEL = re.compile(r"^filamenthub-(?P<version>[^-]+)-.*\.whl$", re.IGNORECASE)
_OCTOPRINT_WHEEL = re.compile(
    r"^octoprint[-_]filamenthubbridge-(?P<version>[^-]+)-.*\.whl$", re.IGNORECASE
)
_PRINT_FARM_WHEEL = re.compile(r"^printers-(?P<version>[^-]+)-.*\.whl$", re.IGNORECASE)
_CHECKSUM_LINE = re.compile(r"^(?P<sha256>[0-9a-f]{64})\s+\*?\.?/?(?P<name>.+)$", re.IGNORECASE)


@dataclass(frozen=True)
class PluginPackage:
    """One downloadable package as the published release describes it."""

    plugin: str
    filename: str
    version: str
    size_bytes: int
    sha256: str | None
    source_url: str
    release_url: str


_metadata_lock = asyncio.Lock()
_download_locks: dict[str, asyncio.Lock] = {}
_cached_packages: list[PluginPackage] = []
_cached_at: datetime | None = None


def mirror_dir() -> Path:
    base = Path("/app") if Path("/app").exists() else Path(__file__).resolve().parents[2]
    return base / settings.DISTRIBUTIONS_DIR / "plugins"


def _classify(filename: str) -> tuple[str, str] | None:
    match = _ORCA_WHEEL.match(filename)
    if match:
        return ORCASLICER_PLUGIN, match.group("version")
    match = _OCTOPRINT_WHEEL.match(filename)
    if match:
        return OCTOPRINT_BRIDGE, match.group("version")
    match = _PRINT_FARM_WHEEL.match(filename)
    if match:
        return PRINT_FARM_PLUGIN, match.group("version")
    return None


def _parse_checksums(text: str) -> dict[str, str]:
    sums: dict[str, str] = {}
    for line in text.splitlines():
        match = _CHECKSUM_LINE.match(line.strip())
        if match:
            sums[Path(match.group("name")).name] = match.group("sha256").lower()
    return sums


async def _fetch_release(
    releases_url: str,
    *,
    tag_prefix: str | None = None,
    required_asset: re.Pattern[str] | None = None,
) -> dict | None:
    """The newest published plugin release, or None when GitHub cannot answer.

    Drafts are invisible to an unauthenticated caller, which is exactly what we
    want: an unpublished release must never reach the download page.
    """
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.get(
                releases_url,
                params={"per_page": _RELEASE_PAGE_SIZE},
                headers={"Accept": "application/vnd.github+json"},
            )
            response.raise_for_status()
            releases = response.json()
    except (httpx.HTTPError, ValueError):
        logger.warning("Could not read the plugin releases from GitHub", exc_info=True)
        return None

    if not isinstance(releases, list):
        return None
    for release in releases:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        if tag_prefix and not str(release.get("tag_name") or "").startswith(tag_prefix):
            continue
        if required_asset and not any(
            required_asset.match(str(asset.get("name") or ""))
            for asset in (release.get("assets") or [])
            if isinstance(asset, dict)
        ):
            continue
        return release
    return None


async def _fetch_checksums(assets: list[dict]) -> dict[str, str]:
    asset = next(
        (item for item in assets if str(item.get("name") or "") == CHECKSUM_ASSET),
        None,
    )
    url = asset.get("browser_download_url") if isinstance(asset, dict) else None
    if not url:
        return {}
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Could not read the plugin release checksums", exc_info=True)
        return {}
    return _parse_checksums(response.text)


async def _packages_from_release(
    release: dict,
    allowed_plugins: frozenset[str],
) -> list[PluginPackage]:
    assets = [item for item in (release.get("assets") or []) if isinstance(item, dict)]
    checksums = await _fetch_checksums(assets)
    release_url = str(release.get("html_url") or "")

    packages: list[PluginPackage] = []
    for asset in assets:
        filename = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        classified = _classify(filename)
        if classified is None or classified[0] not in allowed_plugins or not url:
            continue
        plugin, version = classified
        packages.append(
            PluginPackage(
                plugin=plugin,
                filename=filename,
                version=version,
                size_bytes=int(asset.get("size") or 0),
                sha256=checksums.get(filename),
                source_url=url,
                release_url=release_url,
            )
        )
    return packages


async def _load_source(
    releases_url: str,
    allowed_plugins: frozenset[str],
    *,
    tag_prefix: str | None = None,
    required_asset: re.Pattern[str] | None = None,
) -> list[PluginPackage] | None:
    release = await _fetch_release(
        releases_url,
        tag_prefix=tag_prefix,
        required_asset=required_asset,
    )
    if release is None:
        return None
    return await _packages_from_release(release, allowed_plugins)


async def get_packages(*, force_refresh: bool = False) -> list[PluginPackage]:
    """Packages of the newest published release, cached for a short while.

    Keeps the previous answer when GitHub is unreachable: a listing that empties
    itself during an outage would tell people the plugin no longer exists.
    """
    global _cached_packages, _cached_at

    async with _metadata_lock:
        fresh = (
            _cached_at is not None
            and datetime.now(timezone.utc) - _cached_at < METADATA_TTL
        )
        if fresh and not force_refresh:
            return _cached_packages

        source_results = await asyncio.gather(
            _load_source(
                GITHUB_RELEASES_URL,
                frozenset({ORCASLICER_PLUGIN, OCTOPRINT_BRIDGE}),
                tag_prefix=RELEASE_TAG_PREFIX,
            ),
            _load_source(
                PRINT_FARM_RELEASES_URL,
                frozenset({PRINT_FARM_PLUGIN}),
                required_asset=_PRINT_FARM_WHEEL,
            ),
        )

        packages_by_plugin = {package.plugin: package for package in _cached_packages}
        source_plugins = (
            frozenset({ORCASLICER_PLUGIN, OCTOPRINT_BRIDGE}),
            frozenset({PRINT_FARM_PLUGIN}),
        )
        refreshed = False
        for packages, owned_plugins in zip(source_results, source_plugins, strict=True):
            if packages is None:
                continue
            refreshed = True
            for plugin in owned_plugins:
                packages_by_plugin.pop(plugin, None)
            packages_by_plugin.update({package.plugin: package for package in packages})

        if not refreshed:
            return _cached_packages

        _cached_packages = list(packages_by_plugin.values())
        _cached_at = datetime.now(timezone.utc)
        return _cached_packages


def _stored_path(package: PluginPackage) -> Path:
    return mirror_dir() / package.filename


def _matches_checksum(path: Path, expected: str | None) -> bool:
    if expected is None:
        return True
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected


async def ensure_local_copy(package: PluginPackage) -> Path | None:
    """Path to our own copy, fetching it once if this is the first request."""
    target = _stored_path(package)
    if target.is_file() and _matches_checksum(target, package.sha256):
        return target

    lock = _download_locks.setdefault(package.filename, asyncio.Lock())
    async with lock:
        # Another request may have finished the same download while we waited.
        if target.is_file() and _matches_checksum(target, package.sha256):
            return target
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
                response = await client.get(package.source_url)
                response.raise_for_status()
                payload = response.content
        except httpx.HTTPError:
            logger.warning("Could not mirror plugin package %s", package.filename, exc_info=True)
            return None

        if len(payload) > MAX_ASSET_BYTES:
            logger.warning("Refused an oversized plugin package %s", package.filename)
            return None

        if package.sha256 is not None and hashlib.sha256(payload).hexdigest() != package.sha256:
            logger.warning("Checksum mismatch for plugin package %s", package.filename)
            return None

        target.parent.mkdir(parents=True, exist_ok=True)
        # Write beside the target and rename, so a reader never sees a half file.
        staged = target.with_name(f"{target.name}.part")
        staged.write_bytes(payload)
        staged.replace(target)
        return target
