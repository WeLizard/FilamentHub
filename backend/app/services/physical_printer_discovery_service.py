"""Stage B: derive physical printers from staged connection observations.

For each observation that carries a connection endpoint, upsert a
PrinterConnectionBinding keyed by the normalized endpoint and, on first sight of
an endpoint, auto-create a physical printer (UserPrinterDevice). Observations
whose preset matched a PrinterProfile also link that profile to the printer
(many-to-many). A shared profile is configuration, never physical identity.
"""

import hashlib
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.field_encryption import blind_index, decrypt_field, encrypt_field
from app.models.orca_printer_connection_observation import OrcaPrinterConnectionObservation
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.printer_connection_binding import PrinterConnectionBinding
from app.models.printer_profile import PrinterProfile
from app.models.user_printer_device import UserPrinterDevice
from app.services.printer_connection_observation_service import observed_endpoint

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


def _endpoint_fingerprint(value: str, provider: str | None) -> str:
    canonical = f"{str(provider or 'generic').lower()}|{value}"
    return blind_index(canonical, context="printer-endpoint-v1")


def _binding_storage_key(
    *,
    source_instance_id: str | None,
    connection_ref: str | None,
    endpoint_fingerprint: str | None,
) -> str:
    if connection_ref:
        stable = f"{source_instance_id or ''}|{connection_ref}"
        return "ref:" + hashlib.sha256(stable.encode("utf-8")).hexdigest()
    return "endpoint:" + str(endpoint_fingerprint or "unknown")


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
        link = UserPrinterProfileLink(
            user_id=user_id,
            physical_printer_id=physical_printer_id,
            printer_profile_id=profile_id,
        )
        db.add(link)
        await db.flush()


def display_endpoint(binding: PrinterConnectionBinding) -> str | None:
    """A human-readable endpoint label (host[:port]) — never identity or secrets."""
    if binding.endpoint_ciphertext:
        endpoint = normalize_endpoint(
            decrypt_field(binding.endpoint_ciphertext),
            binding.provider,
        )
        if endpoint["host"]:
            return (
                f'{endpoint["host"]}:{endpoint["port"]}'
                if endpoint["port"]
                else endpoint["host"]
            )
    if binding.host:
        return f"{binding.host}:{binding.port}" if binding.port else binding.host
    return binding.print_host


async def _unbound_catalog_printer(
    db: AsyncSession,
    *,
    user_id: int,
    printer_id: int | None,
) -> int | None:
    """Return one unbound physical machine of the model, never guess among two."""
    if printer_id is None:
        return None
    candidates = list(
        (
            await db.execute(
                select(UserPrinterDevice.id)
                .outerjoin(
                    PrinterConnectionBinding,
                    PrinterConnectionBinding.physical_printer_id == UserPrinterDevice.id,
                )
                .where(
                    UserPrinterDevice.user_id == user_id,
                    UserPrinterDevice.printer_id == printer_id,
                    PrinterConnectionBinding.id.is_(None),
                )
                .order_by(UserPrinterDevice.id)
                .limit(2)
            )
        ).scalars()
    )
    return candidates[0] if len(candidates) == 1 else None


async def _unique_legacy_binding_for_catalog(
    db: AsyncSession,
    *,
    user_id: int,
    printer_id: int | None,
) -> int | None:
    """Upgrade one pre-connection_ref binding, but never choose among two."""
    if printer_id is None:
        return None
    bindings = list(
        (
            await db.execute(
                select(PrinterConnectionBinding)
                .join(
                    UserPrinterDevice,
                    UserPrinterDevice.id
                    == PrinterConnectionBinding.physical_printer_id,
                )
                .where(
                    PrinterConnectionBinding.user_id == user_id,
                    PrinterConnectionBinding.connection_ref.is_(None),
                    UserPrinterDevice.printer_id == printer_id,
                )
                .order_by(PrinterConnectionBinding.id)
                .limit(2)
            )
        )
        .scalars()
    )
    return bindings[0].physical_printer_id if len(bindings) == 1 else None


async def _unique_legacy_binding_for_profile(
    db: AsyncSession,
    *,
    user_id: int,
    profile_id: int | None,
) -> int | None:
    """Upgrade one profile-linked legacy binding, never choose between machines."""
    if profile_id is None:
        return None
    physical_ids = list(
        (
            await db.execute(
                select(PrinterConnectionBinding.physical_printer_id)
                .join(
                    UserPrinterProfileLink,
                    UserPrinterProfileLink.physical_printer_id
                    == PrinterConnectionBinding.physical_printer_id,
                )
                .where(
                    PrinterConnectionBinding.user_id == user_id,
                    PrinterConnectionBinding.connection_ref.is_(None),
                    UserPrinterProfileLink.user_id == user_id,
                    UserPrinterProfileLink.printer_profile_id == profile_id,
                )
                .distinct()
                .order_by(PrinterConnectionBinding.physical_printer_id)
                .limit(2)
            )
        ).scalars()
    )
    return physical_ids[0] if len(physical_ids) == 1 else None


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


