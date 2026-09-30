"""Resolve Orca catalog model identity once, then use Printer foreign keys.

Printer.name preserves the source machine_model.name. Printer.model is a short
display label and is never an identity or a compatibility lookup key.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.printer import Printer
from app.models.printer_profile import PrinterProfile


def resolve_orca_printer_model(printer: Printer) -> str | None:
    """Return the source model identity, without cosmetic normalization."""
    return printer.name if printer.name and printer.name.strip() else None


def is_orca_system_printer(printer: Printer) -> bool:
    """Only bundle-imported catalog rows carry authoritative Orca names."""
    return printer.source == "system"


def split_orca_printer_identity(
    vendor: str | None, raw_name: str | None
) -> tuple[str, str, str]:
    """Preserve exact source identity; derive manufacturer and short labels."""
    if not raw_name or not raw_name.strip():
        raise ValueError("Orca machine model name is required")
    vendor_text = " ".join((vendor or "").split())
    tokens = raw_name.split()
    if not vendor_text:
        return raw_name, tokens[0], " ".join(tokens)

    vendor_key = re.sub(r"[^a-z0-9]+", "", vendor_text.casefold())
    prefix_key = ""
    for index, token in enumerate(tokens, 1):
        prefix_key += re.sub(r"[^a-z0-9]+", "", token.casefold())
        if vendor_key and prefix_key == vendor_key:
            manufacturer = " ".join(tokens[:index])
            return raw_name, manufacturer, " ".join(tokens[index:]) or manufacturer
        if not vendor_key.startswith(prefix_key):
            break
    return raw_name, vendor_text, " ".join(tokens)


def _identity_text(value: Any) -> str:
    return value if isinstance(value, str) and value.strip() else ""


def legacy_orca_printer_name(vendor: str, canonical_name: str) -> str:
    """Reproduce the retired importer's name solely as a repair lookup alias."""
    vendor = vendor.strip()
    simplified = " ".join(canonical_name.split())
    model = simplified
    if vendor and simplified.lower().startswith(vendor.lower()):
        model = simplified[len(vendor):].strip()
    return f"{vendor} {model}".strip() if vendor else simplified


async def find_exact_orca_printer_profile(
    db: AsyncSession, name: str, owner_user_id: int | None, vendor: str
) -> tuple[PrinterProfile | None, bool]:
    """Resolve within the account, then the official catalog; never other users."""
    if not name:
        return None, False
    scopes = []
    if owner_user_id is not None:
        scopes.append(([PrinterProfile.owner_user_id == owner_user_id], False))
    system_scope = [
        PrinterProfile.owner_user_id.is_(None),
        PrinterProfile.source == "system",
    ]
    scopes.append((system_scope, True))
    for scope, is_system in scopes:
        rows = list((await db.scalars(
            select(PrinterProfile).where(PrinterProfile.name == name, *scope).limit(2)
        )).all())
        if rows:
            if len(rows) > 1 and is_system and vendor:
                rows = list((await db.scalars(
                    select(PrinterProfile).where(
                        PrinterProfile.name == name, *scope,
                        PrinterProfile.vendor == vendor,
                    ).limit(2)
                )).all())
            return (rows[0], False) if len(rows) == 1 else (None, True)
    return None, False


