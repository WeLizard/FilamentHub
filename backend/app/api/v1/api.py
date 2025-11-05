"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    auth,
    brand_requests,
    brands,
    calculator,
    filament_reviews,
    filaments,
    presets,
    printer_requests,
    printers,
    qr,
    saved_presets,
    spoolman,
)

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router)
api_router.include_router(brands.router)
api_router.include_router(brand_requests.router)
api_router.include_router(filaments.router)
api_router.include_router(presets.router)
api_router.include_router(qr.router)
api_router.include_router(printers.router)
api_router.include_router(printer_requests.router)
api_router.include_router(calculator.router)
api_router.include_router(spoolman.router)
api_router.include_router(admin.router)
api_router.include_router(saved_presets.router)
api_router.include_router(filament_reviews.router)

