from __future__ import annotations

import json

import httpx
import pytest

from app.services.catalog_source_reader import (
    CatalogSourceReader,
    _canonical_url,
    read_source_site,
)


async def _public_resolver(host: str, port: int) -> set[str]:
    return {"93.184.216.34"}


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://maker.example"
    )


@pytest.mark.asyncio
async def test_reader_collects_page_structure_and_sitemap_without_persisting_bodies() -> None:
    requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200, text="User-agent: *\nDisallow: /private\nCrawl-delay: 0\nSitemap: /map.xml"
            )
        if request.url.path == "/map.xml":
            return httpx.Response(
                200,
                headers={"content-type": "application/xml"},
                text="""<urlset><url><loc>https://maker.example/catalog</loc></url></urlset>""",
            )
        if request.url.path == "/catalog":
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                text="""<html><head><title>Catalog</title><script>secret()</script></head>
                <body><h1>Materials</h1><a href='/archive'>Archive</a>
                <a href='/private'>Hidden</a><a href='https://other.example/item'>External</a>
                <table><tr><th>Type</th><th>Temperature</th></tr><tr><td>PLA</td><td>205</td></tr></table>
                <p>Catalog text</p></body></html>""",
            )
        if request.url.path == "/archive":
            return httpx.Response(
                200, headers={"content-type": "text/html"}, text="<title>Archive</title>"
            )
        return httpx.Response(404)

    async with _client(handler) as client:
        reader = CatalogSourceReader(client=client, resolver=_public_resolver, default_delay=0)
        result = await reader.read("https://maker.example/catalog")

    assert [page.url for page in result.pages] == [
        "https://maker.example/catalog",
        "https://maker.example/archive",
    ]
    first = result.pages[0]
    assert first.title == "Catalog"
    assert first.headings == ("Materials",)
    assert "secret" not in first.text
    assert first.tables[0].rows == (("Type", "Temperature"), ("PLA", "205"))
    assert result.manifest.archive_candidates == ["https://maker.example/archive"]
    assert any(
        entry["reason"] == "robots_disallowed" and entry["url"].endswith("/private")
        for entry in result.manifest.blocked
    )
    assert any(entry["reason"] == "cross_origin" for entry in result.manifest.blocked)
    assert "https://maker.example/archive" in result.manifest.visited
    assert json.loads(json.dumps(result.model_dump()))["pages"][0]["title"] == "Catalog"
    assert all("secret()" not in str(page) for page in result.pages)


@pytest.mark.asyncio
async def test_reader_blocks_unsafe_hosts_redirects_and_non_page_resources() -> None:
    requested: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<a href='/redirect'>go</a><a href='/manual.pdf'>manual</a><a href='http://127.0.0.1/admin'>local</a>",
            )
        if request.url.path == "/redirect":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})
        return httpx.Response(404)

    async with _client(handler) as client:
        result = await CatalogSourceReader(
            client=client, resolver=_public_resolver, default_delay=0
        ).read("https://maker.example/")

    assert all("127.0.0.1" not in url for url in requested)
    assert any(item["reason"] == "non_page_resource" for item in result.manifest.blocked)
    assert any(item["reason"] == "cross_origin_redirect" for item in result.manifest.blocked)
    assert _canonical_url("http://user:pass@maker.example") is None
    assert _canonical_url("http://localhost") is None
    assert _canonical_url("http://192.168.1.2") is None
    assert _canonical_url('https://maker.example/image.png"') is None


@pytest.mark.asyncio
async def test_reader_limits_page_count() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if request.url.path == "/sitemap.xml":
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=f"<title>{request.url.path}</title><a href='/one'>one</a><a href='/two'>two</a>",
        )

    async with _client(handler) as client:
        result = await CatalogSourceReader(
            client=client, resolver=_public_resolver, max_pages=1, default_delay=0
        ).read("https://maker.example/")

    assert len(result.pages) == 1
    assert any(item["reason"] == "page_limit" for item in result.manifest.blocked)
    assert result.manifest.partial is True


@pytest.mark.asyncio
async def test_seed_navigation_precedes_sitemap_only_pages_and_marks_partial_coverage() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nCrawl-delay: 0\nSitemap: /map.xml")
        if request.url.path == "/map.xml":
            return httpx.Response(
                200,
                headers={"content-type": "application/xml"},
                text="""<urlset><url><loc>/catalog-only</loc></url><url><loc>/archive</loc></url></urlset>""",
            )
        if request.url.path == "/":
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                text="<title>Start</title><a href='/line'>Line</a>",
            )
        return httpx.Response(
            200, headers={"content-type": "text/html"}, text=f"<title>{request.url.path}</title>"
        )

    async with _client(handler) as client:
        result = await CatalogSourceReader(
            client=client, resolver=_public_resolver, max_pages=2, default_delay=0
        ).read("https://maker.example/")

    assert [page.url for page in result.pages] == [
        "https://maker.example/",
        "https://maker.example/line",
    ]
    assert result.manifest.partial is True
    assert any(
        item["url"].endswith("/catalog-only") and item["reason"] == "page_limit"
        for item in result.manifest.blocked
    )
    assert "https://maker.example/archive" in result.manifest.discovered