async def reconcile_user_printers(
    db: AsyncSession,
    user_id: int,
    *,
    source_instance_id: str | None = None,
) -> int:
    """Upsert physical printers + bindings from the user's observations.

    Idempotent: a known endpoint updates its binding and an unclaimed endpoint
    creates a printer. A profile may be shared by several physical machines, so
    it is never used to merge endpoints. Returns the number newly auto-created."""
    observations_query = select(OrcaPrinterConnectionObservation).where(
        OrcaPrinterConnectionObservation.owner_user_id == user_id
    )
    if source_instance_id:
        observations_query = observations_query.where(
            OrcaPrinterConnectionObservation.source_instance_id == source_instance_id
        )
    observations = list(
        (
            await db.execute(
                observations_query.order_by(
                    OrcaPrinterConnectionObservation.last_seen_at.asc(),
                    OrcaPrinterConnectionObservation.id.asc(),
                )
            )
        ).scalars().all()
    )
    observations = [
        observation
        for observation in observations
        if (observation.sanitized_payload or {}).get("present_in_snapshot") is not False
    ]

    created = 0
    for obs in observations:
        raw_endpoint = observed_endpoint(obs)
        has_connection_identity = bool(obs.connection_ref)
        if not raw_endpoint and not has_connection_identity:
            # A stock Bambu/other cloud-managed preset has no network endpoint.
            # It may still identify the exact configuration of an already known
            # physical printer. A current preset works on older plugin payloads;
            # a visible system preset means the model is enabled in Orca's setup.
            # Attach only when one physical printer of that catalog model exists;
            # multiple identical machines require an explicit user choice.
            payload = obs.sanitized_payload or {}
            if (
                obs.matched_printer_profile_id is not None
                and (
                    bool(payload.get("is_current"))
                    or (
                        bool(payload.get("is_system"))
                        and bool(payload.get("is_visible"))
                    )
                )
            ):
                profile = await db.get(PrinterProfile, obs.matched_printer_profile_id)
                if profile is not None and profile.printer_id is not None:
                    printer_ids = list(
                        (
                            await db.execute(
                                select(UserPrinterDevice.id)
                                .where(
                                    UserPrinterDevice.user_id == user_id,
                                    UserPrinterDevice.printer_id == profile.printer_id,
                                )
                                .order_by(UserPrinterDevice.id)
                                .limit(2)
                            )
                        ).scalars()
                    )
                    if not printer_ids:
                        printer = UserPrinterDevice(
                            user_id=user_id,
                            printer_id=profile.printer_id,
                            name=obs.printer_model or obs.preset_name or "Printer",
                            device_fingerprint=None,
                            supports_hh=False,
                        )
                        db.add(printer)
                        await db.flush()
                        printer_ids = [printer.id]
                        created += 1
                    if len(printer_ids) == 1:
                        await _ensure_profile_link(
                            db,
                            user_id,
                            printer_ids[0],
                            obs.matched_printer_profile_id,
                        )
            continue
        endpoint = normalize_endpoint(raw_endpoint, obs.host_type) if raw_endpoint else None
        endpoint_fingerprint = (
            _endpoint_fingerprint(raw_endpoint, obs.host_type) if raw_endpoint else None
        )

        binding = None
        endpoint_peer_physical_id = None
        if obs.connection_ref:
            binding = (
                await db.execute(
                    select(PrinterConnectionBinding).where(
                        PrinterConnectionBinding.user_id == user_id,
                        PrinterConnectionBinding.source_instance_id == obs.source_instance_id,
                        PrinterConnectionBinding.connection_ref == obs.connection_ref,
                    )
                )
            ).scalar_one_or_none()
            if binding is None and endpoint_fingerprint:
                endpoint_peer_ids = list(
                    (
                        await db.execute(
                            select(PrinterConnectionBinding.physical_printer_id).where(
                                PrinterConnectionBinding.user_id == user_id,
                                PrinterConnectionBinding.endpoint_fingerprint
                                == endpoint_fingerprint,
                            )
                        )
                    ).scalars()
                )
                if len(set(endpoint_peer_ids)) == 1:
                    endpoint_peer_physical_id = endpoint_peer_ids[0]
        elif endpoint_fingerprint:
            binding = (
                await db.execute(
                    select(PrinterConnectionBinding).where(
                        PrinterConnectionBinding.user_id == user_id,
                        (
                            PrinterConnectionBinding.endpoint_fingerprint
                            == endpoint_fingerprint
                        )
                        | (
                            PrinterConnectionBinding.normalized_endpoint
                            == endpoint["normalized"]
                        ),
                    )
                )
            ).scalar_one_or_none()

        if binding is None:
            matched_profile = (
                await db.get(PrinterProfile, obs.matched_printer_profile_id)
                if obs.matched_printer_profile_id is not None
                else None
            )
            if obs.connection_ref and endpoint_peer_physical_id is None:
                endpoint_peer_physical_id = await _unique_legacy_binding_for_profile(
                    db,
                    user_id=user_id,
                    profile_id=obs.matched_printer_profile_id,
                )
                if endpoint_peer_physical_id is None:
                    endpoint_peer_physical_id = await _unique_legacy_binding_for_catalog(
                        db,
                        user_id=user_id,
                        printer_id=matched_profile.printer_id if matched_profile else None,
                    )
        if binding is None:
            physical_printer_id = endpoint_peer_physical_id
            if physical_printer_id is None:
                physical_printer_id = await _unbound_catalog_printer(
                    db,
                    user_id=user_id,
                    printer_id=matched_profile.printer_id if matched_profile else None,
                )
            if physical_printer_id is None:
                printer = UserPrinterDevice(
                    user_id=user_id,
                    name=(
                        obs.printer_model
                        or obs.preset_name
                        or (endpoint["host"] if endpoint else None)
                        or "Printer"
                    ),
                    printer_id=matched_profile.printer_id if matched_profile else None,
                    device_fingerprint=None,
                    supports_hh=False,
                )
                db.add(printer)
                await db.flush()
                physical_printer_id = printer.id
                created += 1
            binding = PrinterConnectionBinding(
                user_id=user_id,
                physical_printer_id=physical_printer_id,
                source_instance_id=obs.source_instance_id,
                connection_ref=obs.connection_ref,
                normalized_endpoint=_binding_storage_key(
                    source_instance_id=obs.source_instance_id,
                    connection_ref=obs.connection_ref,
                    endpoint_fingerprint=endpoint_fingerprint,
                ),
                provider=(endpoint["provider"] if endpoint else obs.host_type),
                scheme=None,
                host=None,
                port=None,
                path=None,
                print_host=None,
                endpoint_ciphertext=(encrypt_field(raw_endpoint) if raw_endpoint else None),
                endpoint_fingerprint=endpoint_fingerprint,
            )
            db.add(binding)
            await db.flush()
        else:
            binding.last_seen_at = datetime.now(timezone.utc)
            binding.source_instance_id = obs.source_instance_id
            binding.connection_ref = obs.connection_ref
            binding.normalized_endpoint = _binding_storage_key(
                source_instance_id=obs.source_instance_id,
                connection_ref=obs.connection_ref,
                endpoint_fingerprint=endpoint_fingerprint,
            )
            binding.provider = endpoint["provider"] if endpoint else obs.host_type
            binding.scheme = None
            binding.host = None
            binding.port = None
            binding.path = None
            binding.print_host = None
            binding.endpoint_ciphertext = (
                encrypt_field(raw_endpoint) if raw_endpoint else None
            )
            binding.endpoint_fingerprint = endpoint_fingerprint

            # A device created from this preset used to inherit the full preset
            # display name. Once the model is known, replace only that generated
            # name; never overwrite a name the person chose themselves.
            physical_printer = await db.get(
                UserPrinterDevice, binding.physical_printer_id
            )
            if (
                physical_printer is not None
                and obs.printer_model
                and physical_printer.name == obs.preset_name
            ):
                physical_printer.name = obs.printer_model

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
        if not model:
            continue
        payload = obs.sanitized_payload or {}
        is_current = bool(payload.get("is_current"))
        is_system = bool(payload.get("is_system"))
        is_visible = bool(payload.get("is_visible"))
        if is_system and not (is_current or is_visible):
            continue
        if model in candidates and (not is_current or candidates[model]["_is_current"]):
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
            # A model installs several stock nozzle variants. Only the profile
            # selected right now is an intentional configuration choice; using
            # an arbitrary non-current variant would silently attach the wrong
            # nozzle when the physical printer card is created.
            "printer_profile_id": (
                obs.matched_printer_profile_id if is_current else None
            ),
            "catalog_name": printer.name if printer else None,
            "last_seen_at": obs.last_seen_at,
            "_is_current": is_current,
        }
    result = []
    for candidate in candidates.values():
        candidate.pop("_is_current", None)
        result.append(candidate)
    return sorted(result, key=lambda item: item["model"])


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

    linked_printer_ids = list(
        (
            await db.execute(
            select(UserPrinterProfileLink.physical_printer_id)
            .where(
                UserPrinterProfileLink.user_id == user_id,
                UserPrinterProfileLink.printer_profile_id
                == observation.matched_printer_profile_id,
            )
                .distinct()
                .limit(2)
            )
        ).scalars()
    )
    physical_printer_id = linked_printer_ids[0] if len(linked_printer_ids) == 1 else None

    return {
        "printer_profile_id": observation.matched_printer_profile_id,
        "physical_printer_id": physical_printer_id,
        "preset_name": observation.preset_name,
        "last_seen_at": observation.last_seen_at,
    }
