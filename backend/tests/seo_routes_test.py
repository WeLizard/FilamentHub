import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_robots_allows_noindex_pages_to_be_crawled(client: AsyncClient) -> None:
    response = await client.get("/robots.txt")

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert "Disallow: /api/" in response.text
    assert "Disallow: /spool_compat/" in response.text
    assert "Disallow: /profile" not in response.text
    assert "Disallow: /admin" not in response.text
    assert "Disallow: /reset-password" not in response.text
    assert "Sitemap: https://filamenthub.ru/sitemap.xml" in response.text


@pytest.mark.asyncio
async def test_robots_points_each_host_at_its_own_sitemap(client: AsyncClient) -> None:
    response = await client.get("/robots.txt", headers={"host": "filamenthub.club"})

    assert "Sitemap: https://filamenthub.club/sitemap.xml" in response.text
    assert "filamenthub.ru" not in response.text
