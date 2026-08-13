"""Build explicit OrcaSlicer bundles for one user-owned physical printer."""

from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.print_profile import PrintProfile
from app.models.print_profile_configuration import PrintProfileConfigurationLink
from app.models.print_profile_printer import PrintProfilePrinter
from app.models.printer_profile import PrinterProfile
from app.models.user_printer_device import UserPrinterDevice
from app.services.orcaslicer_machine_exporter import (
    print_profile_to_orca_json,
    printer_profile_to_orca_json,
)

ORCA_PRINTER_BUNDLE_FORMAT = "filamenthub.orcaslicer.printer-bundle"
ORCA_PRINTER_BUNDLE_VERSION = 1


def _archive_stem(value: object, fallback: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-.")
    return (stem or fallback)[:100]


def build_orca_printer_archive(bundle: dict[str, Any]) -> bytes:
    """Pack the same explicit bundle as directly loadable Orca JSON files."""

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(bundle, ensure_ascii=False, indent=2),
        )
        for key, folder, suffix in (
            ("machine_profiles", "machine", "orca_printer"),
            ("process_profiles", "process", "orca_process"),
        ):
            for entry in bundle.get(key, []):
                profile_id = int(entry["id"])
                stem = _archive_stem(entry.get("name"), f"profile-{profile_id}")
                archive.writestr(
                    f"{folder}/{stem}-{profile_id}.{suffix}.json",
                    json.dumps(entry["profile"], ensure_ascii=False, indent=2),
                )
    return output.getvalue()


def _machine_match_keys(profile: PrinterProfile) -> set[str]:
    keys = {profile.slug, profile.name}
    if profile.printer is not None:
        keys.update(
            value
            for value in (
                profile.printer.slug,
                profile.printer.name,
                profile.printer.model,
            )
            if value
        )
    return {value for value in keys if value}


def _matching_machine_profiles(
    process_profile: PrintProfile,
    machine_profiles: list[PrinterProfile],
) -> list[PrinterProfile]:
    exact_configuration_ids = {
        link.printer_profile_id for link in process_profile.configuration_links
    }
    if exact_configuration_ids and process_profile.configuration_links_resolved:
        return [
            machine_profile
            for machine_profile in machine_profiles
            if machine_profile.id in exact_configuration_ids
        ]

    matches_by_id: dict[int, PrinterProfile] = {
        machine_profile.id: machine_profile
        for machine_profile in machine_profiles
        if machine_profile.id in exact_configuration_ids
    }
    for machine_profile in machine_profiles:
        keys = _machine_match_keys(machine_profile)
        for link in process_profile.printer_links:
            if link.relation_type != "explicit":
                continue
            if (
                link.printer_id is not None
                and machine_profile.printer_id == link.printer_id
            ) or link.printer_slug in keys:
                matches_by_id[machine_profile.id] = machine_profile
                break
    return [
        machine_profile
        for machine_profile in machine_profiles
        if machine_profile.id in matches_by_id
    ]


async def build_orca_printer_bundle(
    *,
    db: AsyncSession,
    physical_printer: UserPrinterDevice,
    user_id: int,
    include_process_profiles: bool,
) -> dict[str, Any]:
    """Return loadable managed machine/process profiles for one physical printer."""

    profile_ids = sorted(
        {link.printer_profile_id for link in physical_printer.profile_links}
    )
    machine_profiles: list[PrinterProfile] = []
    if profile_ids:
        result = await db.execute(
            select(PrinterProfile)
            .options(selectinload(PrinterProfile.printer))
            .where(
                PrinterProfile.id.in_(profile_ids),
                PrinterProfile.active.is_(True),
                or_(
                    PrinterProfile.owner_user_id == user_id,
                    (
                        PrinterProfile.owner_user_id.is_(None)
                        & PrinterProfile.is_official.is_(True)
                    ),
                ),
            )
            .order_by(PrinterProfile.id)
        )
        machine_profiles = list(result.scalars().all())

    machine_entries: list[dict[str, Any]] = []
    machine_payload_by_id: dict[int, dict[str, Any]] = {}
    for profile in machine_profiles:
        payload = await printer_profile_to_orca_json(profile, db)
        machine_payload_by_id[profile.id] = payload
        # Stock Orca profiles already exist in the slicer's vendor bundle. They
        # are matching context for custom process profiles, not files to install:
        # exporting them would create a managed duplicate beside the original.
        if profile.owner_user_id == user_id:
            machine_entries.append(
                {
                    "id": profile.id,
                    "name": payload.get("name") or profile.name,
                    "profile": payload,
                }
            )

    process_entries: list[dict[str, Any]] = []
    if include_process_profiles and machine_profiles:
        printer_ids = {
            profile.printer_id
            for profile in machine_profiles
            if profile.printer_id is not None
        }
        printer_slugs = set().union(
            *(_machine_match_keys(profile) for profile in machine_profiles)
        )
        link_conditions = []
        if printer_ids:
            link_conditions.append(PrintProfilePrinter.printer_id.in_(printer_ids))
        if printer_slugs:
            link_conditions.append(PrintProfilePrinter.printer_slug.in_(printer_slugs))

        profiles_by_id: dict[int, PrintProfile] = {}
        profile_options = (
            selectinload(PrintProfile.printer_links),
            selectinload(PrintProfile.configuration_links),
        )
        exact_result = await db.execute(
            select(PrintProfile)
            .join(PrintProfileConfigurationLink)
            .options(*profile_options)
            .where(
                PrintProfile.owner_user_id == user_id,
                PrintProfile.active.is_(True),
                PrintProfileConfigurationLink.printer_profile_id.in_(profile_ids),
            )
        )
        profiles_by_id.update(
            (profile.id, profile) for profile in exact_result.scalars().unique().all()
        )

        if link_conditions:
            legacy_result = await db.execute(
                select(PrintProfile)
                .join(PrintProfilePrinter)
                .options(*profile_options)
                .where(
                    PrintProfile.owner_user_id == user_id,
                    PrintProfile.active.is_(True),
                    PrintProfile.configuration_links_resolved.is_(False),
                    PrintProfilePrinter.relation_type == "explicit",
                    or_(*link_conditions),
                )
            )
            profiles_by_id.update(
                (profile.id, profile)
                for profile in legacy_result.scalars().unique().all()
            )

        for profile in sorted(profiles_by_id.values(), key=lambda item: item.id):
            matching_machines = _matching_machine_profiles(profile, machine_profiles)
            if not matching_machines:
                continue
            compatible_names = [
                str(machine_payload_by_id[machine.id]["name"])
                for machine in matching_machines
            ]
            payload = await print_profile_to_orca_json(
                profile,
                db,
                compatible_printer_names=compatible_names,
                printer_for_tag=matching_machines[0].printer,
            )
            process_entries.append(
                {
                    "id": profile.id,
                    "name": payload.get("name") or profile.name,
                    "profile": payload,
                }
            )

    return {
        "format": ORCA_PRINTER_BUNDLE_FORMAT,
        "version": ORCA_PRINTER_BUNDLE_VERSION,
        "physical_printer": {
            "id": physical_printer.id,
            "name": physical_printer.name,
        },
        "machine_profiles": machine_entries,
        "process_profiles": process_entries,
    }
