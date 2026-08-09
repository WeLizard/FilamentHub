"""Security and publication invariants for user-supplied Wiki images."""

from io import BytesIO

import pytest
from PIL import Image, PngImagePlugin
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.wiki_category import WikiCategory
from app.models.wiki_media import WikiMediaAsset
from app.models.wiki_space import WikiSpace

pytestmark = pytest.mark.asyncio


def _headers(user) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}


async def _seed_wiki(db_session) -> WikiCategory:
    db_session.add_all(
        [
            WikiSpace(id=1, key="guides", order=0, allows_community_authors=False),
            WikiSpace(id=2, key="knowledge", order=10, allows_community_authors=True),
        ]
    )
    category = WikiCategory(
        name="Materials",
        slug="materials",
        description="Material knowledge",
        order=0,
    )
    db_session.add(category)
    await db_session.commit()
    await db_session.refresh(category)
    return category


def _png_bytes(*, width: int = 120, height: int = 80) -> bytes:
    image = Image.new("RGB", (width, height), (64, 128, 192))
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("Comment", "MALICIOUS_METADATA_MARKER")
    output = BytesIO()
    image.save(output, "PNG", pnginfo=metadata)
    return output.getvalue() + b"APPENDED_PAYLOAD_MARKER"


def _animated_webp_bytes() -> bytes:
    first = Image.new("RGB", (32, 32), "red")
    second = Image.new("RGB", (32, 32), "blue")
    output = BytesIO()
    first.save(
        output,
        "WEBP",
        save_all=True,
        append_images=[second],
        duration=100,
        loop=0,
    )
    return output.getvalue()


async def test_upload_rebuilds_image_as_metadata_free_webp(
    client,
    auth_user,
    db_session,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "app.services.wiki_media_service.get_upload_root_dir", lambda: tmp_path
    )

    response = await client.post(
        "/api/v1/wiki/author/media",
        headers=_headers(auth_user),
        files={"file": ("article.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["mime_type"] == "image/webp"
    assert payload["url"].endswith(f"/{payload['id']}.webp")

    asset = (
        await db_session.execute(
            select(WikiMediaAsset).where(WikiMediaAsset.public_id == payload["id"])
        )
    ).scalar_one()
    stored = (tmp_path / asset.storage_path).read_bytes()
    assert b"MALICIOUS_METADATA_MARKER" not in stored
    assert b"APPENDED_PAYLOAD_MARKER" not in stored
    with Image.open(BytesIO(stored)) as decoded:
        assert decoded.format == "WEBP"
        assert decoded.size == (120, 80)
        assert "exif" not in decoded.info
        assert "xmp" not in decoded.info
        assert "icc_profile" not in decoded.info


async def test_upload_rejects_extension_mismatch_and_animation(
    client,
    auth_user,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "app.services.wiki_media_service.get_upload_root_dir", lambda: tmp_path
    )

    mismatch = await client.post(
        "/api/v1/wiki/author/media",
        headers=_headers(auth_user),
        files={"file": ("article.jpg", _png_bytes(), "image/jpeg")},
    )
    assert mismatch.status_code == 400
    assert mismatch.json()["detail"]["code"] == "ERR_FILE_CONTENT_MISMATCH"

    animated = await client.post(
        "/api/v1/wiki/author/media",
        headers=_headers(auth_user),
        files={"file": ("animated.webp", _animated_webp_bytes(), "image/webp")},
    )
    assert animated.status_code == 400
    assert (
        animated.json()["detail"]["code"]
        == "ERR_WIKI_MEDIA_ANIMATED_NOT_ALLOWED"
    )


async def test_upload_enforces_per_account_asset_quota(
    client,
    auth_user,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "app.services.wiki_media_service.get_upload_root_dir", lambda: tmp_path
    )
    monkeypatch.setattr(
        "app.services.wiki_media_service.WIKI_MEDIA_MAX_USER_ASSETS", 0
    )

    response = await client.post(
        "/api/v1/wiki/author/media",
        headers=_headers(auth_user),
        files={"file": ("article.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "ERR_WIKI_MEDIA_QUOTA_EXCEEDED"
    assert list(tmp_path.rglob("*.webp")) == []


async def test_staged_media_becomes_public_only_with_approved_revision(
    client,
    auth_user,
    admin_user,
    db_session,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "app.services.wiki_media_service.get_upload_root_dir", lambda: tmp_path
    )
    category = await _seed_wiki(db_session)

    uploaded = await client.post(
        "/api/v1/wiki/author/media",
        headers=_headers(auth_user),
        files={"file": ("article.png", _png_bytes(), "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    media = uploaded.json()

    anonymous_before = await client.get(media["url"])
    assert anonymous_before.status_code == 404
    owner_preview = await client.get(media["url"], headers=_headers(auth_user))
    assert owner_preview.status_code == 200
    assert owner_preview.headers["content-type"] == "image/webp"
    assert owner_preview.headers["cache-control"] == "private, no-store"

    created = await client.post(
        "/api/v1/wiki/author/articles",
        headers=_headers(auth_user),
        json={
            "category_id": category.id,
            "title": "Safe media article",
            "summary": "An article with moderated media",
            "content": f"![Print result]({media['url']})",
        },
    )
    assert created.status_code == 201, created.text
    revision_id = created.json()["id"]
    submitted = await client.post(
        f"/api/v1/wiki/author/revisions/{revision_id}/submit",
        headers=_headers(auth_user),
        json={"edit_summary": "Add an explanatory image"},
    )
    assert submitted.status_code == 200, submitted.text

    still_private = await client.get(media["url"])
    assert still_private.status_code == 404
    approved = await client.post(
        f"/api/v1/wiki/moderation/revisions/{revision_id}/decision",
        headers=_headers(admin_user),
        json={"decision": "publish", "review_note": "Verified"},
    )
    assert approved.status_code == 200, approved.text

    anonymous_after = await client.get(media["url"])
    assert anonymous_after.status_code == 200
    assert anonymous_after.headers["cache-control"] == (
        "public, max-age=31536000, immutable"
    )
    asset = (
        await db_session.execute(
            select(WikiMediaAsset).where(WikiMediaAsset.public_id == media["id"])
        )
    ).scalar_one()
    assert asset.published is True
    assert asset.published_at is not None


async def test_draft_cannot_reference_another_users_staged_media(
    client,
    auth_user,
    admin_user,
    db_session,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(
        "app.services.wiki_media_service.get_upload_root_dir", lambda: tmp_path
    )
    category = await _seed_wiki(db_session)
    uploaded = await client.post(
        "/api/v1/wiki/author/media",
        headers=_headers(auth_user),
        files={"file": ("article.png", _png_bytes(), "image/png")},
    )
    assert uploaded.status_code == 201

    response = await client.post(
        "/api/v1/wiki/author/articles",
        headers=_headers(admin_user),
        json={
            "category_id": category.id,
            "space_key": "knowledge",
            "title": "Borrowed staged image",
            "summary": "Should not be accepted",
            "content": f"![Private]({uploaded.json()['url']})",
        },
    )
    # Editors may inspect staged media during moderation, but cannot silently
    # take ownership of it in a separate draft.
    assert response.status_code == 403
