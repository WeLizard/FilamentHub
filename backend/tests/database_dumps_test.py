"""Admin database dumps: reachable, guarded, and never in the served tree."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.services.database_service import _encrypt_dump


def test_dumps_live_outside_the_uploads_tree():
    dumps = Path(settings.DATABASE_DUMP_DIR).resolve()
    uploads = Path(settings.UPLOAD_DIR).resolve()
    assert not dumps.is_relative_to(uploads)


@pytest.mark.asyncio
async def test_a_stranger_is_not_shown_the_dumps(client: AsyncClient):
    """Asking for both clients in one test would authorise this one.

    `auth_client` is the same object as `client` with a token written into its
    headers, so a single test taking both never makes an anonymous request —
    the signed-in 403 merely looks like the anonymous one.
    """
    assert (await client.get("/api/v1/admin/database/dumps")).status_code == 401


@pytest.mark.asyncio
async def test_an_ordinary_account_is_not_shown_the_dumps(auth_client: AsyncClient):
    assert (await auth_client.get("/api/v1/admin/database/dumps")).status_code == 403


@pytest.mark.asyncio
async def test_admin_sees_the_dump_list(admin_client: AsyncClient):
    response = await admin_client.get("/api/v1/admin/database/dumps")
    assert response.status_code == 200
    assert isinstance(response.json()["dumps"], list)


@pytest.mark.asyncio
async def test_deleting_a_missing_dump_answers_not_found(admin_client: AsyncClient):
    response = await admin_client.delete("/api/v1/admin/database/dumps/nope.sql")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_dump_stays_put_when_no_key_is_configured(tmp_path, monkeypatch):
    """Losing the backup before a migration is worse than an unencrypted one."""
    monkeypatch.setattr(settings, "BACKUP_PUBLIC_KEY", str(tmp_path / "absent.asc"))
    dump = tmp_path / "dump.sql"
    dump.write_text("-- data", encoding="utf-8")

    result, encrypted = await _encrypt_dump(dump)

    assert encrypted is False
    assert result == dump
    assert dump.exists()
