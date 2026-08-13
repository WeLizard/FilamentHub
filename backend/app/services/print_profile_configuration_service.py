"""Exact process-profile assignment to slicer machine configurations."""

from collections.abc import Iterable

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
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


def _inherits_name(profile: PrinterProfile) -> str:
    settings = profile.orcaslicer_settings
    if not isinstance(settings, dict):
        return ""
    value = settings.get("inherits")
    return str(value or "").strip()


async def _inherited_configuration_ids(
    db: AsyncSession,
    *,
    owner_user_id: int | None,
    explicit_ids: Iterable[int],
) -> list[int]:
    """Project compatible parent configurations onto the owner's children.

    Orca stores a custom machine as a delta with ``inherits``. A process that
    targets the factory parent is therefore valid for the child too. The
    projection is deliberately owner-local and stops on ambiguous names; it
    never creates another profile or guesses across accounts.
    """
    if owner_user_id is None:
        return []
    base_ids = {int(profile_id) for profile_id in explicit_ids}
    if not base_ids:
        return []

    profiles = list(
        (
            await db.execute(
                select(PrinterProfile).where(
                    PrinterProfile.active.is_(True),
                    _configuration_access(owner_user_id),
                )
            )
        )
        .scalars()
        .all()
    )
    by_name: dict[str, list[PrinterProfile]] = {}
    for profile in profiles:
        by_name.setdefault(profile.name, []).append(profile)
    target_names = {profile.name for profile in profiles if profile.id in base_ids}

    inherited: set[int] = set()
    for candidate in profiles:
        if candidate.owner_user_id != owner_user_id or candidate.id in base_ids:
            continue
        current = candidate
        visited = {current.id}
        while True:
            parent_name = _inherits_name(current)
            if not parent_name:
                break
            if parent_name in target_names:
                inherited.add(candidate.id)
                break
            parents = by_name.get(parent_name, [])
            # An owner profile wins over an official profile with the same
            # display name, matching Orca's local-account shadowing semantics.
            owned = [item for item in parents if item.owner_user_id == owner_user_id]
            parents = owned if owned else parents
            if len(parents) != 1 or parents[0].id in visited:
                break
            current = parents[0]
            visited.add(current.id)
    return sorted(inherited)


async def configuration_ancestor_map(
    db: AsyncSession,
    *,
    owner_user_id: int | None,
    printer_profile_ids: Iterable[int],
) -> dict[int, set[int]]:
    """Map requested configurations to themselves and unambiguous ancestors."""
    requested = sorted({int(profile_id) for profile_id in printer_profile_ids})
    if not requested:
        return {}
    profiles = list(
        (
            await db.execute(
                select(PrinterProfile).where(
                    PrinterProfile.active.is_(True),
                    _configuration_access(owner_user_id),
                )
            )
        )
        .scalars()
        .all()
    )
    by_id = {profile.id: profile for profile in profiles}
    by_name: dict[str, list[PrinterProfile]] = {}
    for profile in profiles:
        by_name.setdefault(profile.name, []).append(profile)

    result: dict[int, set[int]] = {}
    for requested_id in requested:
        current = by_id.get(requested_id)
        if current is None:
            continue
        ancestors = {current.id}
        while True:
            parent_name = _inherits_name(current)
            if not parent_name:
                break
            parents = by_name.get(parent_name, [])
            owned = [item for item in parents if item.owner_user_id == owner_user_id]
            parents = owned if owned else parents
            if len(parents) != 1 or parents[0].id in ancestors:
                break
            current = parents[0]
            ancestors.add(current.id)
        result[requested_id] = ancestors
    return result


async def _inherited_process_configuration_ids(
    db: AsyncSession,
    *,
    profile: PrintProfile,
) -> list[int]:
    """Resolve machine links inherited through the Orca process hierarchy."""
    if profile.compatible_printers is not None:
        return []
    parent_name = ""
    if isinstance(profile.orcaslicer_settings, dict):
        parent_name = str(profile.orcaslicer_settings.get("inherits") or "").strip()
    if not parent_name:
        return []

    query = select(PrintProfile).where(PrintProfile.active.is_(True))
    if profile.owner_user_id is None:
        query = query.where(
            PrintProfile.owner_user_id.is_(None),
            PrintProfile.is_official.is_(True),
        )
    else:
        query = query.where(
            or_(
                PrintProfile.owner_user_id == profile.owner_user_id,
                (
                    PrintProfile.owner_user_id.is_(None)
                    & PrintProfile.is_official.is_(True)
                ),
            )
        )
    profiles = list(
        (
            await db.execute(
                query.options(selectinload(PrintProfile.configuration_links))
            )
        )
        .scalars()
        .all()
    )
    by_name: dict[str, list[PrintProfile]] = {}
    for candidate in profiles:
        by_name.setdefault(candidate.name, []).append(candidate)

    visited = {profile.id}
    while parent_name:
        candidates = by_name.get(parent_name, [])
        owned = [
            candidate
            for candidate in candidates
            if candidate.owner_user_id == profile.owner_user_id
        ]
        candidates = owned if owned else candidates
        if len(candidates) != 1 or candidates[0].id in visited:
            return []
        parent = candidates[0]
        visited.add(parent.id)
        parent_ids = {
            link.printer_profile_id for link in parent.configuration_links
        }
        if parent_ids:
            return sorted(parent_ids)
        parent_settings = (
            parent.orcaslicer_settings
            if isinstance(parent.orcaslicer_settings, dict)
            else {}
        )
        parent_name = str(parent_settings.get("inherits") or "").strip()
    return []


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
    inherited_process = (
        await _inherited_process_configuration_ids(db, profile=profile)
        if not validated
        else []
    )
    inherited = await _inherited_configuration_ids(
        db,
        owner_user_id=profile.owner_user_id,
        explicit_ids=[*validated, *inherited_process],
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
            relation_type=(
                "explicit"
                if printer_profile_id in validated
                else "inherited_process"
                if printer_profile_id in inherited_process
                else "inherited_machine"
            ),
        )
        for printer_profile_id in [*validated, *inherited_process, *inherited]
    ]
    db.add_all(links)
    await db.flush()
    # The profile may already be present in this AsyncSession with its old
    # relationship loaded. Keep the response state aligned with the rows we
    # just replaced without triggering an implicit async lazy-load.
    set_committed_value(profile, "configuration_links", links)
    profile.configuration_links_resolved = resolved


async def refresh_owner_configuration_projections(
    db: AsyncSession,
    *,
    owner_user_id: int,
) -> None:
    """Rebuild inherited links after the owner's machine graph changes."""
    profiles = list(
        (
            await db.execute(
                select(PrintProfile)
                .where(PrintProfile.owner_user_id == owner_user_id)
                .options(selectinload(PrintProfile.configuration_links))
            )
        )
        .scalars()
        .all()
    )
    for profile in profiles:
        explicit_ids = [
            link.printer_profile_id
            for link in profile.configuration_links
            if link.relation_type == "explicit"
        ]
        await replace_configuration_links(
            db,
            profile=profile,
            printer_profile_ids=explicit_ids,
            resolved=profile.configuration_links_resolved,
        )


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
