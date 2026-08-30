"""Resolve actual local connections without treating configurations as printers."""

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ERR_DEVICE_NOT_FOUND,
    ERR_PRINTER_CONNECTION_NOT_FOUND,
    ERR_PRINTER_IDENTITY_CONFLICT,
    raise_error,
)
from app.core.field_encryption import blind_index, decrypt_field, encrypt_field
from app.models.orca_printer_connection_observation import OrcaPrinterConnectionObservation
from app.models.physical_printer_profile import UserPrinterProfileLink
from app.models.printer_connection_binding import PrinterConnectionBinding
from app.models.printer_profile import PrinterProfile
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.printer_connection_observation import PrinterIdentityEvidence
from app.services.orca_import_guard import hold_account_import_lock
from app.services.printer_connection_observation_service import observed_endpoint
from app.services.printer_identity_service import (
    discovery_key,
    identity_printer,
    normalize_endpoint,
    remember_identity,
)
from app.services.printer_identity_service import (
    endpoint_token as make_endpoint_token,
)


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
    stable = f"{source_instance_id or ''}|{endpoint_fingerprint or 'unknown'}"
    return "endpoint:" + hashlib.sha256(stable.encode("utf-8")).hexdigest()


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
                f'{endpoint["host"]}:{endpoint["port"]}' if endpoint["port"] else endpoint["host"]
            )
    if binding.host:
        return f"{binding.host}:{binding.port}" if binding.port else binding.host
    return binding.print_host


async def list_user_bindings(db: AsyncSession, user_id: int) -> list[PrinterConnectionBinding]:
    return list(
        (
            await db.execute(
                select(PrinterConnectionBinding)
                .where(PrinterConnectionBinding.user_id == user_id)
                .order_by(PrinterConnectionBinding.physical_printer_id)
            )
        )
        .scalars()
        .all()
    )


async def binding_preset_names(db: AsyncSession, user_id: int) -> dict[tuple[str | None, str], str]:
    """Latest safe Orca preset label for each stable local connection."""
    rows = (
        await db.execute(
            select(
                OrcaPrinterConnectionObservation.source_instance_id,
                OrcaPrinterConnectionObservation.connection_ref,
                OrcaPrinterConnectionObservation.preset_name,
            )
            .where(
                OrcaPrinterConnectionObservation.owner_user_id == user_id,
                OrcaPrinterConnectionObservation.connection_ref.is_not(None),
                OrcaPrinterConnectionObservation.preset_name.is_not(None),
            )
            .order_by(
                OrcaPrinterConnectionObservation.last_seen_at.desc(),
                OrcaPrinterConnectionObservation.id.desc(),
            )
        )
    ).all()
    result: dict[tuple[str | None, str], str] = {}
    for source_instance_id, connection_ref, preset_name in rows:
        if connection_ref and preset_name:
            result.setdefault((source_instance_id, connection_ref), preset_name)
    return result


