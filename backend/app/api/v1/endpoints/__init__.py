"""API v1 endpoints."""

from . import (
    admin,
    auth,
    brand_requests,
    brands,
    calculator,
    downloads,
    filaments,
    orca_sync,
    presets,
    printer_requests,
    printers,
    qr,
    saved_presets,
    spool_compat,
)

__all__ = [
    "admin",
    "auth",
    "brand_requests",
    "brands",
    "calculator",
    "downloads",
    "spool_compat",
    "filaments",
    "presets",
    "printer_requests",
    "printers",
    "qr",
    "saved_presets",
    "orca_sync",
]