async def resolve_orca_printer_id(
    *,
    db: AsyncSession,
    printer_id: int | None = None,
    printer_slug: str | None = None,
    known_printer_id: int | None = None,
    owner_user_id: int | None = None,
    profile_metadata: dict[str, Any] | None = None,
    profile_settings: dict[str, Any] | None = None,
    profile_vendor: str | None = None,
) -> int | None:
    """Resolve authoritative evidence in order, leaving ambiguity unresolved.

    known_printer_id comes from the caller's already authorized profile lookup.
    No display-name shortening, substring scoring or catalog row creation occurs.
    """
    if printer_id is not None and await db.get(Printer, printer_id) is not None:
        return printer_id
    if printer_slug:
        explicit = await db.scalar(select(Printer.id).where(Printer.slug == printer_slug))
        if explicit is not None:
            return explicit
    if known_printer_id is not None:
        return known_printer_id

    metadata = {**(profile_metadata or {}), **(profile_settings or {})}
    vendor = _identity_text(profile_vendor) or _identity_text(metadata.get("vendor"))
    # Follow exact inheritance in the same visibility boundary, with cycle and
    # depth protection. Parent model evidence is used only if the child lacks it.
    parent_name = _identity_text(metadata.get("inherits"))
    seen: set[str] = set()
    for _ in range(32):
        if not parent_name or parent_name in seen:
            break
        seen.add(parent_name)
        parent, ambiguous = await find_exact_orca_printer_profile(db, parent_name, owner_user_id, vendor)
        if ambiguous:
            return None
        if parent is None:
            break
        if parent.printer_id is not None:
            return parent.printer_id
        parent_metadata = {
            **(parent.extra_metadata or {}), **(parent.orcaslicer_settings or {})
        }
        for key in ("printer_model", "model_id", "printer_model_id"):
            if not _identity_text(metadata.get(key)):
                metadata[key] = parent_metadata.get(key)
        vendor = vendor or _identity_text(parent.vendor)
        parent_name = _identity_text(parent_metadata.get("inherits"))

    canonical_name = _identity_text(metadata.get("printer_model"))
    if canonical_name:
        query = select(Printer.id).where(
            Printer.source == "system", Printer.name == canonical_name
        )
        ids = list((await db.scalars(query.limit(2))).all())
        if len(ids) > 1 and vendor:
            ids = list((await db.scalars(
                query.where(Printer.vendor == vendor).limit(2)
            )).all())
            if len(ids) != 1:
                return None
        if ids:
            return ids[0] if len(ids) == 1 else None

    external_id = (
        _identity_text(metadata.get("model_id"))
        or _identity_text(metadata.get("printer_model_id"))
    )
    if external_id and vendor:
        ids = list((await db.scalars(
            select(Printer.id).where(
                Printer.source == "system",
                Printer.vendor == vendor,
                Printer.model_id == external_id,
            ).limit(2)
        )).all())
        if ids:
            return ids[0] if len(ids) == 1 else None

    # The previous importer prepended the raw vendor even when already present.
    # This precise historical alias may locate one old system row until refresh.
    if canonical_name and vendor:
        ids = list((await db.scalars(
            select(Printer.id).where(
                Printer.source == "system",
                Printer.vendor == vendor,
                Printer.name == legacy_orca_printer_name(vendor, canonical_name),
            ).limit(2)
        )).all())
        if len(ids) == 1:
            return ids[0]
    return None


async def resolve_orca_printer_link(
    *, db: AsyncSession, owner_user_id: int | None, identifier: str,
    profile_vendor: str | None = None,
) -> tuple[int | None, str]:
    """Resolve a process's model evidence without altering raw compatibility.

    Unknown expressions/names retain a discovery label with no inferred FK.
    The original compatible_printers fields remain authoritative for Orca.
    """
    if not identifier:
        return None, ""
    profile, ambiguous = await find_exact_orca_printer_profile(
        db, identifier, owner_user_id, profile_vendor or "",
    )
    if ambiguous:
        return None, (re.sub(r"[^a-z0-9]+", "-", identifier.lower()).strip("-") or "item")[:200]
    printer_id = await resolve_orca_printer_id(
        db=db,
        owner_user_id=owner_user_id,
        profile_vendor=profile_vendor or (profile.vendor if profile is not None else None),
        known_printer_id=profile.printer_id if profile is not None else None,
        profile_metadata=profile.extra_metadata if profile is not None else None,
        profile_settings=(
            profile.orcaslicer_settings if profile is not None
            else {"printer_model": identifier}
        ),
    )
    if printer_id is not None:
        printer = await db.get(Printer, printer_id)
        return printer.id, printer.slug
    return None, (re.sub(r"[^a-z0-9]+", "-", identifier.lower()).strip("-") or "item")[:200]
