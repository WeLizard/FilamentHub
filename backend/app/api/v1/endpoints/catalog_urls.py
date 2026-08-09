"""Read-only resolver used by nginx to normalize public catalogue URLs."""

from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.brand import Brand
from app.models.filament import Filament
from app.services.brand_slug_service import resolve_brand_identifier
from app.services.catalog_url_service import (
    brand_public_path,
    filament_public_path,
    localized_public_path,
    resolve_filament_identifier,
)

router = APIRouter(prefix="/catalog-urls", tags=["catalog-urls"])


def _resolver_response(canonical_path: str | None, requested_path: str) -> Response:
    headers = {"Cache-Control": "no-store"}
    if canonical_path is None:
        return Response(status_code=status.HTTP_403_FORBIDDEN, headers=headers)
    if requested_path == canonical_path:
        return Response(status_code=status.HTTP_204_NO_CONTENT, headers=headers)
    headers["X-Canonical-Path"] = canonical_path
    # nginx auth_request forwards 401/403 from a subrequest. The parent route
    # translates this internal 401 into a permanent redirect.
    return Response(status_code=status.HTTP_401_UNAUTHORIZED, headers=headers)


@router.get("/resolve")
async def resolve_catalog_url(
    x_original_uri: str = Header(..., alias="X-Original-URI"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Return 204 for canonical paths and an internal redirect signal for aliases."""
    requested_path = unquote(urlsplit(x_original_uri).path)
    parts = [part for part in requested_path.split("/") if part]
    locale: str | None = None
    if parts and parts[0].casefold() in {"en", "ru", "zh"}:
        locale = parts.pop(0).casefold()

    canonical_path: str | None = None
    if len(parts) == 2 and parts[0] == "brands":
        brand, _alias = await resolve_brand_identifier(db, parts[1])
        if brand is not None:
            canonical_path = localized_public_path(brand_public_path(brand), locale)
    elif len(parts) == 4 and parts[0] == "brands" and parts[2] == "filaments":
        resolved = await resolve_filament_identifier(
            db,
            brand_identifier=parts[1],
            filament_identifier=parts[3],
        )
        if resolved is not None:
            canonical_path = localized_public_path(
                filament_public_path(resolved.filament, resolved.brand),
                locale,
            )
    elif len(parts) == 2 and parts[0] == "filaments" and parts[1].isdecimal():
        filament = await db.get(Filament, int(parts[1]))
        brand = await db.get(Brand, filament.brand_id) if filament is not None else None
        if filament is not None and brand is not None:
            canonical_path = localized_public_path(
                filament_public_path(filament, brand),
                locale,
            )

    return _resolver_response(canonical_path, requested_path)
