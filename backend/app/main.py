"""FilamentHub FastAPI Application."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.errors import ERR_PROTECTED_DATA_UNREADABLE
from app.core.field_encryption import FieldDecryptionError
from app.core.limiter import limiter
from app.middleware.catalogue_cache import CatalogueCacheMiddleware
from app.middleware.maintenance import MaintenanceMiddleware
from app.services.file_service import ensure_upload_dir_compatibility, get_upload_root_dir
from app.services.maintenance_service import get_maintenance_info
from app.services.request_region_service import geoip_database_health


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    try:
        await _start_background_tasks(application)
        yield
    finally:
        await _stop_background_tasks(application)


# Create FastAPI app
# Hide OpenAPI docs in production [INFRA-15]
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if settings.DEBUG else None,
    docs_url=f"{settings.API_V1_PREFIX}/docs" if settings.DEBUG else None,
    redoc_url=f"{settings.API_V1_PREFIX}/redoc" if settings.DEBUG else None,
    lifespan=_lifespan,
)

# Rate limiting setup
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.exception_handler(FieldDecryptionError)
async def _field_decryption_error_handler(
    _request: Request,
    _exc: FieldDecryptionError,
) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": {"code": ERR_PROTECTED_DATA_UNREADABLE}},
    )


async def _start_background_tasks(application: FastAPI) -> None:
    """Warm application state and start long-running service tasks."""
    import logging as _logging

    from app.db.session import AsyncSessionLocal
    from app.services.provisional_account_service import (
        run_provisional_account_sweeper,
        sweep_abandoned_provisional_accounts,
    )
    from app.services.subscription_service import refresh_settings_cache

    try:
        async with AsyncSessionLocal() as db:
            await refresh_settings_cache(db)
            await sweep_abandoned_provisional_accounts(db)
    except Exception:
        _logging.getLogger(__name__).warning("Failed to warm app-settings cache", exc_info=True)

    # QR recovery may need to render many images after a storage restore. It is
    # deliberately detached from startup readiness; public QR endpoints still
    # repair an individual missing asset on demand while this sweep is running.
    application.state.qr_repair_task = asyncio.create_task(
        _repair_verified_qr_codes(AsyncSessionLocal),
        name="verified-brand-qr-repair",
    )

    application.state.provisional_account_sweeper_task = asyncio.create_task(
        run_provisional_account_sweeper(AsyncSessionLocal),
        name="provisional-account-sweeper",
    )

    from app.services.inbound_mail_service import run_inbound_mail_poller

    application.state.inbound_mail_task = asyncio.create_task(
        run_inbound_mail_poller(AsyncSessionLocal),
        name="inbound-mail-poller",
    )

    # The document renderer is a heavy native library loaded on first use, which
    # made the first person to ask for a quote after every deploy wait a second
    # and a half for someone else's import. Pay it here, in the background,
    # where nobody is waiting.
    application.state.pdf_warmup_task = asyncio.create_task(
        _warm_pdf_renderer(), name="pdf-renderer-warmup"
    )


async def _warm_pdf_renderer() -> None:
    import logging as _logging

    from starlette.concurrency import run_in_threadpool

    def load() -> None:
        from weasyprint import HTML  # noqa: F401

    try:
        await run_in_threadpool(load)
    except Exception:  # noqa: BLE001 — a missing renderer must not stop the server
        _logging.getLogger(__name__).warning("PDF renderer unavailable", exc_info=True)


async def _repair_verified_qr_codes(session_factory) -> None:
    import logging as _logging

    from app.services.qr_service import repair_verified_brand_qr_codes

    try:
        async with session_factory() as db:
            repaired = await repair_verified_brand_qr_codes(db)
            await db.commit()
        if repaired:
            _logging.getLogger(__name__).info(
                "Restored %d missing verified-brand QR codes", repaired
            )
    except Exception:  # noqa: BLE001 — recovery must never make the API unavailable
        # The public QR endpoint and representative fallback can still repair
        # individual labels if the background sweep cannot complete.
        _logging.getLogger(__name__).warning(
            "Failed to repair verified-brand QR codes", exc_info=True
        )


async def _stop_background_tasks(application: FastAPI) -> None:
    for name in (
        "provisional_account_sweeper_task",
        "inbound_mail_task",
        "pdf_warmup_task",
        "qr_repair_task",
    ):
        task = getattr(application.state, name, None)
        if task is None:
            continue
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


# Catalogue caching sits inside maintenance and CORS: a maintenance block must
# never be cached, and the CORS headers must reach even a 304.
app.add_middleware(CatalogueCacheMiddleware)

# Maintenance mode middleware (должен быть перед CORS для блокировки запросов)
app.add_middleware(MaintenanceMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-API-Key",
        "X-CSRF-Token",
        "Accept",
        "Origin",
    ],
)

# Static files for uploaded files
upload_dir = get_upload_root_dir()
ensure_upload_dir_compatibility()


class PublicStaticFiles(StaticFiles):
    """Uploads mount minus assets that require an authorization decision.

    Proof files are served only via the authed endpoints
    /brand-requests/{id}/proof/{file} and /printer-requests/{id}/proof/{file}.
    Managed Wiki media is served via /api/v1/wiki/media/{public_id}.webp so staged
    assets cannot bypass the publication and ownership checks.
    """

    _protected_prefixes = (
        "brand_requests/",
        "printer_requests/",
        "database_dumps/",
        "wiki_media/",
    )
    _immutable_prefixes = (
        "avatars/",
        "brand_logos/",
    )

    async def get_response(self, path: str, scope):
        normalized_path = path.replace("\\", "/").lstrip("/")
        if normalized_path.startswith(self._protected_prefixes):
            raise StarletteHTTPException(status_code=404)
        response = await super().get_response(path, scope)
        if response.status_code == 200 and normalized_path.startswith(self._immutable_prefixes):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


app.mount("/uploads", PublicStaticFiles(directory=str(upload_dir)), name="uploads")

# Static files for distributions (OrcaSlicer builds)
distributions_dir = Path(__file__).parent.parent / settings.DISTRIBUTIONS_DIR
distributions_dir.mkdir(parents=True, exist_ok=True)
app.mount("/distributions", StaticFiles(directory=str(distributions_dir)), name="distributions")

# Static files for QR codes (изображения QR-кодов для печати)
qr_codes_dir = Path(__file__).parent.parent / settings.QR_CODES_DIR
qr_codes_dir.mkdir(parents=True, exist_ok=True)
app.mount("/qr_codes", StaticFiles(directory=str(qr_codes_dir)), name="qr_codes")

# Static files for Wiki images
# Картинки лежат в wiki_content/images/, доступны по /wiki_content/images/
wiki_images_dir = Path(__file__).parent.parent / "wiki_content" / "images"
wiki_images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/wiki_content/images", StaticFiles(directory=str(wiki_images_dir)), name="wiki-images")


# Health check endpoint
@app.get("/health")
async def health_check() -> dict[str, object]:
    """Health check endpoint."""
    from app.services.inbound_mail_service import mail_storage_health

    maintenance_info = get_maintenance_info()
    return {
        "status": "ok",
        "version": settings.VERSION,
        "project": settings.PROJECT_NAME,
        "maintenance_mode": maintenance_info["enabled"],
        "maintenance_message": maintenance_info["message"] if maintenance_info["enabled"] else None,
        "auth_region": geoip_database_health(),
        "inbound_mail_storage": mail_storage_health(),
    }


# Root endpoint
@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} API",
        "version": settings.VERSION,
        "docs": f"{settings.API_V1_PREFIX}/docs",
        "api": f"{settings.API_V1_PREFIX}",
    }


# Include API routers
from app.api.v1.api import api_router
from app.api.v1.endpoints import sitemap, spool_compat

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
# Sitemap доступен без префикса API для SEO
app.include_router(sitemap.router)
# Clean spool_compat mount: /spool_compat/{api_key}/api/v1/spool
# Moonraker config: server: https://filamenthub.ru/spool_compat/{api_key}
app.include_router(spool_compat.router, prefix="/spool_compat")
