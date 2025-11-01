"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    auth,
    brands,
    calculator,
    # filament_reviews,
    filaments,
    presets,
    printers,
    # saved_presets,
    spoolman,
)

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router)
api_router.include_router(brands.router)
api_router.include_router(filaments.router)
api_router.include_router(presets.router)
api_router.include_router(printers.router)
api_router.include_router(calculator.router)
api_router.include_router(spoolman.router)
api_router.include_router(admin.router)
# api_router.include_router(filament_reviews.router)  # TODO: доделать
# api_router.include_router(saved_presets.router)  # TODO: доделать