@pytest.mark.asyncio
async def test_multiple_explicit_seeds_keep_a_page_slot_each() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in {"/robots.txt", "/sitemap.xml"}:
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=f"<title>{request.url.path}</title><a href='/unrelated'>Other</a>",
        )

    async with _client(handler) as client:
        result = await read_source_site(
            ["https://maker.example/spool", "https://maker.example/refill"],
            max_pages=2,
            client=client,
            resolver=_public_resolver,
            default_delay=0,
        )

    assert [page.url for page in result.pages] == [
        "https://maker.example/spool",
        "https://maker.example/refill",
    ]
    assert result.manifest.partial is True


@pytest.mark.asyncio
async def test_reader_decodes_declared_windows_1251_html() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in {"/robots.txt", "/sitemap.xml"}:
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=windows-1251"},
            content="<title>Каталог</title><h1>Пластик</h1>".encode("cp1251"),
        )

    async with _client(handler) as client:
        result = await CatalogSourceReader(
            client=client, resolver=_public_resolver, default_delay=0
        ).read("https://maker.example/catalog")

    assert result.pages[0].title == "Каталог"
    assert result.pages[0].headings == ("Пластик",)


@pytest.mark.asyncio
async def test_overlapping_seeds_do_not_duplicate_pages() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in {"/robots.txt", "/sitemap.xml"}:
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<title>Catalog</title><a href='/item'>Item</a>",
        )

    async with _client(handler) as client:
        result = await read_source_site(
            ["https://maker.example/", "https://maker.example/item"],
            max_pages=3,
            client=client,
            resolver=_public_resolver,
            default_delay=0,
        )

    assert [page.url for page in result.pages] == [
        "https://maker.example/",
        "https://maker.example/item",
    ]


@pytest.mark.asyncio
async def test_image_link_keeps_accessible_title_as_link_context() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in {"/robots.txt", "/sitemap.xml"}:
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<a href='/item' title='PA6 natural 1.75 mm'><img src='/x.png'></a>",
        )

    async with _client(handler) as client:
        result = await CatalogSourceReader(
            client=client, resolver=_public_resolver, max_pages=1, default_delay=0
        ).read("https://maker.example/catalog")

    assert result.pages[0].links[0].text == "PA6 natural 1.75 mm"
    assert result.pages[0].links[0].url == "https://maker.example/item"


@pytest.mark.asyncio
async def test_reader_collects_bounded_safe_image_references_without_fetching_assets() -> None:
    requests: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.path in {"/robots.txt", "/sitemap.xml"}:
            return httpx.Response(404)
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="""<a href='/datasheet' title='Technical data'>
              <img data-src='/spec.png' alt='Drying: 70 C' title='PA6 properties'>
            </a>
            <img srcset='/small.png 1x, /large.png 2x' alt='Dimensions'>
            <img data-lazy-src='https://cdn.example/image.png' alt='External'>
            <img src='javascript:alert(1)' alt='Unsafe'>""",
        )

    async with _client(handler) as client:
        result = await CatalogSourceReader(
            client=client, resolver=_public_resolver, max_pages=1, default_delay=0
        ).read("https://maker.example/catalog")

    images = result.pages[0].images
    assert [(image.url, image.alt) for image in images] == [
        ("https://maker.example/spec.png", "Drying: 70 C"),
        ("https://maker.example/small.png", "Dimensions"),
        ("https://maker.example/large.png", "Dimensions"),
        ("https://cdn.example/image.png", "External"),
    ]
    assert images[0].title == "PA6 properties"
    assert images[0].link_url == "https://maker.example/datasheet"
    assert images[0].link_text == "Technical data"
    assert result.pages[0].image_count == 4
    assert result.pages[0].images_truncated is False
    assert all(not any(request.endswith(name) for name in ("spec.png", "small.png", "large.png", "image.png")) for request in requests)
    dumped = json.loads(json.dumps(result.model_dump()))
    assert dumped["pages"][0]["images"][0]["url"] == "https://maker.example/spec.png"


@pytest.mark.asyncio
async def test_reader_marks_image_reference_truncation() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in {"/robots.txt", "/sitemap.xml"}:
            return httpx.Response(404)
        images = "".join(f'<img src="/image-{index}.png">' for index in range(105))
        return httpx.Response(200, headers={"content-type": "text/html"}, text=images)

    async with _client(handler) as client:
        result = await CatalogSourceReader(
            client=client, resolver=_public_resolver, max_pages=1, default_delay=0
        ).read("https://maker.example/catalog")

    page = result.pages[0]
    assert len(page.images) == 100
    assert page.image_count == 105
    assert page.images_truncated is True
    dumped = json.loads(json.dumps(result.model_dump()))["pages"][0]
    assert dumped["image_count"] == 105
    assert dumped["images_truncated"] is True
