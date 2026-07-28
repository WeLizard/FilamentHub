"""The uploads mount must never hand out anything but user-facing files."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.main import PublicStaticFiles


@pytest.mark.parametrize(
    "path",
    [
        "database_dumps/backup.sql",
        "database_dumps/nested/backup.sql.gz",
        "brand_requests/proof.pdf",
        "printer_requests/proof.pdf",
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
