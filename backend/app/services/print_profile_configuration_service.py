"""Exact process-profile assignment to slicer machine configurations."""

from collections.abc import Iterable

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import set_committed_value

from app.core.errors import ERR_PRINTER_PROFILE_NOT_FOUND, raise_error
from app.models.print_profile import PrintProfile
from app.models.print_profile_configuration import PrintProfileConfigurationLink
from app.models.printer_profile import PrinterProfile


def _configuration_access(owner_user_id: int | None):
    if owner_user_id is None:
        return (
            PrinterProfile.owner_user_id.is_(None)
            & PrinterProfile.is_official.is_(True)
        )
    return or_(
        PrinterProfile.owner_user_id == owner_user_id,
        (
            PrinterProfile.owner_user_id.is_(None)
            & PrinterProfile.is_official.is_(True)
        ),
    )


async def validate_printer_profile_ids(
    db: AsyncSession,
    *,
    owner_user_id: int | None,
    printer_profile_ids: Iterable[int],
) -> list[int]:
    """Return unique accessible active configuration IDs or reject the set."""
    requested = sorted({int(profile_id) for profile_id in printer_profile_ids})
    if not requested:
        return []
    found = set(
        (
            await db.execute(
                select(PrinterProfile.id).where(
                    PrinterProfile.id.in_(requested),
                    PrinterProfile.active.is_(True),
                    _configuration_access(owner_user_id),
                )
            )
        )
        .scalars()
        .all()
    )
    if found != set(requested):
        raise_error(404, ERR_PRINTER_PROFILE_NOT_FOUND)
    return requested


async def _resolve_printer_profile_identifiers(
    db: AsyncSession,
    *,
    owner_user_id: int | None,
    identifiers: Iterable[str],
) -> tuple[list[int], bool]:
    """Return exact IDs and whether every non-empty identifier was resolved."""
    names = {str(identifier).strip() for identifier in identifiers if str(identifier).strip()}
    if not names:
        return [], True
    candidates = list(
        (
            await db.execute(
                select(PrinterProfile).where(
                    PrinterProfile.active.is_(True),
                    _configuration_access(owner_user_id),
                    or_(
                        PrinterProfile.name.in_(names),
                        PrinterProfile.slug.in_(names),
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    resolved: set[int] = set()
    resolved_identifiers = 0
    for identifier in names:
        matches = {
            profile.id
            for profile in candidates
            if profile.name == identifier or profile.slug == identifier
        }
        if len(matches) == 1:
            resolved.update(matches)
            resolved_identifiers += 1
    return sorted(resolved), resolved_identifiers == len(names)


async def replace_configuration_links(
    db: AsyncSession,
    *,
    profile: PrintProfile,
    printer_profile_ids: Iterable[int],
    resolved: bool = True,
) -> None:
    """Replace exact configuration assignments after ownership validation."""
    validated = await validate_printer_profile_ids(
        db,
        owner_user_id=profile.owner_user_id,
        printer_profile_ids=printer_profile_ids,
    )
    await db.execute(
        delete(PrintProfileConfigurationLink).where(
            PrintProfileConfigurationLink.print_profile_id == profile.id
        )
    )
    links = [
        PrintProfileConfigurationLink(
            print_profile_id=profile.id,
            printer_profile_id=printer_profile_id,
        )
        for printer_profile_id in validated
    ]
    db.add_all(links)
    await db.flush()
    # The profile may already be present in this AsyncSession with its old
    # relationship loaded. Keep the response state aligned with the rows we
    # just replaced without triggering an implicit async lazy-load.
    set_committed_value(profile, "configuration_links", links)
    profile.configuration_links_resolved = resolved


async def infer_and_replace_configuration_links(
    db: AsyncSession,
    *,
    profile: PrintProfile,
) -> None:
    """Preserve exact Orca machine names without guessing ambiguous matches."""
    inferred, all_identifiers_resolved = await _resolve_printer_profile_identifiers(
        db,
        owner_user_id=profile.owner_user_id,
        identifiers=profile.compatible_printers or [],
    )
    await replace_configuration_links(
        db,
        profile=profile,
        printer_profile_ids=inferred,
        resolved=all_identifiers_resolved,
    )
