"""External filament database of the Spoolman-compatible API.

Spoolman serves a copy of SpoolmanDB under ``/external``, and clients use it to
recognise what a tag or a person describes: Happy Hare looks a scanned tag's
brand, material and colour up there before it creates a filament.

FilamentHub serves its own catalog in that shape. Each entry's ``id`` is the
external id of a catalog filament, so a client that finds a match and asks for
``/filament?external_id=<id>`` is given the catalog filament itself. Nothing is
copied into the account and no duplicate appears.
"""

from __future__ import annotations

import json
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.session import get_db
from app.models.filament import Filament
from app.services.preset_enrichment_service import _load_material_defaults

from .spool_compat_catalog import catalog_external_id

router = APIRouter(tags=["spool_compat"])

# The catalog changes rarely and the list is the same for every account, so one
# rendering per worker is reused for a while instead of being rebuilt per client.
CACHE_SECONDS = 600
_cache: dict[str, tuple[float, bytes]] = {}


def _midpoint(low: int | None, high: int | None) -> int | None:
    """One recommended value out of a manufacturer's range."""
    if low is not None and high is not None:
        return round((low + high) / 2)
    return low if low is not None else high


def _hex(value: str | None) -> str | None:
    text = (value or "").strip().lstrip("#").lower()
    return text if len(text) in {6, 8} and all(char in "0123456789abcdef" for char in text) else None


def external_filament(filament: Filament) -> dict | None:
    """Project one catalog filament, or None when a client could not match it."""
    brand = filament.brand
    if brand is None or not filament.material_type:
        return None
    entry: dict = {
        "id": catalog_external_id(filament.id),
        "manufacturer": brand.name,
        "name": filament.name,
        "material": filament.material_type,
        "diameter": filament.diameter,
    }
    # Only what the catalog actually knows: a guessed weight or density would be
    # copied into someone's inventory as if a manufacturer had stated it.
    optional = {
        "density": filament.density if filament.density and filament.density > 0 else None,
        "weight": filament.spool_weight if filament.spool_weight and filament.spool_weight > 0 else None,
        "spool_weight": filament.empty_spool_weight_g,
        "color_hex": _hex(filament.color_hex),
        "extruder_temp": _midpoint(
            filament.recommended_nozzle_temp_min, filament.recommended_nozzle_temp_max
        ),
        # Beyond Spoolman's shape: the top of the range, for clients that keep one.
        "extruder_temp_max": filament.recommended_nozzle_temp_max,
        "bed_temp": _midpoint(filament.recommended_bed_temp_min, filament.recommended_bed_temp_max),
    }
    entry.update({key: value for key, value in optional.items() if value is not None})
    return entry


def external_materials() -> list[dict]:
    materials = []
    for name, defaults in sorted(_load_material_defaults().items()):
        if not isinstance(defaults, dict) or defaults.get("filament_density") is None:
            continue
        materials.append({
            "material": name,
            "density": defaults["filament_density"],
            **{
                key: int(defaults[key])
                for key in ("extruder_temp", "bed_temp")
                if defaults.get(key) is not None
            },
        })
    return materials


async def _filaments_json(db: AsyncSession) -> bytes:
    cached = _cache.get("filament")
    if cached is not None and cached[0] > time.monotonic():
        return cached[1]
    filaments = (
        await db.scalars(
            select(Filament)
            .options(joinedload(Filament.brand))
            .where(Filament.active.is_(True))
            .order_by(Filament.id)
        )
    ).all()
    entries = [entry for entry in map(external_filament, filaments) if entry is not None]
    body = json.dumps(entries, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    _cache["filament"] = (time.monotonic() + CACHE_SECONDS, body)
    return body


async def _serve(db: AsyncSession, api_key: str | None, what: str) -> Response:
    from .spool_compat import _err, _resolve_user_and_device

    user, device = await _resolve_user_and_device(db, api_key)
    if user is None or device is None:
        return _err(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key.")
    body = (
        await _filaments_json(db)
        if what == "filament"
        else json.dumps(external_materials(), separators=(",", ":")).encode("utf-8")
    )
    return Response(content=body, media_type="application/json")


def _register(what: str) -> None:
    async def with_header_key(
        db: Annotated[AsyncSession, Depends(get_db)],
        query_api_key: Annotated[str | None, Query(alias="api_key")] = None,
        header_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> Response:
        return await _serve(db, query_api_key or header_api_key, what)

    async def with_path_key(api_key: str, db: Annotated[AsyncSession, Depends(get_db)]) -> Response:
        return await _serve(db, api_key, what)

    for version in ("v1", "api/v1"):
        router.add_api_route(f"/{version}/external/{what}", with_header_key, methods=["GET"],
                             name=f"external_{what}_{version}_header")
    for version in ("v1", "api/v1"):
        router.add_api_route(f"/{{api_key}}/{version}/external/{what}", with_path_key,
                             methods=["GET"], name=f"external_{what}_{version}_path")


_register("filament")
_register("material")
