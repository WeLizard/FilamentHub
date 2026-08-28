"""Build explicit OrcaSlicer bundles for one user-owned physical printer."""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.orca_profile_sync import OrcaProfileBinding, OrcaProfileSyncScope
from app.models.print_profile import PrintProfile
from app.models.printer_profile import PrinterProfile
from app.models.user_printer_device import UserPrinterDevice
from app.services.material_contract_service import list_physical_printers
from app.services.orcaslicer_machine_exporter import (
    print_profile_to_orca_json,
    printer_profile_to_orca_json,
)

ORCA_PRINTER_BUNDLE_FORMAT = "filamenthub.orcaslicer.printer-bundle"
ORCA_PRINTER_BUNDLE_VERSION = 1
ORCA_PRINTER_RECOVERY_FORMAT = "filamenthub.orcaslicer.printer-recovery"
ORCA_PRINTER_RECOVERY_VERSION = 1


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
    if process_profile.configuration_links_resolved:
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
    """Return one archive subset while keeping shared profile payloads canonical."""

    _printers, machine_entries, process_entries = await _build_recovery_catalog(
        db=db,
        user_id=user_id,
        include_machine_profiles=True,
        include_process_profiles=include_process_profiles,
    )
    machine_entries = [
        entry
        for entry in machine_entries
        if physical_printer.id in entry["physical_printer_ids"]
    ]
    process_entries = [
        entry
        for entry in process_entries
        if physical_printer.id in entry["physical_printer_ids"]
    ]

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


