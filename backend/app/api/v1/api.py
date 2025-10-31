"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1.endpoints import brands, filaments

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(brands.router)
api_router.include_router(filaments.router)

