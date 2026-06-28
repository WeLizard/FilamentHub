"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    auth,
    brand_requests,
    brands,
    calculator,
    catalog_bundles,
    devices,
    downloads,
    feedback,
    filament_import,
    filament_lines,
    filament_reviews,
    filaments,
    notifications,
    orca_preset_slot_sync,
    orca_sync,
    preset_slots,
    preset_versions,
    presets,
    print_profiles,
    printer_profiles,
    printer_requests,
    printers,
    qr,
    saved_presets,
    spool_compat,
    spools,
    wiki,
)

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router)
api_router.include_router(brands.router)
api_router.include_router(devices.router)
api_router.include_router(brand_requests.router)
api_router.include_router(filaments.router)
api_router.include_router(filament_lines.router)
api_router.include_router(filament_import.router)
api_router.include_router(presets.router)
api_router.include_router(preset_versions.router)
api_router.include_router(qr.router)
api_router.include_router(printers.router)
api_router.include_router(printer_profiles.router)
api_router.include_router(print_profiles.router)
api_router.include_router(printer_requests.router)
api_router.include_router(calculator.router)
api_router.include_router(spool_compat.router, prefix="/spool_compat")
api_router.include_router(admin.router)
api_router.include_router(catalog_bundles.router)
api_router.include_router(saved_presets.router)
api_router.include_router(filament_reviews.router)
api_router.include_router(notifications.router)
api_router.include_router(orca_sync.router)
api_router.include_router(orca_preset_slot_sync.router)
api_router.include_router(preset_slots.router)
api_router.include_router(spools.router)
api_router.include_router(feedback.router)
api_router.include_router(downloads.router)
api_router.include_router(wiki.router)