async def assign_user_binding(
    db: AsyncSession,
    *,
    user_id: int,
    binding_id: int,
    physical_printer_id: int,
) -> None:
    """Explicitly assign one observed connection to one owned physical printer."""
    await hold_account_import_lock(db, user_id)
    binding = (
        await db.execute(
            select(PrinterConnectionBinding)
            .where(
                PrinterConnectionBinding.id == binding_id,
                PrinterConnectionBinding.user_id == user_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if binding is None:
        raise_error(404, ERR_PRINTER_CONNECTION_NOT_FOUND)

    printer_id = await db.scalar(
        select(UserPrinterDevice.id).where(
            UserPrinterDevice.id == physical_printer_id,
            UserPrinterDevice.user_id == user_id,
        )
    )
    if printer_id is None:
        raise_error(404, ERR_DEVICE_NOT_FOUND)

    if (
        binding.identity_kind
        and binding.identity_token
        and not await remember_identity(
            db,
            user_id,
            physical_printer_id,
            PrinterIdentityEvidence(kind=binding.identity_kind, token=binding.identity_token),
        )
    ):
        raise_error(409, ERR_PRINTER_IDENTITY_CONFLICT)
    binding.physical_printer_id = physical_printer_id
    binding.assignment_confirmed = True
    binding.status = "bound"
    await db.commit()


def _binding_endpoint(binding: PrinterConnectionBinding) -> str | None:
    if binding.endpoint_ciphertext:
        return decrypt_field(binding.endpoint_ciphertext)
    if binding.print_host:
        return binding.print_host
    if binding.host:
        port = f":{binding.port}" if binding.port else ""
        return f"{binding.scheme or 'http'}://{binding.host}{port}{binding.path or ''}"
    return None


def _resolution(observation, status: str, candidates=()) -> None:
    payload = dict(observation.sanitized_payload or {})
    payload["resolution_status"] = status
    payload["candidate_printer_ids"] = sorted(set(candidates))
    observation.sanitized_payload = payload


async def reconcile_user_printers(
    db: AsyncSession,
    user_id: int,
    *,
    source_instance_id: str | None = None,
) -> int:
    """Same local connection/device -> same printer; a preset alone proves neither.

    An endpoint is scoped to its installation: identical private addresses in
    two different LANs are not device identity. Cross-installation continuity
    uses device evidence or an explicit saved choice.
    """
    await hold_account_import_lock(db, user_id)
    query = select(OrcaPrinterConnectionObservation).where(
        OrcaPrinterConnectionObservation.owner_user_id == user_id
    )
    if source_instance_id:
        query = query.where(
            OrcaPrinterConnectionObservation.source_instance_id == source_instance_id
        )
    observations = [
        row
        for row in (
            await db.execute(
                query.order_by(
                    OrcaPrinterConnectionObservation.last_seen_at,
                    OrcaPrinterConnectionObservation.id,
                )
            )
        ).scalars()
        if (row.sanitized_payload or {}).get("present_in_snapshot") is not False
    ]
    key = await discovery_key(db, user_id)
    bindings = await list_user_bindings(db, user_id)
    for binding in bindings:
        raw = _binding_endpoint(binding)
        if raw:
            binding.endpoint_token = make_endpoint_token(key, raw, binding.provider)
        if (source_instance_id and binding.source_instance_id == source_instance_id
                and binding.source != "local_setup"):
            present = any(
                o.connection_ref == binding.connection_ref
                if binding.connection_ref
                else bool(
                    observed_endpoint(o)
                    and make_endpoint_token(key, observed_endpoint(o), o.host_type)
                    == binding.endpoint_token
                )
                for o in observations
            )
            if not present:
                binding.status = "disconnected"

    profile_ids = {
        o.matched_printer_profile_id
        for o in observations
        if o.matched_printer_profile_id is not None
    }
    profiles = (
        {
            p.id: p
            for p in (
                await db.execute(select(PrinterProfile).where(PrinterProfile.id.in_(profile_ids)))
            ).scalars()
        }
        if profile_ids
        else {}
    )
    created = 0
    for obs in observations:
        payload = obs.sanitized_payload or {}
        if payload.get("present_in_snapshot") is False:
            continue
        raw_endpoint = observed_endpoint(obs)
        token = make_endpoint_token(key, raw_endpoint, obs.host_type) or payload.get(
            "endpoint_token"
        )
        evidence = (
            PrinterIdentityEvidence.model_validate(payload["device_identity"])
            if payload.get("device_identity")
            else None
        )
        binding = next(
            (
                b
                for b in bindings
                if obs.connection_ref
                and b.source_instance_id == obs.source_instance_id
                and b.connection_ref == obs.connection_ref
            ),
            None,
        )
        if not token and not evidence:
            # Old hidden-address payloads do not prove that a user preset has a
            # connection. Preserve known links, but never manufacture new ones.
            if binding is not None and payload.get("has_connection") is False:
                binding.status = "disconnected"
            if (
                binding is not None
                and binding.status == "bound"
                and payload.get("has_connection") is not False
            ):
                _resolution(obs, "bound", [binding.physical_printer_id])
            elif binding is not None and binding.status == "conflict":
                _resolution(obs, "pending", [binding.physical_printer_id])
            else:
                _resolution(obs, "configuration")
            continue

        peers = [b for b in bindings if token and b.endpoint_token == token]
        local_ids = {
            b.physical_printer_id for b in peers if b.source_instance_id == obs.source_instance_id
        }
        all_ids = {b.physical_printer_id for b in peers}
        confirmed_local = {
            b.physical_printer_id
            for b in peers
            if b.source_instance_id == obs.source_instance_id and b.assignment_confirmed
        }
        identified = await identity_printer(db, user_id, evidence) if evidence else None
        identity_changed = bool(
            binding
            and evidence
            and binding.identity_token
            and (binding.identity_kind, binding.identity_token) != (evidence.kind, evidence.token)
        )
        candidates = set(local_ids)
        if binding:
            candidates.add(binding.physical_printer_id)
        if identified is not None:
            candidates.add(identified)
        # Recovering an installation/ref must not silently steal another
        # machine's material system. Keep the evidence visible for resolution.
        if not (binding and binding.assignment_confirmed) and len(confirmed_local) != 1:
            candidates.update(all_ids)
        conflict = identity_changed or len(candidates) > 1
        cross_source_unknown = (
            binding is None and identified is None and not local_ids and bool(all_ids)
        )
        if conflict or cross_source_unknown:
            if binding:
                binding.status = "conflict"
            _resolution(obs, "pending", candidates)
            continue
        physical_id = (
            binding.physical_printer_id
            if binding
            else (identified if identified is not None else next(iter(local_ids), None))
        )
        if physical_id is None:
            profile = profiles.get(obs.matched_printer_profile_id)
            endpoint = normalize_endpoint(raw_endpoint, obs.host_type)
            printer = UserPrinterDevice(
                user_id=user_id,
                name=obs.preset_name or obs.printer_model or endpoint["host"] or "Printer",
                printer_id=profile.printer_id if profile else None,
                device_fingerprint=None,
                supports_hh=False,
            )
            db.add(printer)
            await db.flush()
            physical_id = printer.id
            created += 1
        if binding is None:
            # Old clients without refs still have one row per local endpoint.
            binding = (
                next(
                    (
                        b
                        for b in peers
                        if b.source_instance_id == obs.source_instance_id
                        and b.connection_ref is None
                    ),
                    None,
                )
                if not obs.connection_ref
                else None
            )
        if binding is None:
            binding = PrinterConnectionBinding(
                user_id=user_id,
                physical_printer_id=physical_id,
                source_instance_id=obs.source_instance_id,
                connection_ref=obs.connection_ref,
                normalized_endpoint=_binding_storage_key(
                    source_instance_id=obs.source_instance_id,
                    connection_ref=obs.connection_ref,
                    endpoint_fingerprint=token,
                ),
            )
            db.add(binding)
            bindings.append(binding)
        binding.last_seen_at = datetime.now(timezone.utc)
        binding.provider = normalize_endpoint(raw_endpoint, obs.host_type)["provider"]
        binding.status = "bound"
        binding.endpoint_token = token
        binding.endpoint_ciphertext = encrypt_field(raw_endpoint) if raw_endpoint else None
        binding.endpoint_fingerprint = (
            _endpoint_fingerprint(raw_endpoint, obs.host_type) if raw_endpoint else None
        )
        binding.scheme = binding.host = binding.port = binding.path = binding.print_host = None
        if evidence:
            if not await remember_identity(db, user_id, physical_id, evidence):
                binding.status = "conflict"
                _resolution(obs, "pending", [physical_id])
                continue
            binding.identity_kind, binding.identity_token = evidence.kind, evidence.token
        await db.flush()
        if obs.matched_printer_profile_id:
            await _ensure_profile_link(db, user_id, physical_id, obs.matched_printer_profile_id)
        _resolution(obs, "bound", [physical_id])
    await db.commit()
    return created


def _connection_revision(observation: OrcaPrinterConnectionObservation) -> str:
    payload = observation.sanitized_payload or {}
    return hashlib.sha256(
        json.dumps(
            {
                "observation": observation.observation_hash,
                "device_identity": payload.get("device_identity"),
                "candidates": payload.get("candidate_printer_ids", []),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


async def list_pending_connections(db: AsyncSession, user_id: int) -> list[dict]:
    rows = (
        await db.execute(
            select(OrcaPrinterConnectionObservation)
            .where(
                OrcaPrinterConnectionObservation.owner_user_id == user_id,
                OrcaPrinterConnectionObservation.sanitized_payload["resolution_status"].as_string()
                == "pending",
                OrcaPrinterConnectionObservation.sanitized_payload["present_in_snapshot"]
                .as_boolean()
                .is_(True),
            )
            .order_by(OrcaPrinterConnectionObservation.last_seen_at.desc())
            .limit(256)
        )
    ).scalars()
    result = {}
    for row in rows:
        payload = row.sanitized_payload or {}
        key = (
            row.source_instance_id,
            payload.get("endpoint_token") or row.connection_ref or row.id,
        )
        result.setdefault(
            key,
            {
                "id": row.id,
                "revision": _connection_revision(row),
                "preset_name": row.preset_name,
                "provider": row.host_type,
                "candidate_printer_ids": payload.get("candidate_printer_ids", []),
                "last_seen_at": row.last_seen_at,
            },
        )
    return list(result.values())


async def resolve_pending_connection(
    db: AsyncSession,
    *,
    user_id: int,
    observation_id: int,
    physical_printer_id: int | None,
    create_new: bool,
    revision: str,
) -> None:
    await hold_account_import_lock(db, user_id)
    obs = await db.scalar(
        select(OrcaPrinterConnectionObservation).where(
            OrcaPrinterConnectionObservation.owner_user_id == user_id,
            OrcaPrinterConnectionObservation.id == observation_id,
        )
    )
    if obs is None or (obs.sanitized_payload or {}).get("present_in_snapshot") is False:
        raise_error(404, ERR_PRINTER_CONNECTION_NOT_FOUND)
    payload = obs.sanitized_payload or {}
    if payload.get("resolution_status") == "bound":
        previous_ids = payload.get("candidate_printer_ids", [])
        if payload.get("resolved_revision") == revision and (
            create_new or previous_ids == [physical_printer_id]
        ):
            return
        raise_error(409, ERR_PRINTER_IDENTITY_CONFLICT)
    if payload.get("resolution_status") != "pending":
        raise_error(409, ERR_PRINTER_IDENTITY_CONFLICT)
    if _connection_revision(obs) != revision:
        raise_error(409, ERR_PRINTER_IDENTITY_CONFLICT)
    token = payload.get("endpoint_token") or make_endpoint_token(
        await discovery_key(db, user_id), observed_endpoint(obs), obs.host_type
    )
    if not token or (physical_printer_id is None) == (not create_new):
        raise_error(409, ERR_PRINTER_IDENTITY_CONFLICT)
    if physical_printer_id is not None:
        if not await db.scalar(
            select(UserPrinterDevice.id).where(
                UserPrinterDevice.id == physical_printer_id, UserPrinterDevice.user_id == user_id
            )
        ):
            raise_error(404, ERR_DEVICE_NOT_FOUND)
    else:
        printer = UserPrinterDevice(
            user_id=user_id, name=obs.preset_name or obs.printer_model or "Printer"
        )
        db.add(printer)
        await db.flush()
        physical_printer_id = printer.id
    evidence = (
        PrinterIdentityEvidence.model_validate(payload["device_identity"])
        if payload.get("device_identity")
        else None
    )
    if evidence and not await remember_identity(
        db,
        user_id,
        physical_printer_id,
        evidence,
        allow_replacement=not create_new,
    ):
        raise_error(409, ERR_PRINTER_IDENTITY_CONFLICT)
    binding = (
        await db.scalar(
            select(PrinterConnectionBinding).where(
                PrinterConnectionBinding.user_id == user_id,
                PrinterConnectionBinding.source_instance_id == obs.source_instance_id,
                PrinterConnectionBinding.connection_ref == obs.connection_ref,
            )
        )
        if obs.connection_ref
        else None
    )
    if binding is None:
        binding = PrinterConnectionBinding(
            user_id=user_id,
            source_instance_id=obs.source_instance_id,
            connection_ref=obs.connection_ref,
            physical_printer_id=physical_printer_id,
            normalized_endpoint=_binding_storage_key(
                source_instance_id=obs.source_instance_id,
                connection_ref=obs.connection_ref,
                endpoint_fingerprint=token,
            ),
        )
        db.add(binding)
    binding.physical_printer_id = physical_printer_id
    binding.endpoint_token = token
    binding.assignment_confirmed = True
    binding.status = "bound"
    if evidence:
        binding.identity_kind, binding.identity_token = evidence.kind, evidence.token
    for peer in await list_user_bindings(db, user_id):
        if peer.source_instance_id == obs.source_instance_id and peer.endpoint_token == token:
            peer.physical_printer_id = physical_printer_id
            peer.assignment_confirmed = True
            peer.status = "bound"
            if evidence:
                peer.identity_kind, peer.identity_token = evidence.kind, evidence.token
    obs.sanitized_payload = {**payload, "resolved_revision": revision}
    await db.flush()
    await reconcile_user_printers(db, user_id, source_instance_id=obs.source_instance_id)


async def list_installed_printer_candidates(db: AsyncSession, user_id: int) -> list[dict]:
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
        if payload.get("present_in_snapshot") is False:
            continue
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
            "printer_profile_id": (obs.matched_printer_profile_id if is_current else None),
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
                OrcaPrinterConnectionObservation.sanitized_payload["present_in_snapshot"]
                .as_boolean()
                .is_(True),
            )
            .order_by(
                OrcaPrinterConnectionObservation.last_seen_at.desc(),
                OrcaPrinterConnectionObservation.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if observation is None or observation.matched_printer_profile_id is None:
        return None

    physical_printer_id = await observation_physical_printer(db, user_id, observation)

    return {
        "printer_profile_id": observation.matched_printer_profile_id,
        "physical_printer_id": physical_printer_id,
        "preset_name": observation.preset_name,
        "last_seen_at": observation.last_seen_at,
    }


async def observation_physical_printer(
    db: AsyncSession,
    user_id: int,
    observation: OrcaPrinterConnectionObservation,
) -> int | None:
    payload = observation.sanitized_payload or {}
    if payload.get("present_in_snapshot") is False or payload.get("resolution_status") in {
        "pending",
        "configuration",
    }:
        return None
    query = select(PrinterConnectionBinding.physical_printer_id).where(
        PrinterConnectionBinding.user_id == user_id,
        PrinterConnectionBinding.source_instance_id == observation.source_instance_id,
        PrinterConnectionBinding.status == "bound",
    )
    if observation.connection_ref:
        query = query.where(PrinterConnectionBinding.connection_ref == observation.connection_ref)
    elif observation.endpoint_fingerprint:
        query = query.where(
            PrinterConnectionBinding.endpoint_fingerprint == observation.endpoint_fingerprint
        )
    else:
        return None
    ids = set((await db.execute(query.limit(2))).scalars())
    return next(iter(ids)) if len(ids) == 1 else None
