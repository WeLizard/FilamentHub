"""What can be attached to a letter, and what a browser does with it."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.email_attachment_service import prepare_email_attachments


class _Upload:
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self._content = content

    async def read(self, size: int = -1) -> bytes:
        return self._content


@pytest.mark.asyncio
async def test_a_web_page_can_be_attached() -> None:
    """Sending a rendered page to a partner is ordinary work."""
    prepared = await prepare_email_attachments(
        [_Upload("release-notes.html", b"<!doctype html><p>hello</p>")]
    )

    assert len(prepared) == 1
    assert prepared[0].filename == "release-notes.html"
    assert prepared[0].content_type == "text/html"


@pytest.mark.asyncio
async def test_the_older_extension_works_too() -> None:
    prepared = await prepare_email_attachments([_Upload("page.htm", b"<html></html>")])

    assert prepared[0].content_type == "text/html"


@pytest.mark.asyncio
async def test_an_executable_is_still_refused() -> None:
    with pytest.raises(HTTPException):
        await prepare_email_attachments([_Upload("setup.exe", b"MZ")])
