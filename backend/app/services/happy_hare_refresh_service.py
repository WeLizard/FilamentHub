"""Desired Happy Hare map using the native compatibility projection."""

import hashlib
import json

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import device_inventory_digest
from app.models.material_system import MaterialSystem, PhysicalPrinterConnector
from app.models.spool_compat_resource import SpoolCompatResource
from app.models.user_printer_device import UserPrinterDevice
from app.schemas.printer_bridge import HappyHareRefreshGate, HappyHareRefreshTarget


async def build_happy_hare_refresh_target(
    db: AsyncSession, connector: PhysicalPrinterConnector, system: MaterialSystem
) -> HappyHareRefreshTarget | None:
    # The compatibility catalog also uses this projection entry point. Keep one
    # implementation for imported metadata, bound presets and registered tags.
    from app.api.v1.endpoints.spool_compat import _build_location_map, project_gate_material
    from app.api.v1.endpoints.spool_compat_catalog import prepare_projection
    from app.services.spool_compat_resource_service import get_spool_material_context
    from app.services.spool_tag_service import list_spool_tags

    if (connector.provider != "happy_hare" or connector.transport != "edge_agent"
            or not system.active):
        return None
    printer = await db.scalar(select(UserPrinterDevice).where(
        UserPrinterDevice.id == connector.physical_printer_id,
        UserPrinterDevice.user_id == connector.user_id,
    ))
    if printer is None or not printer.printer_hostname or not printer.api_key:
        return None
    inventory_digest = device_inventory_digest(printer.api_key)
    if inventory_digest is None:
        return None
    spools = {
        slot.assignment.spool.id: slot.assignment.spool
        for slot in system.slots
        if slot.active and slot.assignment and slot.assignment.spool
    }
    _location_map, gate_meta = await _build_location_map(
        db, connector.user_id, spool_ids=list(spools),
    )
    known_refs = {ref.id: ref for ref in (await db.scalars(select(SpoolCompatResource).where(
        SpoolCompatResource.id.in_([spool.compat_filament_ref_id for spool in spools.values()
                                   if spool.compat_filament_ref_id is not None]),
        SpoolCompatResource.kind == "filament",
        or_(SpoolCompatResource.user_id.is_(None),
            SpoolCompatResource.user_id == connector.user_id),
    ))).all()}
    refs = {}
    for spool in spools.values():
        if spool.compat_filament_ref_id is not None:
            refs[spool.id] = known_refs.get(spool.compat_filament_ref_id)
        else:
            # Compatibility migration for a newly created native spool only;
            # persisted references are batch-loaded on ordinary polling reads.
            refs[spool.id] = await get_spool_material_context(
                db, user_id=connector.user_id, spool=spool,
            )
    if any(ref is None for ref in refs.values()):
        return None
    await prepare_projection(db, user_id=connector.user_id, refs=list(refs.values()))
    tags = await list_spool_tags(db, user_id=connector.user_id, spool_ids=list(spools))
    gates = []
    for slot in sorted(system.slots, key=lambda item: item.provider_index):
        if not slot.active or slot.kind == "bypass" or slot.provider_index > 255:
            continue
        spool = slot.assignment.spool if slot.assignment else None
        if spool is None:
            gates.append(HappyHareRefreshGate(
                index=slot.provider_index, spool_id=-1, name="", material="", color="",
                vendor="", temperature=0, initial_weight=-1, rfids="",
            ))
            continue
        meta = gate_meta.get(spool.id)
        if meta is None or meta[1:3] != (slot.provider_index, printer.printer_hostname):
            return None  # Native projection and domain binding must agree.
        filament = await project_gate_material(db, spool, refs[spool.id], gate_meta)
        try:
            temperature = int(filament.get("settings_extruder_temp", ""))
        except ValueError:
            temperature = 0  # Happy Hare's _safe_int fallback, before its local clamp.
        gates.append(HappyHareRefreshGate(
            index=slot.provider_index, spool_id=spool.id,
            name=filament.get("name", ""), material=filament.get("material", ""),
            color=filament.get("color_hex", "").strip("#")[:8].lower(),
            vendor=filament.get("vendor", {}).get("name", ""),
            temperature=temperature,
            initial_weight=round(round(spool.initial_weight_g, 3)),
            rfids=",".join(sorted(tag.uid for tag in tags.get(spool.id, []))),
        ))
    if not gates or [gate.index for gate in gates] != list(range(len(gates))):
        return None
    payload = {
        "physical_printer_id": connector.physical_printer_id, "material_system_id": system.id,
        "inventory_key_digest": inventory_digest,
        "printer_hostname": printer.printer_hostname,
        "gates": [gate.model_dump() for gate in gates],
    }
    revision = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False).encode()).hexdigest()
    return HappyHareRefreshTarget(revision=revision, **payload)
