"""Image attachments on admin feedback replies."""

from io import BytesIO
from uuid import uuid4

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.applications import Starlette
from starlette.testclient import TestClient

from app.core.security import create_access_token
from app.main import PublicStaticFiles
from app.models.feedback import FeedbackMessage, FeedbackMessageAttachment
from app.models.notification import Notification
from app.models.user import User, UserRole
from app.services.account_deletion import delete_user_account
from app.services.legal_acceptance_service import (
    CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    CURRENT_TERMS_VERSION,
)


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': user.email})}"}


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (40, 30), (10, 120, 200)).save(output, "PNG")
    return output.getvalue()


@pytest.fixture
def upload_root(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.feedback_media.get_upload_root_dir", lambda: tmp_path)
    return tmp_path


def _stored_files(root) -> list:
    return [path for path in (root / "feedback_media").rglob("*") if path.is_file()]


async def _thread(client: AsyncClient, user: User) -> int:
    response = await client.post(
        "/api/v1/feedback/",
        headers=_headers(user),
        json={"type": "bug", "subject": "Screenshot", "message": "See my screen"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _reply(client: AsyncClient, admin: User, feedback_id: int, files, *, key=None, text="Fixed"):
    return client.post(
        f"/api/v1/feedback/{feedback_id}/admin-reply",
        headers=_headers(admin),
        data={"message": text, "idempotency_key": key or str(uuid4())},
        files=[("images", (name, data, "image/png")) for name, data in files],
    )


async def _other_user(db_session: AsyncSession) -> User:
    user = User(
        email="stranger@example.com",
        username="stranger",
        password_hash="$2b$12$test",
        active=True,
        email_verified=True,
        role=UserRole.USER,
        terms_version_accepted=CURRENT_TERMS_VERSION,
        personal_data_consent_version=CURRENT_PERSONAL_DATA_CONSENT_VERSION,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_attachment_is_visible_only_to_thread_owner_and_admin(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_user: User,
    admin_user: User,
    upload_root,
) -> None:
    feedback_id = await _thread(client, auth_user)
    reply = await _reply(client, admin_user, feedback_id, [("shot.png", _png())])
    assert reply.status_code == 200, reply.text
    attachment = reply.json()["messages"][-1]["attachments"][0]
    assert attachment["url"] == (
        f"/api/v1/feedback/{feedback_id}/attachments/{attachment['public_id']}.webp"
    )
    assert (attachment["width"], attachment["height"]) == (40, 30)

    owner = await client.get(attachment["url"], headers=_headers(auth_user))
    assert owner.status_code == 200
    assert owner.headers["content-type"] == "image/webp"
    assert owner.headers["x-content-type-options"] == "nosniff"
    assert owner.headers["cache-control"] == "private, no-cache"
    assert (await client.get(attachment["url"], headers=_headers(admin_user))).status_code == 200

    stranger = await _other_user(db_session)
    assert (await client.get(attachment["url"], headers=_headers(stranger))).status_code == 404
    assert (await client.get(attachment["url"])).status_code in {401, 404}

    other_thread = await _thread(client, stranger)
    cross = f"/api/v1/feedback/{other_thread}/attachments/{attachment['public_id']}.webp"
    assert (await client.get(cross, headers=_headers(stranger))).status_code == 404


def test_feedback_media_is_not_served_by_the_public_uploads_mount(tmp_path) -> None:
    media_dir = tmp_path / "feedback_media" / "ab"
    media_dir.mkdir(parents=True)
    (media_dir / "asset.webp").write_bytes(b"private image")
    static_app = Starlette()
    static_app.mount("/uploads", PublicStaticFiles(directory=tmp_path))

    with TestClient(static_app) as static_client:
        response = static_client.get("/uploads/feedback_media/ab/asset.webp")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_retry_with_the_same_key_stores_nothing_twice(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_user: User,
    admin_user: User,
    upload_root,
) -> None:
    feedback_id = await _thread(client, auth_user)
    key = str(uuid4())
    first = await _reply(client, admin_user, feedback_id, [("a.png", _png())], key=key)
    assert first.status_code == 200
    retry = await _reply(client, admin_user, feedback_id, [("a.png", _png())], key=key)
    assert retry.status_code == 200

    assert len(retry.json()["messages"]) == 2
    assert len(_stored_files(upload_root)) == 1
    count = await db_session.scalar(select(func.count(FeedbackMessageAttachment.id)))
    assert count == 1


@pytest.mark.asyncio
async def test_invalid_image_in_batch_leaves_no_message_and_no_file(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_user: User,
    admin_user: User,
    upload_root,
) -> None:
    feedback_id = await _thread(client, auth_user)
    response = await _reply(
        client,
        admin_user,
        feedback_id,
        [("ok.png", _png()), ("broken.png", b"not an image")],
    )
    assert response.status_code >= 400

    assert _stored_files(upload_root) == []
    admin_messages = await db_session.scalar(
        select(func.count(FeedbackMessage.id)).where(FeedbackMessage.author_type == "admin")
    )
    assert admin_messages == 0


@pytest.mark.asyncio
async def test_reply_limits_and_empty_payload(
    client: AsyncClient,
    auth_user: User,
    admin_user: User,
    upload_root,
) -> None:
    feedback_id = await _thread(client, auth_user)
    too_many = await _reply(
        client, admin_user, feedback_id, [(f"{i}.png", _png()) for i in range(5)]
    )
    assert too_many.status_code == 400
    assert too_many.json()["detail"]["code"] == "ERR_MAX_FILES_EXCEEDED"

    wrong_ext = await _reply(client, admin_user, feedback_id, [("x.gif", _png())])
    assert wrong_ext.json()["detail"]["code"] == "ERR_FILE_EXT_NOT_ALLOWED"

    empty = await _reply(client, admin_user, feedback_id, [], text="  ")
    assert empty.status_code == 422
    assert _stored_files(upload_root) == []


@pytest.mark.asyncio
async def test_deleting_a_thread_removes_its_attachment_files(
    client: AsyncClient,
    auth_user: User,
    admin_user: User,
    upload_root,
) -> None:
    feedback_id = await _thread(client, auth_user)
    reply = await _reply(client, admin_user, feedback_id, [("a.png", _png()), ("b.png", _png())])
    assert reply.status_code == 200
    assert len(_stored_files(upload_root)) == 2

    deleted = await client.delete(f"/api/v1/feedback/{feedback_id}", headers=_headers(admin_user))
    assert deleted.status_code == 200
    assert _stored_files(upload_root) == []


@pytest.mark.asyncio
async def test_failure_after_files_are_written_removes_them(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_user: User,
    admin_user: User,
    upload_root,
    monkeypatch,
) -> None:
    feedback_id = await _thread(client, auth_user)

    async def fail_notification(**_kwargs):
        raise RuntimeError("notification store unavailable")

    monkeypatch.setattr("app.services.notification_service.create_notification", fail_notification)
    try:
        response = await _reply(
            client, admin_user, feedback_id, [("a.png", _png()), ("b.png", _png())]
        )
        assert response.status_code >= 500
    except RuntimeError:
        pass

    assert _stored_files(upload_root) == []
    admin_messages = await db_session.scalar(
        select(func.count(FeedbackMessage.id)).where(FeedbackMessage.author_type == "admin")
    )
    assert admin_messages == 0


@pytest.mark.asyncio
async def test_image_only_reply_keeps_text_and_sends_a_readable_notification(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_user: User,
    admin_user: User,
    upload_root,
) -> None:
    feedback_id = await _thread(client, auth_user)
    first = await _reply(client, admin_user, feedback_id, [], text="Looking into it")
    assert first.status_code == 200
    reply = await _reply(client, admin_user, feedback_id, [("a.png", _png())], text="")
    assert reply.status_code == 200, reply.text

    assert reply.json()["admin_response"] == "Looking into it"
    messages = (
        await db_session.scalars(
            select(Notification.message)
            .where(Notification.user_id == auth_user.id)
            .order_by(Notification.id)
        )
    ).all()
    assert messages[-1] == "feedback_response_images"


@pytest.mark.asyncio
async def test_deleting_the_account_removes_screenshots_from_its_threads(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_user: User,
    admin_user: User,
    upload_root,
) -> None:
    feedback_id = await _thread(client, auth_user)
    reply = await _reply(client, admin_user, feedback_id, [("a.png", _png())])
    assert reply.status_code == 200
    assert len(_stored_files(upload_root)) == 1

    user = await db_session.get(User, auth_user.id)
    await delete_user_account(
        user, delete_reviews=True, release_brand_representation=True, db=db_session
    )

    assert _stored_files(upload_root) == []
