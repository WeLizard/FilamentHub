"""Collect a complete, stable snapshot of the existing public catalog."""

from __future__ import annotations

from typing import Any

import httpx

PAGE_SIZE = 100
MAX_ITEMS = 5_000


class CatalogSnapshotError(RuntimeError):
    """The catalog changed or returned an incomplete/unusable page set."""


async def _collect_pages(
    client: httpx.AsyncClient,
    path: str,
    *,
    params: dict[str, Any],
    label: str,
    project: Any,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    expected_total: int | None = None
    page = 1

    while True:
        response = await client.get(
            path,
            params={**params, "page": page, "size": PAGE_SIZE},
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise CatalogSnapshotError(f"{label} page {page} was not valid JSON") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
            raise CatalogSnapshotError(f"{label} page {page} had an invalid response shape")
        total = payload.get("total")
        if isinstance(total, bool) or not isinstance(total, int) or total < 0 or total > MAX_ITEMS:
            raise CatalogSnapshotError(f"{label} total was invalid or exceeded {MAX_ITEMS}")
        if expected_total is None:
            expected_total = total
        elif total != expected_total:
            raise CatalogSnapshotError(f"{label} total changed during pagination")
        if payload.get("page") != page or payload.get("size") != PAGE_SIZE:
            raise CatalogSnapshotError(f"{label} page metadata did not match the request")

        page_items = payload["items"]
        if len(page_items) > PAGE_SIZE:
            raise CatalogSnapshotError(f"{label} page {page} exceeded the requested size")
        for item in page_items:
            if not isinstance(item, dict):
                raise CatalogSnapshotError(f"{label} page {page} contained an invalid item")
            item_id = item.get("id")
            if isinstance(item_id, bool) or not isinstance(item_id, int) or item_id <= 0:
                raise CatalogSnapshotError(f"{label} page {page} contained an invalid id")
            if item_id in seen_ids:
                raise CatalogSnapshotError(f"{label} pagination contained duplicate id {item_id}")
            seen_ids.add(item_id)
            items.append(project(item))

        if len(items) > expected_total:
            raise CatalogSnapshotError(f"{label} returned more rows than its declared total")
        if len(items) == expected_total:
            return items
        if not page_items or page * PAGE_SIZE >= MAX_ITEMS:
            raise CatalogSnapshotError(f"{label} pagination ended before its declared total")
        page += 1


def _brand(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "name": item.get("name"),
        "slug": item.get("slug"),
        "website": item.get("website"),
    }


def _filament(item: dict[str, Any]) -> dict[str, Any]:
    # Deliberately omit prices and delivery/packaging details. The snapshot is
    # for catalog identity and matching, not a market or spool import.
    return {
        "id": item["id"],
        "brand_id": item.get("brand_id"),
        "name": item.get("name"),
        "slug": item.get("slug"),
        "material_type": item.get("material_type"),
        "additives": item.get("additives", []),
        "property_claims": item.get("property_claims", []),
        "color_name": item.get("color_name"),
        "color_hex": item.get("color_hex"),
        "diameter": item.get("diameter"),
        "line_id": item.get("line_id"),
        "line_name": item.get("line_name"),
        "availability": item.get("availability"),
        "active": item.get("active"),
    }


async def collect_catalog_snapshot(
    client: httpx.AsyncClient,
    brand_name: str,
    brand_id: int | None = None,
) -> dict[str, Any]:
    """Fetch all brands and, when uniquely identified, all their materials.

    Callers pass an ``AsyncClient`` rooted at the application origin. An absent
    or ambiguous name leaves ``selected_brand`` unset, allowing a semantic
    caller to inspect all candidates before suggesting a new manufacturer.
    """
    brands = await _collect_pages(
        client,
        "/api/v1/brands/",
        params={"active_only": "false"},
        label="brands",
        project=_brand,
    )
    exact_name_matches = [
        brand
        for brand in brands
        if isinstance(brand.get("name"), str)
        and brand["name"].casefold() == brand_name.strip().casefold()
    ]

    selected: dict[str, Any] | None = None
    match_reason = "no_exact_match"
    if brand_id is not None:
        selected = next((brand for brand in brands if brand["id"] == brand_id), None)
        match_reason = "explicit_id" if selected else "id_not_found"
    elif len(exact_name_matches) == 1:
        selected = exact_name_matches[0]
        match_reason = "exact_casefold_name"
    elif len(exact_name_matches) > 1:
        match_reason = "ambiguous_exact_name"

    filaments: list[dict[str, Any]] = []
    if selected is not None:
        filaments = await _collect_pages(
            client,
            "/api/v1/filaments/",
            params={"active_only": "false", "brand_id": selected["id"]},
            label=f"filaments for brand {selected['id']}",
            project=_filament,
        )

    return {
        "requested_brand": {"id": brand_id, "name": brand_name},
        "brand_match": {
            "reason": match_reason,
            "exact_name_candidate_ids": [brand["id"] for brand in exact_name_matches],
        },
        "brands": brands,
        "brand_candidates": brands,
        "selected_brand": selected,
        "filaments": filaments,
    }
