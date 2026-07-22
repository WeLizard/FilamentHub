"""Record OrcaSlicer plugin printer-connection observations (stage A).

Staging/evidence only: idempotent upsert per observation fingerprint, credential
stripping, and best-effort match to an existing PrinterProfile by exact
printer_settings_id. No PhysicalPrinter / ConnectionBinding is created here.
"""

import hashlib
from collections.abc import Iterable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orca_printer_connection_observation import OrcaPrinterConnectionObservation
from app.models.printer_profile import PrinterProfile
from app.schemas.printer_connection_observation import PrinterConnectionObservationIn

SOURCE = "orcaslicer_plugin"
PAYLOAD_VERSION = 1


def _sanitize_host(value: str | None) -> str | None:
    """Drop URL userinfo (user:pass@), a credential, from the observed host."""
    if not value:
        return value
    raw = value.strip()
    scheme = ""
    rest = raw
    if "://" in raw:
        scheme, rest = raw.split("://", 1)
        scheme += "://"
    authority = rest.split("/", 1)[0]
    remainder = rest[len(authority):]
    if "@" in authority:
        authority = authority.rsplit("@", 1)[1]
    return scheme + authority + remainder


def _fingerprint(
    owner_id: int,
    source_instance_id: str | None,
    printer_settings_id: str | None,
    host_type: str | None,
    print_host: str | None,
) -> str:
    canonical = "|".join(
        [
            str(owner_id),
            SOURCE,
            source_instance_id or "",
            printer_settings_id or "",
            host_type or "",
            print_host or "",
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def record_observations(
    db: AsyncSession,
    owner_id: int,
    source_instance_id: str | None,
    observations: Iterable[PrinterConnectionObservationIn],
) -> tuple[int, int, int]:
    """Upsert observations. Returns (accepted, matched, unmatched)."""
    accepted = matched = unmatched = 0
    for obs in observations:
        host = _sanitize_host(obs.print_host)
        fingerprint = _fingerprint(
            owner_id, source_instance_id, obs.printer_settings_id, obs.host_type, host
        )

        matched_id: int | None = None
        if obs.printer_settings_id:
            result = await db.execute(
                select(PrinterProfile.id)
                .where(
                    PrinterProfile.owner_user_id == owner_id,
                    PrinterProfile.setting_id == obs.printer_settings_id,
                )
                .limit(1)
            )
            matched_id = result.scalar_one_or_none()

        sanitized = {
            "preset_name": obs.preset_name,
            "printer_settings_id": obs.printer_settings_id,
            "inherits": obs.inherits,
            "printer_model": obs.printer_model,
            "print_host": host,
            "host_type": obs.host_type,
        }

        existing = (
            await db.execute(
                select(OrcaPrinterConnectionObservation).where(
                    OrcaPrinterConnectionObservation.owner_user_id == owner_id,
                    OrcaPrinterConnectionObservation.observation_fingerprint == fingerprint,
                )
            )
        ).scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if existing is None:
            db.add(
                OrcaPrinterConnectionObservation(
                    owner_user_id=owner_id,
                    source=SOURCE,
                    source_instance_id=source_instance_id,
                    printer_settings_id=obs.printer_settings_id,
                    preset_name=obs.preset_name,
                    inherits=obs.inherits,
                    printer_model=obs.printer_model,
                    print_host=host,
                    host_type=obs.host_type,
                    payload_version=PAYLOAD_VERSION,
                    observation_fingerprint=fingerprint,
                    matched_printer_profile_id=matched_id,
                    sanitized_payload=sanitized,
                )
            )
        else:
            # Same endpoint seen again: bump last_seen/received, refresh display
            # fields and match, never touch first_seen_at. An endpoint change
            # produces a different fingerprint, i.e. a separate row.
            existing.last_seen_at = now
            existing.received_at = now
            existing.matched_printer_profile_id = matched_id
            existing.preset_name = obs.preset_name
            existing.inherits = obs.inherits
            existing.printer_model = obs.printer_model
            existing.sanitized_payload = sanitized

        accepted += 1
        if matched_id is not None:
            matched += 1
        else:
            unmatched += 1

    await db.commit()
    return accepted, matched, unmatched
