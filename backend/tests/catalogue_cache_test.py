"""The catalogue is fetched once and then confirmed, not fetched again."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand import Brand
from app.models.filament import Filament


async def _catalogue(db: AsyncSession) -> Filament:
    brand = Brand(name="Cache Brand", slug="cache-brand", active=True)
    db.add(brand)
    await db.flush()
    filament = Filament(
        brand_id=brand.id,
        name="Cache PLA",
        slug="cache-pla",
        material_type="PLA",
        diameter=1.75,
        active=True,
    )
    db.add(filament)
    await db.commit()
    return filament


@pytest.mark.asyncio
async def test_a_catalogue_answer_carries_a_version_and_a_lifetime(
    client: AsyncClient, db_session: AsyncSession
):
    await _catalogue(db_session)

    response = await client.get("/api/v1/filaments/", params={"size": 20})

    assert response.status_code == 200
    assert response.headers["etag"]
    assert "max-age=60" in response.headers["cache-control"]


@pytest.mark.asyncio
async def test_asking_again_with_the_same_version_is_answered_without_the_body(
    client: AsyncClient, db_session: AsyncSession
):
    await _catalogue(db_session)

    first = await client.get("/api/v1/filaments/", params={"size": 20})
    again = await client.get(
        "/api/v1/filaments/",
        params={"size": 20},
        headers={"If-None-Match": first.headers["etag"]},
    )

    assert again.status_code == 304
    assert again.content == b""


@pytest.mark.asyncio
async def test_a_changed_catalogue_gets_a_new_version(
    client: AsyncClient, db_session: AsyncSession
):
    filament = await _catalogue(db_session)

    before = await client.get("/api/v1/filaments/", params={"size": 20})

    filament.name = "Cache PLA renamed"
    await db_session.commit()

    after = await client.get(
        "/api/v1/filaments/",
        params={"size": 20},
        headers={"If-None-Match": before.headers["etag"]},
    )

    assert after.status_code == 200
    assert after.headers["etag"] != before.headers["etag"]


@pytest.mark.asyncio
async def test_private_answers_are_left_alone(client: AsyncClient):
    """Nothing outside the public catalogue may be handed a shared lifetime."""
    response = await client.get("/api/v1/auth/legal-requirements")

    assert "cache-control" not in response.headers or "public" not in response.headers[
        "cache-control"
    ]


def test_nothing_shared_depends_on_who_is_asking():
    """The guard that stops a shared cache being handed one person's answer.

    A first attempt matched whole branches of the API by their address, which
    swept in a brand's team roster and its usage report — both answer per user.
    Anything declared cacheable must take no user, and this fails if one ever
    does again.
    """
    import inspect

    from app.main import app
    from app.middleware.catalogue_cache import CACHEABLE_ROUTES

    user_markers = ("current_user", "get_current", "require_", "api_key")
    offenders = []
    matched = set()

    for route in app.routes:
        path = getattr(route, "path", None)
        if path not in CACHEABLE_ROUTES or "GET" not in (getattr(route, "methods", None) or ()):
            continue
        matched.add(path)
        source = inspect.getsource(route.endpoint)
        if any(marker in source for marker in user_markers):
            offenders.append(path)

    assert not offenders, f"общий кеш обещан ручкам, зависящим от пользователя: {offenders}"
    assert matched == set(CACHEABLE_ROUTES), (
        f"в списке кешируемых есть несуществующие маршруты: {set(CACHEABLE_ROUTES) - matched}"
    )
