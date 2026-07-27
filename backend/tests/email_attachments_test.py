"""What can be attached to a letter, and what a browser does with it."""

from __future__ import annotations

import base64

import pytest
from fastapi import HTTPException

from app.services.email_attachment_service import prepare_email_attachments
from app.services.email_service import ADMIN_REPLY_TEMPLATES, format_recipient


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


@pytest.mark.asyncio
async def test_an_attachment_reaches_the_provider_intact() -> None:
    """Base64 in, the same bytes out: the file must survive the trip."""
    content = b"<!doctype html><h1>Application</h1>"
    prepared = await prepare_email_attachments([_Upload("form.html", content)])
    payload = prepared[0].provider_payload()

    assert payload["filename"] == "form.html"
    assert base64.b64decode(payload["content"]) == content


def test_the_letter_is_addressed_to_a_person() -> None:
    assert format_recipient("team@orca.io", "Orca team") == '"Orca team" <team@orca.io>'
    assert format_recipient("team@orca.io", "") == "team@orca.io"


def test_a_name_cannot_smuggle_another_recipient() -> None:
    addressed = format_recipient("team@orca.io", 'Evil", <thief@example.com>')

    assert addressed.count("<") == 1
    assert "thief@example.com>" not in addressed.split("<")[1]


def test_support_writes_plainly_and_partners_get_the_branded_card() -> None:
    """A person with a problem wants an answer, not a postcard."""
    assert ADMIN_REPLY_TEMPLATES["support"] == "admin_reply_plain.html"
    assert ADMIN_REPLY_TEMPLATES["partnerships"] == "admin_reply.html"
    assert ADMIN_REPLY_TEMPLATES["pr"] == "admin_reply.html"


def test_both_templates_render_the_letter() -> None:
    from app.services.email_service import _render

    for template in set(ADMIN_REPLY_TEMPLATES.values()):
        html = _render(
            template,
            subject="Partner application",
            body="Please find our application attached.",
            body_html=None,
            contact_email="hello@filamenthub.ru",
        )
        assert "Please find our application attached." in html
        assert "hello@filamenthub.ru" in html
