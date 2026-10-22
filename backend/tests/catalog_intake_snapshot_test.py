from __future__ import annotations

import httpx
import pytest

from app.services.catalog_intake_snapshot import CatalogSnapshotError, collect_catalog_snapshot


def _page(items: list[dict], total: int, page: int, size: int = 100) -> dict:
    return {"items": items, "total": total, "page": page, "size": size, "pages": 1}


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://catalog.example"
    )


@pytest.mark.asyncio
async def test_collects_all_brand_pages_then_all_filament_pages_without_market_or_price_data() -> (
    None
):
    requests: list[httpx.Request] = []
    brands = [
        {"id": index, "name": f"Maker {index}", "slug": f"maker-{index}", "website": None}
        for index in range(1, 102)
    ]
    filaments = [
        {
            "id": 900 + index,
            "brand_id": 101,
            "name": f"PLA Example {index}",
            "slug": f"pla-example-{index}",
            "material_type": "PLA",
            "additives": [{"name": "wood", "percentage": None}],
            "property_claims": [{"claim": "impact resistant"}],
            "color_name": "Red",
            "color_hex": "#aa0000",
            "diameter": 1.75,
            "line_id": 71,
            "line_name": "Example Line",
            "availability": "discontinued",
            "active": False,
            "price_per_kg": 99,
            "spool_weight": 1.0,
            "market_country": "US",
        }
        for index in range(101)
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = int(request.url.params["page"])
        if request.url.path == "/api/v1/brands/":
            batch = brands[(page - 1) * 100 : page * 100]
            return httpx.Response(200, json=_page(batch, len(brands), page))
        assert request.url.path == "/api/v1/filaments/"
        assert request.url.params["brand_id"] == "101"
        batch = filaments[(page - 1) * 100 : page * 100]
        return httpx.Response(200, json=_page(batch, len(filaments), page))

    async with _client(handler) as client:
        snapshot = await collect_catalog_snapshot(client, "MAKER 101")

    assert len(snapshot["brands"]) == 101
    assert snapshot["selected_brand"] == {
        "id": 101,
        "name": "Maker 101",
        "slug": "maker-101",
        "website": None,
    }
    assert snapshot["brand_match"]["reason"] == "exact_casefold_name"
    assert len(snapshot["filaments"]) == 101
    assert snapshot["filaments"][0]["availability"] == "discontinued"
    assert "price_per_kg" not in snapshot["filaments"][0]
    assert "spool_weight" not in snapshot["filaments"][0]
    assert "market_country" not in snapshot["filaments"][0]
    assert all(request.url.params["active_only"] == "false" for request in requests)
    assert all("country" not in request.url.params for request in requests)
    assert sum(request.url.path == "/api/v1/brands/" for request in requests) == 2


@pytest.mark.asyncio
async def test_explicit_brand_id_wins_over_name_and_missing_brand_returns_all_candidates() -> None:
    requests: list[str] = []
    brands = [
        {"id": 1, "name": "Example", "slug": "example", "website": "https://one.example"},
        {"id": 2, "name": "Other", "slug": "other", "website": "https://two.example"},
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/api/v1/brands/":
            return httpx.Response(200, json=_page(brands, 2, 1))
        return httpx.Response(200, json=_page([], 0, 1))

    async with _client(handler) as client:
        explicit = await collect_catalog_snapshot(client, "Example", brand_id=2)
        unrecognized = await collect_catalog_snapshot(client, "Example Industries")

    assert explicit["selected_brand"]["id"] == 2
    assert explicit["brand_match"]["reason"] == "explicit_id"
    assert explicit["filaments"] == []
    assert unrecognized["selected_brand"] is None
    assert unrecognized["brand_match"]["reason"] == "no_exact_match"
    assert unrecognized["brands"] == unrecognized["brand_candidates"]
    assert unrecognized["filaments"] == []
    assert requests.count("/api/v1/filaments/") == 1


@pytest.mark.asyncio
async def test_exact_casefold_duplicate_names_are_not_arbitrarily_selected() -> None:
    brands = [
        {"id": 1, "name": "Maker", "slug": "maker", "website": None},
        {"id": 2, "name": "MAKER", "slug": "maker-2", "website": None},
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/brands/"
        return httpx.Response(200, json=_page(brands, 2, 1))

    async with _client(handler) as client:
        snapshot = await collect_catalog_snapshot(client, "maker")

    assert snapshot["selected_brand"] is None
    assert snapshot["brand_match"] == {
        "reason": "ambiguous_exact_name",
        "exact_name_candidate_ids": [1, 2],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["changed_total", "duplicate_id", "short_page"])
async def test_rejects_inconsistent_catalog_pages(failure: str) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        if failure == "duplicate_id":
            batch = [{"id": 1, "name": f"Maker {page}", "slug": "m", "website": None}]
            return httpx.Response(200, json=_page(batch, 101, page))
        if failure == "short_page":
            if page == 1:
                batch = [
                    {"id": index, "name": f"Maker {index}", "slug": f"m-{index}", "website": None}
                    for index in range(1, 101)
                ]
                return httpx.Response(200, json=_page(batch, 101, page))
            return httpx.Response(
                200,
                json=_page([], 101, page),
            )
        start = (page - 1) * 100
        batch = [
            {"id": index, "name": f"Maker {index}", "slug": f"m-{index}", "website": None}
            for index in range(start + 1, min(start + 101, 102))
        ]
        if failure == "changed_total" and page == 2:
            batch = []
        total = 101 if page == 1 else (100 if failure == "changed_total" else 101)
        return httpx.Response(200, json=_page(batch, total, page))

    async with _client(handler) as client:
        with pytest.raises(CatalogSnapshotError):
            await collect_catalog_snapshot(client, "Does not exist")


@pytest.mark.asyncio
async def test_propagates_http_failures() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with _client(handler) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await collect_catalog_snapshot(client, "Maker")