def _profile_content_hash(profile: dict[str, Any]) -> str:
    encoded = json.dumps(
        profile,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def _build_recovery_catalog(
    *,
    db: AsyncSession,
    user_id: int,
    include_machine_profiles: bool,
    include_process_profiles: bool,
) -> tuple[list[UserPrinterDevice], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build every recoverable profile once; devices are grouping only."""

    physical_printers = await list_physical_printers(db, user_id)
    physical_ids_by_machine: dict[int, set[int]] = {}
    for physical_printer in physical_printers:
        for link in physical_printer.profile_links:
            physical_ids_by_machine.setdefault(link.printer_profile_id, set()).add(
                physical_printer.id
            )

    process_profiles: list[PrintProfile] = []
    if include_process_profiles:
        process_result = await db.execute(
            select(PrintProfile)
            .options(
                selectinload(PrintProfile.printer_links),
                selectinload(PrintProfile.configuration_links),
            )
            .where(
                PrintProfile.owner_user_id == user_id,
                PrintProfile.active.is_(True),
            )
            .order_by(PrintProfile.id)
        )
        process_profiles = list(process_result.scalars().unique().all())

    contextual_profile_ids = set(physical_ids_by_machine)
    contextual_profile_ids.update(
        link.printer_profile_id
        for profile in process_profiles
        for link in profile.configuration_links
    )
    visible_condition = PrinterProfile.owner_user_id == user_id
    if contextual_profile_ids:
        visible_condition = or_(
            visible_condition,
            (
                PrinterProfile.id.in_(contextual_profile_ids)
                & PrinterProfile.owner_user_id.is_(None)
                & PrinterProfile.is_official.is_(True)
            ),
        )

    result = await db.execute(
        select(PrinterProfile)
        .options(selectinload(PrinterProfile.printer))
        .where(
            PrinterProfile.active.is_(True),
            visible_condition,
        )
        .order_by(PrinterProfile.id)
    )
    machine_profiles = list(result.scalars().all())
    machine_payload_by_id: dict[int, dict[str, Any]] = {}
    machine_entries: list[dict[str, Any]] = []
    for profile in machine_profiles:
        payload = await printer_profile_to_orca_json(profile, db)
        machine_payload_by_id[profile.id] = payload
        # Official vendor profiles are compatibility context. They already
        # exist in Orca and must never be duplicated into our managed bundle.
        if include_machine_profiles and profile.owner_user_id == user_id:
            machine_entries.append(
                {
                    "id": profile.id,
                    "name": payload.get("name") or profile.name,
                    "profile": payload,
                    "content_hash": _profile_content_hash(payload),
                    "physical_printer_ids": sorted(
                        physical_ids_by_machine.get(profile.id, set())
                    ),
                }
            )

    process_entries: list[dict[str, Any]] = []
    if not include_process_profiles or not machine_profiles:
        return physical_printers, machine_entries, process_entries

    for profile in process_profiles:
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
        physical_printer_ids = sorted(
            {
                physical_id
                for machine in matching_machines
                for physical_id in physical_ids_by_machine.get(machine.id, set())
            }
        )
        process_entries.append(
            {
                "id": profile.id,
                "name": payload.get("name") or profile.name,
                "profile": payload,
                "content_hash": _profile_content_hash(payload),
                "physical_printer_ids": physical_printer_ids,
            }
        )
    return physical_printers, machine_entries, process_entries


async def build_orca_printer_recovery_bundle(
    *,
    db: AsyncSession,
    user_id: int,
    source_instance_id: str,
    account_id: str,
    include_machine_profiles: bool,
    include_process_profiles: bool,
    machine_snapshot_complete: bool = False,
    machine_present_local_profile_ids: set[str] | None = None,
    process_snapshot_complete: bool = False,
    process_present_local_profile_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Return the explicit, profile-level recovery payload for one Orca account."""

    physical_printers, machine_entries, process_entries = await _build_recovery_catalog(
        db=db,
        user_id=user_id,
        include_machine_profiles=include_machine_profiles,
        include_process_profiles=include_process_profiles,
    )
    bundle = {
        "format": ORCA_PRINTER_RECOVERY_FORMAT,
        "version": ORCA_PRINTER_RECOVERY_VERSION,
        "scope": {
            "owner_user_id": user_id,
            "source_instance_id": source_instance_id,
            "account_id": account_id,
        },
        "physical_printers": [
            {"id": printer.id, "name": printer.name}
            for printer in physical_printers
        ],
        "machine_profiles": machine_entries,
        "process_profiles": process_entries,
    }
    await _annotate_original_presence(
        db=db,
        bundle=bundle,
        user_id=user_id,
        source_instance_id=source_instance_id,
        account_id=account_id,
        live_observations={
            "machine": (
                machine_snapshot_complete,
                machine_present_local_profile_ids or set(),
            ),
            "process": (
                process_snapshot_complete,
                process_present_local_profile_ids or set(),
            ),
        },
    )
    return bundle


async def _annotate_original_presence(
    *,
    db: AsyncSession,
    bundle: dict[str, Any],
    user_id: int,
    source_instance_id: str,
    account_id: str,
    live_observations: dict[str, tuple[bool, set[str]]],
) -> None:
    """Attach only facts from a finalized full snapshot of this exact Orca account."""

    for kind, entries_key, target_column in (
        ("machine", "machine_profiles", OrcaProfileBinding.printer_profile_id),
        ("process", "process_profiles", OrcaProfileBinding.print_profile_id),
    ):
        live_complete, live_present_ids = live_observations.get(
            kind, (False, set())
        )
        scope = (
            await db.execute(
                select(OrcaProfileSyncScope).where(
                    OrcaProfileSyncScope.owner_user_id == user_id,
                    OrcaProfileSyncScope.source_instance_id == source_instance_id,
                    OrcaProfileSyncScope.account_id == account_id,
                    OrcaProfileSyncScope.kind == kind,
                    OrcaProfileSyncScope.status == "finalized",
                )
            )
        ).scalars().first()
        entries = bundle[entries_key]
        if scope is None and not live_complete:
            for entry in entries:
                entry["original_state"] = "unknown"
            continue

        bindings = list(
            (
                await db.execute(
                    select(OrcaProfileBinding).where(
                        OrcaProfileBinding.owner_user_id == user_id,
                        OrcaProfileBinding.source_instance_id == source_instance_id,
                        OrcaProfileBinding.account_id == account_id,
                        OrcaProfileBinding.kind == kind,
                        target_column.in_([entry["id"] for entry in entries]),
                    )
                )
            ).scalars()
        ) if entries else []
        states_by_target: dict[int, list[bool]] = {}
        for binding in bindings:
            target_id = (
                binding.printer_profile_id
                if kind == "machine"
                else binding.print_profile_id
            )
            if target_id is not None:
                states_by_target.setdefault(target_id, []).append(
                    binding.local_profile_id in live_present_ids
                    if live_complete
                    else binding.present
                )
        for entry in entries:
            observed = states_by_target.get(entry["id"])
            entry["original_state"] = (
                "unknown"
                if observed is None
                else "present"
                if any(observed)
                else "missing"
            )
