"""Stage B: derive physical printers from staged connection observations.

For each observation that carries a connection endpoint, upsert a
PrinterConnectionBinding keyed by the normalized endpoint and, on first sight of
an endpoint, auto-create a physical printer (UserPrinterDevice). Observations
whose preset matched a PrinterProfile also link that profile to the printer
(many-to-many). The endpoint — not a bare IP — is the discovery key, and it is
never treated as the printer's permanent identity.
"""

from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orca_printer_connection_observation import OrcaPrinterConnectionObservation
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.printer_connection_binding import PrinterConnectionBinding
from app.models.user_printer_device import UserPrinterDevice

_DEFAULT_PORTS = {
    "moonraker": 7125, "klipper": 7125, "mainsail": 7125, "fluidd": 7125,
    "octoprint": 5000, "prusalink": 80, "repetier": 80, "bambu": 8883,
}


def normalize_endpoint(print_host: str | None, host_type: str | None) -> dict:
    """Parse a raw host into provider + scheme + host + port + path and a
    canonical key. Same IP with a different port/provider is a different endpoint."""
    provider = (host_type or "").strip().lower() or "generic"
    raw = (print_host or "").strip()
    if raw and "://" not in raw:
        raw = "http://" + raw
    parts = urlsplit(raw)
    scheme = (parts.scheme or "http").lower()
    host = (parts.hostname or "").lower()
    try:
        port = parts.port
    except ValueError:
        port = None
    path = (parts.path or "").rstrip("/")
    if port is None:
        port = _DEFAULT_PORTS.get(provider)
    normalized = "|".join([provider, scheme, host, str(port or ""), path])
    return {
        "provider": provider, "scheme": scheme, "host": host,
        "port": port, "path": path, "normalized": normalized,
    }


async def _ensure_profile_link(
    db: AsyncSession, user_id: int, physical_printer_id: int, profile_id: int
) -> None:
    existing = (
        await db.execute(
            select(UserPrinterProfileLink.id)
            .where(
                UserPrinterProfileLink.physical_printer_id == physical_printer_id,
                UserPrinterProfileLink.printer_profile_id == profile_id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            UserPrinterProfileLink(
                user_id=user_id,
                physical_printer_id=physical_printer_id,
                printer_profile_id=profile_id,
            )
        )


async def reconcile_user_printers(db: AsyncSession, user_id: int) -> int:
    """Upsert physical printers + bindings from the user's observations.

    Idempotent: a known endpoint updates its binding, a new endpoint creates a
    printer. Returns the number of physical printers newly auto-created."""
    observations = (
        await db.execute(
            select(OrcaPrinterConnectionObservation).where(
                OrcaPrinterConnectionObservation.owner_user_id == user_id
            )
        )
    ).scalars().all()

    created = 0
    for obs in observations:
        if not obs.print_host:
            continue
        endpoint = normalize_endpoint(obs.print_host, obs.host_type)

        binding = (
            await db.execute(
                select(PrinterConnectionBinding).where(
                    PrinterConnectionBinding.user_id == user_id,
                    PrinterConnectionBinding.normalized_endpoint == endpoint["normalized"],
                )
            )
        ).scalar_one_or_none()

        if binding is None:
            printer = UserPrinterDevice(
                user_id=user_id,
                name=obs.printer_model or obs.preset_name or endpoint["host"] or "Printer",
                device_fingerprint=None,
                supports_hh=False,
            )
            db.add(printer)
            await db.flush()
            binding = PrinterConnectionBinding(
                user_id=user_id,
                physical_printer_id=printer.id,
                normalized_endpoint=endpoint["normalized"],
                provider=endpoint["provider"],
                scheme=endpoint["scheme"],
                host=endpoint["host"],
                port=endpoint["port"],
                path=endpoint["path"],
                print_host=obs.print_host,
            )
            db.add(binding)
            await db.flush()
            created += 1
        else:
            binding.last_seen_at = datetime.now(timezone.utc)
            binding.print_host = obs.print_host

        if obs.matched_printer_profile_id:
            await _ensure_profile_link(
                db, user_id, binding.physical_printer_id, obs.matched_printer_profile_id
            )

    await db.commit()
    return created
