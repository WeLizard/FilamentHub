"""Record OrcaSlicer plugin printer-connection observations (stage A).

Staging/evidence only: idempotent upsert per observation hash, credential
stripping, and best-effort match to an existing PrinterProfile by exact
printer_settings_id. No PhysicalPrinter / ConnectionBinding is created here.
"""

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.field_encryption import blind_index, decrypt_field, encrypt_field
from app.models.orca_printer_connection_observation import OrcaPrinterConnectionObservation
from app.models.printer_profile import PrinterProfile
from app.schemas.printer_connection_observation import PrinterConnectionObservationIn

SOURCE = "orcaslicer_plugin"
PAYLOAD_VERSION = 4


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


def _content_hash(
    owner_id: int,
    source_instance_id: str | None,
    connection_ref: str | None,
    printer_settings_id: str | None,
    preset_name: str | None,
    profile_fingerprint: str | None,
    inherits: str | None,
    has_technical_changes: bool | None,
    host_type: str | None,
    endpoint_fingerprint: str | None,
) -> str:
    canonical = "|".join(
        [
            str(owner_id),
            SOURCE,
            source_instance_id or "",
            connection_ref or "",
            printer_settings_id or "",
            preset_name or "",
            profile_fingerprint or "",
            inherits or "",
            "" if has_technical_changes is None else str(bool(has_technical_changes)),
            host_type or "",
            endpoint_fingerprint or "",
        ]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _endpoint_fingerprint(value: str | None, host_type: str | None) -> str | None:
    if not value:
        return None
    canonical = f"{str(host_type or 'generic').lower()}|{value}"
    return blind_index(canonical, context="printer-endpoint-v1")


def observed_endpoint(observation: OrcaPrinterConnectionObservation) -> str | None:
    """Read encrypted endpoint data with a legacy plaintext fallback."""
    if observation.endpoint_ciphertext:
        return decrypt_field(observation.endpoint_ciphertext) or None
    return observation.print_host


def _profile_aliases(profile: PrinterProfile) -> set[str]:
    metadata = profile.extra_metadata if isinstance(profile.extra_metadata, dict) else {}
    raw = metadata.get("renamed_from")
    if isinstance(raw, str):
        values = raw.split(";")
    elif isinstance(raw, list):
        values = raw
    else:
        values = []
    aliases: set[str] = set()
    for value in values:
        alias = str(value).strip()
        if alias.lower().endswith(".json"):
            alias = alias[:-5]
        if alias:
            aliases.add(alias)
    return aliases


def _settings_fingerprint(profile: PrinterProfile) -> str:
    settings = dict(profile.orcaslicer_settings or {})
    for key in ("bundle_id", "fhub_id", "fhub_source", "updated_at"):
        settings.pop(key, None)
    canonical = json.dumps(
        settings,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _match_printer_profile(
    db: AsyncSession,
    owner_id: int,
    obs: PrinterConnectionObservationIn,
) -> int | None:
    """Resolve an observation without converting a stock profile into ownership."""
    # Orca creates a user child when a person adds an endpoint to a read-only
    # system machine. If the child has no technical delta, its parent is the
    # configuration being used; importing the child would only create a
    # duplicate profile. The parent may itself be a user profile (copy of a
    # custom configuration), so prefer the owner scope before official catalog.
    if obs.has_technical_changes is False and obs.inherits:
        parent_candidates = list(
            (
                await db.execute(
                    select(PrinterProfile).where(
                        PrinterProfile.name == obs.inherits,
                        PrinterProfile.active.is_(True),
                    )
                )
            ).scalars()
        )
        owned_parents = [
            profile for profile in parent_candidates if profile.owner_user_id == owner_id
        ]
        if len(owned_parents) == 1:
            return owned_parents[0].id
        if owned_parents:
            # A stock profile with the same display name is not a tie-breaker
            # between two user-owned parents. Guessing here would bind the
            # physical endpoint to a configuration the person did not select.
            return None

        official_parents = [
            profile
            for profile in parent_candidates
            if profile.owner_user_id is None and profile.is_official
        ]
        if obs.vendor_id:
            vendor_parents = [
                profile
                for profile in official_parents
                if isinstance(profile.extra_metadata, dict)
                and profile.extra_metadata.get("orca_vendor_id") == obs.vendor_id
            ]
            if not vendor_parents:
                return None
            official_parents = vendor_parents
        if len(official_parents) == 1:
            return official_parents[0].id

    if obs.printer_settings_id:
        profiles = list(
            (
                await db.execute(
                    select(PrinterProfile).where(
                        PrinterProfile.setting_id == obs.printer_settings_id,
                        PrinterProfile.active.is_(True),
                    )
                )
            ).scalars()
        )
        owned = [profile for profile in profiles if profile.owner_user_id == owner_id]
        if obs.preset_name:
            exact_owned = [profile for profile in owned if profile.name == obs.preset_name]
            if obs.profile_fingerprint:
                exact_owned = [
                    profile
                    for profile in exact_owned
                    if _settings_fingerprint(profile) == obs.profile_fingerprint
                ]
            if len(exact_owned) == 1:
                return exact_owned[0].id
            # The same raw Orca setting id can belong to separately named user
            # configurations. A name or fingerprint disagreement is evidence
            # that this is not the stored profile.
            if owned:
                return None
        elif obs.profile_fingerprint:
            same_settings = [
                profile
                for profile in owned
                if _settings_fingerprint(profile) == obs.profile_fingerprint
            ]
            if len(same_settings) == 1:
                return same_settings[0].id
            if owned:
                return None
        elif len(owned) == 1:
            return owned[0].id

        official = [
            profile
            for profile in profiles
            if profile.owner_user_id is None and profile.is_official
        ]
        if obs.vendor_id:
            same_vendor = [
                profile
                for profile in official
                if isinstance(profile.extra_metadata, dict)
                and profile.extra_metadata.get("orca_vendor_id") == obs.vendor_id
            ]
            if not same_vendor:
                return None
            official = same_vendor
        if obs.preset_name:
            exact = [profile for profile in official if profile.name == obs.preset_name]
            if len(exact) == 1:
                return exact[0].id
            aliases = [
                profile for profile in official if obs.preset_name in _profile_aliases(profile)
            ]
            if len(aliases) == 1:
                return aliases[0].id
            return None
        if obs.printer_model:
            model_matches = [
                profile
                for profile in official
                if isinstance(profile.extra_metadata, dict)
                and profile.extra_metadata.get("printer_model") == obs.printer_model
            ]
            if len(model_matches) == 1:
                return model_matches[0].id
            return None
        if len(official) == 1:
            return official[0].id

        # A supplied user-profile id that disagrees with the stored profile is
        # meaningful negative evidence. Do not erase that difference by falling
        # back to a coincidentally identical display name.
        if not obs.is_system:
            return None

    if not obs.is_system:
        owned_profiles = list(
            (
                await db.execute(
                    select(PrinterProfile).where(
                        PrinterProfile.owner_user_id == owner_id,
                        PrinterProfile.active.is_(True),
                    )
                )
            ).scalars()
        )
        if obs.preset_name:
            exact_owned = [
                profile for profile in owned_profiles if profile.name == obs.preset_name
            ]
            if len(exact_owned) == 1:
                return exact_owned[0].id
        if obs.profile_fingerprint:
            same_settings = [
                profile
                for profile in owned_profiles
                if _settings_fingerprint(profile) == obs.profile_fingerprint
            ]
            if len(same_settings) == 1:
                return same_settings[0].id
        return None

    # Names and renamed_from are safe for stock observations because their
    # namespace is the canonical upstream bundle.
    if not obs.is_system or not obs.preset_name:
        return None
    official_profiles = list(
        (
            await db.execute(
                select(PrinterProfile).where(
                    PrinterProfile.owner_user_id.is_(None),
                    PrinterProfile.is_official.is_(True),
                    PrinterProfile.active.is_(True),
                )
            )
        ).scalars()
    )
    if obs.vendor_id:
        same_vendor = [
            profile
            for profile in official_profiles
            if isinstance(profile.extra_metadata, dict)
            and profile.extra_metadata.get("orca_vendor_id") == obs.vendor_id
        ]
        if not same_vendor:
            return None
        official_profiles = same_vendor
    exact = [profile for profile in official_profiles if profile.name == obs.preset_name]
    if len(exact) == 1:
        return exact[0].id
    aliases = [
        profile for profile in official_profiles if obs.preset_name in _profile_aliases(profile)
    ]
    return aliases[0].id if len(aliases) == 1 else None


async def record_observations(
    db: AsyncSession,
    owner_id: int,
    source_instance_id: str | None,
    observations: Iterable[PrinterConnectionObservationIn],
) -> tuple[int, int, int]:
    """Upsert observations. Returns (accepted, matched, unmatched)."""
    observations = list(observations)

    # Current/visible/presence are snapshot state, not accumulating facts.
    # Observation rows remain as history, but discovery must never recreate a
    # physical printer from a profile which disappeared from the latest Orca
    # snapshot (for example, the endpoint-only predecessor of a stable ref).
    previous_rows = list(
        (
            await db.execute(
                select(OrcaPrinterConnectionObservation).where(
                    OrcaPrinterConnectionObservation.owner_user_id == owner_id,
                    OrcaPrinterConnectionObservation.source == SOURCE,
                    OrcaPrinterConnectionObservation.source_instance_id
                    == source_instance_id,
                )
            )
        ).scalars()
    )
    for row in previous_rows:
        payload = dict(row.sanitized_payload or {})
        changed = False
        if payload.get("is_current") is True:
            payload["is_current"] = False
            changed = True
        if payload.get("is_visible") is True:
            payload["is_visible"] = False
            changed = True
        if payload.get("present_in_snapshot") is not False:
            payload["present_in_snapshot"] = False
            changed = True
        if changed:
            row.sanitized_payload = payload

    accepted = matched = unmatched = 0
    for obs in observations:
        host = _sanitize_host(obs.print_host)
        endpoint_fingerprint = _endpoint_fingerprint(host, obs.host_type)
        content_hash = _content_hash(
            owner_id,
            source_instance_id,
            obs.connection_ref,
            obs.printer_settings_id,
            obs.preset_name if not host else None,
            obs.profile_fingerprint,
            obs.inherits,
            obs.has_technical_changes,
            obs.host_type,
            endpoint_fingerprint,
        )

        matched_id = await _match_printer_profile(db, owner_id, obs)

        sanitized = {
            "connection_ref": obs.connection_ref,
            "preset_name": obs.preset_name,
            "printer_settings_id": obs.printer_settings_id,
            "inherits": obs.inherits,
            "printer_model": obs.printer_model,
            "nozzle_diameter": obs.nozzle_diameter,
            "vendor_id": obs.vendor_id,
            "profile_fingerprint": obs.profile_fingerprint,
            "has_technical_changes": obs.has_technical_changes,
            "is_system": bool(obs.is_system),
            "is_visible": bool(obs.is_visible),
            # The raw endpoint is encrypted in its dedicated column and never
            # copied into the JSON evidence snapshot or logs.
            "endpoint_shared": bool(host),
            "host_type": obs.host_type,
            # Which preset was selected in the slicer at that moment, so the site
            # can offer the machine the person is working on instead of asking.
            "is_current": bool(obs.is_current),
            "present_in_snapshot": True,
        }

        existing = (
            await db.execute(
                select(OrcaPrinterConnectionObservation).where(
                    OrcaPrinterConnectionObservation.owner_user_id == owner_id,
                    OrcaPrinterConnectionObservation.observation_hash == content_hash,
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
                    connection_ref=obs.connection_ref,
                    printer_settings_id=obs.printer_settings_id,
                    preset_name=obs.preset_name,
                    inherits=obs.inherits,
                    printer_model=obs.printer_model,
                    print_host=None,
                    endpoint_ciphertext=encrypt_field(host) if host else None,
                    endpoint_fingerprint=endpoint_fingerprint,
                    host_type=obs.host_type,
                    payload_version=PAYLOAD_VERSION,
                    observation_hash=content_hash,
                    matched_printer_profile_id=matched_id,
                    sanitized_payload=sanitized,
                )
            )
        else:
            # Same endpoint seen again: bump last_seen/received, refresh display
            # fields and match, never touch first_seen_at. An endpoint change
            # produces a different hash, i.e. a separate row.
            existing.last_seen_at = now
            existing.received_at = now
            existing.matched_printer_profile_id = matched_id
            existing.connection_ref = obs.connection_ref
            existing.preset_name = obs.preset_name
            existing.inherits = obs.inherits
            existing.printer_model = obs.printer_model
            existing.print_host = None
            existing.endpoint_ciphertext = encrypt_field(host) if host else None
            existing.endpoint_fingerprint = endpoint_fingerprint
            existing.sanitized_payload = sanitized

        accepted += 1
        if matched_id is not None:
            matched += 1
        else:
            unmatched += 1

    await db.commit()
    return accepted, matched, unmatched
