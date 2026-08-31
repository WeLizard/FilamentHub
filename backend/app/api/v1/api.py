"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    achievements,
    admin,
    auth,
    brand_invites,
    brand_representatives,
    brand_requests,
    brand_team,
    brands,
    calculator,
    catalog_bundles,
    catalog_urls,
    country_cells,
    crm,
    currencies,
    devices,
    downloads,
    email_communications,
    feedback,
    filament_import,
    filament_lines,
    filament_reviews,
    filaments,
    labels,
    manufacturer_qr,
    notification_campaigns,
    notifications,
    octoprint_bridge,
    orca_preset_slot_sync,
    orca_slices,
    orca_sync,
    physical_printers,
    preset_versions,
    presets,
    print_jobs,
    print_profiles,
    printer_bridge,
    printer_connections,
    printer_profiles,
    printer_requests,
    printers,
    qr,
    saved_presets,
    spool_compat,
    spool_qr,
    spools,
    wiki,
    wiki_authoring,
)

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router)
api_router.include_router(achievements.router)
api_router.include_router(currencies.router)
api_router.include_router(catalog_urls.router)
api_router.include_router(brands.router)
api_router.include_router(brand_invites.router)
api_router.include_router(brand_invites.admin_router)
api_router.include_router(email_communications.admin_router)
api_router.include_router(devices.router)
api_router.include_router(physical_printers.router)
api_router.include_router(printer_bridge.router)
api_router.include_router(printer_connections.router)
api_router.include_router(brand_requests.router)
api_router.include_router(brand_team.router)
api_router.include_router(brand_representatives.router)
api_router.include_router(filaments.router)
api_router.include_router(filament_lines.router)
api_router.include_router(filament_import.router)
api_router.include_router(presets.router)
api_router.include_router(preset_versions.router)
api_router.include_router(print_jobs.router)
api_router.include_router(qr.router)
api_router.include_router(labels.router)
api_router.include_router(manufacturer_qr.router)
api_router.include_router(printers.router)
api_router.include_router(printer_profiles.router)
api_router.include_router(print_profiles.router)
api_router.include_router(printer_requests.router)
api_router.include_router(calculator.router)
api_router.include_router(crm.router)
api_router.include_router(orca_slices.router)
api_router.include_router(country_cells.router)
api_router.include_router(spool_compat.router, prefix="/spool_compat")
api_router.include_router(admin.router)
api_router.include_router(catalog_bundles.router)
api_router.include_router(saved_presets.router)
api_router.include_router(filament_reviews.router)
api_router.include_router(notifications.router)
api_router.include_router(octoprint_bridge.router)
api_router.include_router(notification_campaigns.router)
api_router.include_router(orca_sync.router)
api_router.include_router(orca_preset_slot_sync.router)
api_router.include_router(spools.router)
api_router.include_router(spool_qr.router)
api_router.include_router(feedback.router)
api_router.include_router(downloads.router)
api_router.include_router(wiki.router)
api_router.include_router(wiki_authoring.router)
