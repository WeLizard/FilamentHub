"""Name the user's own printers a sliced job was made for.

A sliced file carries the machine preset and model it was prepared with. A
physical printer is linked to Orca machine profiles, and a Bambu printer is
usually linked only to the catalog's own profiles, so both the user's profiles
and the catalog's count as evidence.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from math import isclose

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.printer_profile import PrinterProfile
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.calculator import CalculatorGcodeParseResponse
from app.services.calculator_printer_compatibility_service import nozzle_values

# Orca names a machine variant "<model> <diameter> nozzle".
_NOZZLE_SUFFIX_RE = re.compile(r"\s+(\d+(?:\.\d+)?)\s*nozzle")
_NOZZLE_TAIL_RE = re.compile(r"(\d+(?:\.\d+)?)\s*nozzle$")
_NOZZLE_TOLERANCE_MM = 0.01


@dataclass(frozen=True, slots=True)
class _LinkedProfile:
    device_id: int
    name: str
    setting_id: str
    nozzles: tuple[float, ...]


def _key(value: str | None) -> str:
    return (value or "").strip().casefold()


def _linked_profile(
    device_id: int,
    name: str,
    setting_id: str | None,
    nozzle_diameters: object,
    nozzle_setting: object,
) -> _LinkedProfile:
    name_key = _key(name)
    nozzles = nozzle_values(nozzle_diameters, nozzle_setting)
    tail = _NOZZLE_TAIL_RE.search(name_key)
    if tail is not None:
        nozzles.append(float(tail.group(1)))
    return _LinkedProfile(device_id, name_key, _key(setting_id), tuple(nozzles))


async def _load_linked_profiles(db: AsyncSession, user_id: int) -> list[_LinkedProfile]:
    rows = await db.execute(
        select(
            UserPrinterDevice.id,
            PrinterProfile.name,
            PrinterProfile.setting_id,
            PrinterProfile.nozzle_diameters,
            PrinterProfile.orcaslicer_settings["nozzle_diameter"],
        )
        .join(
            UserPrinterProfileLink,
            UserPrinterProfileLink.physical_printer_id == UserPrinterDevice.id,
        )
        .join(PrinterProfile, PrinterProfile.id == UserPrinterProfileLink.printer_profile_id)
        .where(
            UserPrinterDevice.user_id == user_id,
            or_(PrinterProfile.owner_user_id == user_id, PrinterProfile.owner_user_id.is_(None)),
        )
    )
    return [_linked_profile(*row) for row in rows.all()]


def _is_model_profile(profile_name: str, model: str) -> bool:
    if profile_name == model:
        return True
    return profile_name.startswith(model) and bool(
        _NOZZLE_SUFFIX_RE.fullmatch(profile_name[len(model) :])
    )


def _carries_nozzle(profile: _LinkedProfile, nozzle_mm: float) -> bool:
    return any(
        isclose(nozzle, nozzle_mm, abs_tol=_NOZZLE_TOLERANCE_MM) for nozzle in profile.nozzles
    )


def _matching_device_ids(
    profiles: Sequence[_LinkedProfile],
    *,
    printer_settings_id: str | None,
    printer_model: str | None,
    nozzle_diameter_mm: float | None,
) -> list[int]:
    """Return the devices of the strongest tier that matches, never a mix of tiers."""
    settings_key = _key(printer_settings_id)
    if settings_key:
        exact = {
            profile.device_id
            for profile in profiles
            if settings_key in (profile.name, profile.setting_id)
        }
        if exact:
            return sorted(exact)

    model_key = _key(printer_model)
    if not model_key:
        return []
    by_model = [profile for profile in profiles if _is_model_profile(profile.name, model_key)]
    if nozzle_diameter_mm:
        # A nozzle the job needs narrows the choice only when someone actually has it.
        by_model = [
            profile for profile in by_model if _carries_nozzle(profile, nozzle_diameter_mm)
        ] or by_model
    return sorted({profile.device_id for profile in by_model})


async def attach_suggested_physical_printers(
    db: AsyncSession,
    jobs: Sequence[CalculatorGcodeParseResponse],
    *,
    user_id: int,
) -> list[CalculatorGcodeParseResponse]:
    """Fill each job's suggested printers with one query for the whole request."""
    if not any(job.printer_settings_id or job.printer_model for job in jobs):
        return list(jobs)
    profiles = await _load_linked_profiles(db, user_id)
    if not profiles:
        return list(jobs)
    return [
        job.model_copy(
            update={
                "suggested_physical_printer_ids": _matching_device_ids(
                    profiles,
                    printer_settings_id=job.printer_settings_id,
                    printer_model=job.printer_model,
                    nozzle_diameter_mm=job.nozzle_diameter_mm,
                )
            }
        )
        for job in jobs
    ]
