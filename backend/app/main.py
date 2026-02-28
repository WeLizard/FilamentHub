"""FilamentHub FastAPI Application."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.limiter import limiter
from app.middleware.maintenance import MaintenanceMiddleware
from app.services.maintenance_service import get_maintenance_info

# Create FastAPI app
# Hide OpenAPI docs in production [INFRA-15]
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if settings.DEBUG else None,
    docs_url=f"{settings.API_V1_PREFIX}/docs" if settings.DEBUG else None,
    redoc_url=f"{settings.API_V1_PREFIX}/redoc" if settings.DEBUG else None,
)

# Rate limiting setup
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

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

# Static files for uploaded proof files
# Используем абсолютный путь относительно корня проекта
upload_dir = Path(__file__).parent.parent / settings.UPLOAD_DIR
upload_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(upload_dir)), name="uploads")

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
async def health_check() -> dict[str, str | bool | None]:
    """Health check endpoint."""
    maintenance_info = get_maintenance_info()
    return {
        "status": "ok",
        "version": settings.VERSION,
        "project": settings.PROJECT_NAME,
        "maintenance_mode": maintenance_info["enabled"],
        "maintenance_message": maintenance_info["message"] if maintenance_info["enabled"] else None,
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
from app.api.v1.endpoints import sitemap

app.include_router(api_router, prefix=settings.API_V1_PREFIX)
# Sitemap доступен без префикса API для SEO
app.include_router(sitemap.router)