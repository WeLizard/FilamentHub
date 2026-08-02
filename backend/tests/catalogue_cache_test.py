"""The catalogue is fetched once and then confirmed, not fetched again."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, Response, StreamingResponse

from app.db.session import get_db
from app.middleware.catalogue_cache import (
    MAX_CACHEABLE_BODY_BYTES,
    CatalogueCacheMiddleware,
)
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
    assert response.headers.get_list("content-length") == [str(len(response.content))]


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
    for header in (
        "content-length",
        "content-type",
        "content-encoding",
        "content-range",
        "transfer-encoding",
    ):
        assert again.headers.get_list(header) == []
    assert again.headers["etag"] == first.headers["etag"]


@pytest.mark.asyncio
async def test_if_none_match_uses_get_weak_comparison(
    client: AsyncClient, db_session: AsyncSession
):
    await _catalogue(db_session)

    first = await client.get("/api/v1/filaments/", params={"size": 20})
    etag = first.headers["etag"]

    validators = (
        f"W/{etag}",
        f'"unrelated", {etag}',
        "*",
    )
    for validator in validators:
        response = await client.get(
            "/api/v1/filaments/",
            params={"size": 20},
            headers={"If-None-Match": validator},
        )
        assert response.status_code == 304
        assert response.content == b""
        assert response.headers.get_list("content-length") == []


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


@pytest.mark.asyncio
async def test_mutation_adjacent_slug_suggestion_is_not_cached(client: AsyncClient):
    """A just-claimed slug must not look available because of a shared response."""
    response = await client.get(
        "/api/v1/brands/slug-suggestion",
        params={"name": "Uncached Brand Name"},
    )

    assert response.status_code == 200
    assert "etag" not in response.headers
    assert "cache-control" not in response.headers or "public" not in response.headers[
        "cache-control"
    ]


@pytest.mark.asyncio
async def test_head_is_not_claimed_as_a_cacheable_contract(client: AsyncClient):
    response = await client.head("/api/v1/filaments/")

    assert response.status_code == 405
    assert "etag" not in response.headers
    assert "cache-control" not in response.headers


@pytest.mark.asyncio
async def test_endpoint_cache_policy_takes_priority():
    app = FastAPI()

    @app.get("/api/v1/filaments/")
    async def endpoint():
        return JSONResponse(
            {"ok": True},
            headers={"Cache-Control": "private, no-store"},
        )

    app.add_middleware(CatalogueCacheMiddleware)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/filaments/")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert "etag" not in response.headers


@pytest.mark.asyncio
async def test_endpoint_etag_takes_priority():
    app = FastAPI()

    @app.get("/api/v1/filaments/")
    async def endpoint():
        return JSONResponse({"ok": True}, headers={"ETag": '"endpoint-owned"'})

    app.add_middleware(CatalogueCacheMiddleware)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/filaments/")

    assert response.status_code == 200
    assert response.headers["etag"] == '"endpoint-owned"'
    assert "cache-control" not in response.headers


@pytest.mark.asyncio
async def test_cookie_response_is_not_shared_and_keeps_all_cookies():
    app = FastAPI()

    @app.get("/api/v1/filaments/")
    async def endpoint():
        response = JSONResponse({"ok": True})
        response.set_cookie("first", "one")
        response.set_cookie("second", "two")
        return response

    app.add_middleware(CatalogueCacheMiddleware)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/filaments/")

    assert response.status_code == 200
    assert len(response.headers.get_list("set-cookie")) == 2
    assert "cache-control" not in response.headers
    assert "etag" not in response.headers


@pytest.mark.asyncio
async def test_streaming_response_is_not_buffered_or_cached():
    app = FastAPI()

    async def chunks():
        yield b'{"ok":'
        yield b"true}"

    @app.get("/api/v1/filaments/")
    async def endpoint():
        return StreamingResponse(chunks(), media_type="application/json")

    app.add_middleware(CatalogueCacheMiddleware)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/filaments/")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert "content-length" not in response.headers
    assert "cache-control" not in response.headers
    assert "etag" not in response.headers


@pytest.mark.asyncio
async def test_oversized_response_is_not_buffered_or_cached():
    app = FastAPI()
    body = b"x" * (MAX_CACHEABLE_BODY_BYTES + 1)

    @app.get("/api/v1/filaments/")
    async def endpoint():
        return Response(content=body, media_type="application/octet-stream")

    app.add_middleware(CatalogueCacheMiddleware)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/filaments/")

    assert response.status_code == 200
    assert response.content == body
    assert response.headers["content-length"] == str(len(body))
    assert "cache-control" not in response.headers
    assert "etag" not in response.headers


def test_nothing_shared_depends_on_who_is_asking():
    """The guard that stops a shared cache being handed one person's answer.

    A first attempt matched whole branches of the API by their address, which
    swept in a brand's team roster and its usage report — both answer per user.
    Anything declared cacheable must take no user, and this fails if one ever
    does again.
    """
    from app.main import app
    from app.middleware.catalogue_cache import CACHEABLE_ROUTES

    allowed_dependencies = {get_db}
    offenders = {}
    matched = set()

    def dependency_calls(dependant):
        calls = set()
        for dependency in dependant.dependencies:
            if dependency.call is not None:
                calls.add(dependency.call)
            calls.update(dependency_calls(dependency))
        return calls

    def dependency_name(call):
        module = getattr(call, "__module__", type(call).__module__)
        name = getattr(call, "__qualname__", type(call).__qualname__)
        return f"{module}.{name}"

    for route in app.routes:
        path = getattr(route, "path", None)
        if path not in CACHEABLE_ROUTES or "GET" not in (getattr(route, "methods", None) or ()):
            continue
        matched.add(path)
        unexpected = dependency_calls(route.dependant) - allowed_dependencies
        if unexpected:
            offenders[path] = sorted(dependency_name(call) for call in unexpected)

    assert not offenders, f"общий кеш обещан ручкам с непроверенными зависимостями: {offenders}"
    assert matched == set(CACHEABLE_ROUTES), (
        f"в списке кешируемых есть несуществующие маршруты: {set(CACHEABLE_ROUTES) - matched}"
    )
