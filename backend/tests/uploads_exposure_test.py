"""The uploads mount must never hand out anything but user-facing files."""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from starlette.applications import Starlette
from starlette.testclient import TestClient

from app.main import PublicStaticFiles


@pytest.mark.parametrize(
    "path",
    [
        "database_dumps/backup.sql",
        "database_dumps/nested/backup.sql.gz",
        "brand_requests/proof.pdf",
        "printer_requests/proof.pdf",
        "wiki_media/ab/asset.webp",
    ],
)
def test_protected_prefixes_cover_what_must_not_be_public(path: str):
    assert path.startswith(PublicStaticFiles._protected_prefixes)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/uploads/database_dumps/filamenthub_backup_20251214_195555.sql",
        "/uploads/database_dumps/anything.sql.gz",
    ],
)
async def test_a_database_dump_is_never_served(client: AsyncClient, path: str):
    response = await client.get(path)
    assert response.status_code == 404


def test_managed_wiki_media_is_never_served_by_the_public_uploads_mount(tmp_path):
    media_dir = tmp_path / "wiki_media" / "ab"
    media_dir.mkdir(parents=True)
    (media_dir / "asset.webp").write_bytes(b"private staged image")
    static_app = Starlette()
    static_app.mount("/uploads", PublicStaticFiles(directory=tmp_path))

    with TestClient(static_app) as client:
        response = client.get("/uploads/wiki_media/ab/asset.webp")

    assert response.status_code == 404


@pytest.mark.parametrize("directory", ["avatars", "brand_logos"])
def test_versioned_public_images_are_immutable(tmp_path, directory: str):
    image_dir = tmp_path / directory
    image_dir.mkdir()
    (image_dir / "1_deadbeef.webp").write_bytes(b"image")
    static_app = Starlette()
    static_app.mount("/uploads", PublicStaticFiles(directory=tmp_path))

    with TestClient(static_app) as client:
        response = client.get(f"/uploads/{directory}/1_deadbeef.webp")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
