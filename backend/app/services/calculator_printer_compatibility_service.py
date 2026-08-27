"""Explainable, read-only compatibility for calculator machine preflight."""

from __future__ import annotations

from math import isclose
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ERR_PRINTER_NOT_FOUND, raise_error
from app.models.filament import Filament
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.calculator import (
    CalculatorPreflightLineRequest,
    CalculatorPreflightMachineEvidence,
    CalculatorPreflightRequest,
    CalculatorPrinterCompatibilityCheck,
    CalculatorPrinterCompatibilityResponse,
    CalculatorPrinterCompatibilityStatus,
)

_NOZZLE_TYPE_HRC = {
    "hardened_steel": 55.0,
    "stainless_steel": 20.0,
    "tungsten_carbide": 85.0,
    "brass": 2.0,
    "e3d": 55.0,
}


def _first(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _number(value: Any) -> float | None:
    try:
        parsed = float(_first(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _numbers(value: Any) -> list[float]:
    values = value if isinstance(value, (list, tuple)) else [value]
    result: list[float] = []
    for item in values:
        try:
            parsed = float(item)
        except (TypeError, ValueError):
            continue
        if parsed > 0 and not any(isclose(parsed, known, abs_tol=0.001) for known in result):
            result.append(parsed)
    return sorted(result)


def _profile_nozzles(profile: PrinterProfile) -> list[float]:
    if profile.nozzle_diameters:
        return _numbers(profile.nozzle_diameters)
    return _numbers((profile.orcaslicer_settings or {}).get("nozzle_diameter"))


def profile_nozzle_hrc(profile: PrinterProfile | None) -> float | None:
    """Return the configured nozzle hardness when the profile proves it.

    This small fact is shared by calculator preflight and preset
    recommendations. Keeping one decoder matters because Orca profiles may
    describe the same nozzle either with an explicit HRC value or a nozzle
    material enum.
    """
    if profile is None:
        return None
    settings = profile.orcaslicer_settings or {}
    explicit = _number(settings.get("nozzle_hrc"))
    if explicit is not None:
        return explicit
    nozzle_type = _first(settings.get("nozzle_type"))
    if not isinstance(nozzle_type, str):
        return None
    return _NOZZLE_TYPE_HRC.get(nozzle_type.strip().casefold())


def _exact_profile(
    evidence: CalculatorPreflightMachineEvidence,
    profiles: list[PrinterProfile],
) -> PrinterProfile | None:
    if evidence.printer_profile_id is not None:
        by_id = [profile for profile in profiles if profile.id == evidence.printer_profile_id]
        if len(by_id) == 1:
            return by_id[0]
    if evidence.printer_settings_id:
        by_setting = [
            profile
            for profile in profiles
            if profile.setting_id == evidence.printer_settings_id
        ]
        if len(by_setting) == 1:
            return by_setting[0]
    return None


def _configuration_for_evidence(
    evidence: CalculatorPreflightMachineEvidence,
    profiles: list[PrinterProfile],
) -> tuple[PrinterProfile | None, list[float]]:
    exact = _exact_profile(evidence, profiles)
    if exact is not None:
        return exact, _profile_nozzles(exact)

    available = sorted(
        {
            nozzle
            for profile in profiles
            for nozzle in _profile_nozzles(profile)
        }
    )
    if evidence.nozzle_diameter_mm is None:
        return None, available
    matching = [
        profile
        for profile in profiles
        if any(
            isclose(evidence.nozzle_diameter_mm, nozzle, abs_tol=0.01)
            for nozzle in _profile_nozzles(profile)
        )
    ]
    return (matching[0] if len(matching) == 1 else None), available


def _overall_status(
    checks: list[CalculatorPrinterCompatibilityCheck],
) -> CalculatorPrinterCompatibilityStatus:
    if any(check.status == "incompatible" for check in checks):
        return "incompatible"
    if not checks or any(check.status == "unknown" for check in checks):
        return "unknown"
    return "compatible"


async def calculate_printer_compatibility(
    db: AsyncSession,
    *,
    user_id: int,
    payload: CalculatorPreflightRequest,
    target_filaments: dict[int, Filament],
) -> CalculatorPrinterCompatibilityResponse | None:
    """Compare only facts the selected printer and sliced jobs actually prove."""
    if payload.physical_printer_id is None:
        return None

    physical_printer = await db.scalar(
        select(UserPrinterDevice).where(
            UserPrinterDevice.id == payload.physical_printer_id,
            UserPrinterDevice.user_id == user_id,
        )
    )
    if physical_printer is None:
        raise_error(404, ERR_PRINTER_NOT_FOUND)

    profiles = (
        await db.execute(
            select(PrinterProfile)
            .join(
                UserPrinterProfileLink,
                UserPrinterProfileLink.printer_profile_id == PrinterProfile.id,
            )
            .where(
                UserPrinterProfileLink.user_id == user_id,
                UserPrinterProfileLink.physical_printer_id == physical_printer.id,
            )
            .order_by(PrinterProfile.id)
        )
    ).scalars().all()
    catalog_printer = (
        await db.get(Printer, physical_printer.printer_id)
        if physical_printer.printer_id is not None
        else None
    )

    lines_by_job: dict[str | None, list[CalculatorPreflightLineRequest]] = {}
    for line in payload.lines:
        lines_by_job.setdefault(line.job_key, []).append(line)

    checks: list[CalculatorPrinterCompatibilityCheck] = []
    for evidence in payload.machine_evidence:
        profile, available_nozzles = _configuration_for_evidence(evidence, profiles)
        profile_fields = {
            "printer_profile_id": profile.id if profile is not None else None,
            "printer_profile_name": profile.name if profile is not None else None,
        }

        if evidence.nozzle_diameter_mm is not None:
            if not available_nozzles:
                nozzle_status: CalculatorPrinterCompatibilityStatus = "unknown"
            elif any(
                isclose(evidence.nozzle_diameter_mm, nozzle, abs_tol=0.01)
                for nozzle in available_nozzles
            ):
                nozzle_status = "compatible"
            else:
                nozzle_status = "incompatible"
            checks.append(
                CalculatorPrinterCompatibilityCheck(
                    kind="nozzle_diameter",
                    status=nozzle_status,
                    job_key=evidence.job_key,
                    required_value=evidence.nozzle_diameter_mm,
                    available_values=available_nozzles,
                    unit="mm",
                    requirement_source="gcode",
                    capability_source="printer_profile" if available_nozzles else None,
                    **profile_fields,
                )
            )

        for line in lines_by_job.get(evidence.job_key, []):
            filament = target_filaments.get(line.filament_id or 0)
            required_hrc = filament.required_nozzle_hrc if filament is not None else None
            if required_hrc is None or required_hrc <= 0:
                continue
            configured_hrc = profile_nozzle_hrc(profile)
            if configured_hrc is None:
                hrc_status: CalculatorPrinterCompatibilityStatus = "unknown"
                available_hrc: list[float] = []
            else:
                hrc_status = "compatible" if configured_hrc >= required_hrc else "incompatible"
                available_hrc = [configured_hrc]
            checks.append(
                CalculatorPrinterCompatibilityCheck(
                    kind="nozzle_hrc",
                    status=hrc_status,
                    job_key=evidence.job_key,
                    line_id=line.line_id,
                    required_value=float(required_hrc),
                    available_values=available_hrc,
                    unit="HRC",
                    requirement_source="filament_catalog",
                    capability_source="printer_profile" if configured_hrc is not None else None,
                    **profile_fields,
                )
            )

        if evidence.max_nozzle_temperature_c is not None:
            max_temperature = (
                float(catalog_printer.max_extruder_temp)
                if catalog_printer is not None and catalog_printer.max_extruder_temp is not None
                else None
            )
            if max_temperature is None:
                temperature_status: CalculatorPrinterCompatibilityStatus = "unknown"
                available_temperatures: list[float] = []
            else:
                temperature_status = (
                    "compatible"
                    if max_temperature >= evidence.max_nozzle_temperature_c
                    else "incompatible"
                )
                available_temperatures = [max_temperature]
            checks.append(
                CalculatorPrinterCompatibilityCheck(
                    kind="hotend_temperature",
                    status=temperature_status,
                    job_key=evidence.job_key,
                    required_value=evidence.max_nozzle_temperature_c,
                    available_values=available_temperatures,
                    unit="°C",
                    requirement_source="gcode",
                    capability_source="catalog_printer" if max_temperature is not None else None,
                    **profile_fields,
                )
            )

    return CalculatorPrinterCompatibilityResponse(
        physical_printer_id=physical_printer.id,
        physical_printer_name=physical_printer.name,
        status=_overall_status(checks),
        checks=checks,
    )
