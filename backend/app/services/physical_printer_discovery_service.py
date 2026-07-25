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


def display_endpoint(binding: PrinterConnectionBinding) -> str | None:
    """A human-readable endpoint label (host[:port]) — never identity or secrets."""
    if binding.host:
        return f"{binding.host}:{binding.port}" if binding.port else binding.host
    return binding.print_host


async def list_user_bindings(db: AsyncSession, user_id: int) -> list[PrinterConnectionBinding]:
    return list(
        (
            await db.execute(
                select(PrinterConnectionBinding)
                .where(PrinterConnectionBinding.user_id == user_id)
                .order_by(PrinterConnectionBinding.physical_printer_id)
            )
        ).scalars().all()
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


async def list_installed_printer_candidates(
    db: AsyncSession, user_id: int
) -> list[dict]:
    """Printer models seen in the user's OrcaSlicer that are not a printer here.

    A model is installed in Orca because the person picked that machine in the
    setup wizard, so it is worth offering — especially for a Bambu, whose presets
    carry no endpoint and are therefore invisible to connection discovery. This
    only proposes: nobody wants six printers created because they once installed
    six vendor profiles out of curiosity.
    """
    from app.models.printer import Printer

    observations = (
        (
            await db.execute(
                select(OrcaPrinterConnectionObservation).where(
                    OrcaPrinterConnectionObservation.owner_user_id == user_id,
                    OrcaPrinterConnectionObservation.print_host.is_(None),
                    OrcaPrinterConnectionObservation.printer_model.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not observations:
        return []

    taken_printer_ids = set(
        (
            await db.execute(
                select(UserPrinterDevice.printer_id).where(
                    UserPrinterDevice.user_id == user_id,
                    UserPrinterDevice.printer_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )

    candidates: dict[str, dict] = {}
    for obs in observations:
        model = (obs.printer_model or "").strip()
        if not model or model in candidates:
            continue
        printer = (
            await db.execute(select(Printer).where(Printer.name == model).limit(1))
        ).scalar_one_or_none()
        printer_id = printer.id if printer else None
        if printer_id is not None and printer_id in taken_printer_ids:
            continue
        candidates[model] = {
            "model": model,
            "printer_id": printer_id,
            "catalog_name": printer.name if printer else None,
            "last_seen_at": obs.last_seen_at,
        }
    return sorted(candidates.values(), key=lambda item: item["model"])


async def current_printer_context(db: AsyncSession, user_id: int) -> dict | None:
    """The machine the user is slicing on right now, as last reported.

    Lets the catalog offer that printer instead of asking the person to pick one
    they have already chosen in the slicer. A snapshot from the last sync, not a
    live subscription: switching presets in OrcaSlicer shows up on the next one.
    """
    observation = (
        await db.execute(
            select(OrcaPrinterConnectionObservation)
            .where(
                OrcaPrinterConnectionObservation.owner_user_id == user_id,
                OrcaPrinterConnectionObservation.sanitized_payload["is_current"]
                .as_boolean()
                .is_(True),
            )
            .order_by(OrcaPrinterConnectionObservation.last_seen_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if observation is None or observation.matched_printer_profile_id is None:
        return None

    physical_printer_id = (
        await db.execute(
            select(UserPrinterProfileLink.physical_printer_id)
            .where(
                UserPrinterProfileLink.user_id == user_id,
                UserPrinterProfileLink.printer_profile_id
                == observation.matched_printer_profile_id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    return {
        "printer_profile_id": observation.matched_printer_profile_id,
        "physical_printer_id": physical_printer_id,
        "preset_name": observation.preset_name,
        "last_seen_at": observation.last_seen_at,
    }
