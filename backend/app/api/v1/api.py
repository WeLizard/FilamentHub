"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    auth,
    brands,
    calculator,
    filaments,
    presets,
    printers,
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

